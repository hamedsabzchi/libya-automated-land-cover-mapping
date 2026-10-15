"""WP03 software behavior/port tests; no credentials or remote EE computation."""

from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from python import landcover_engine as lc
from python import assistant_adapter as adapter
from contracts import ContractError, RunRequest, RunStatus, validate_exchange, validate_transition

ROOT = Path(__file__).resolve().parents[1]


def config(**kwargs):
    return lc.LandCoverConfig(aoi_asset='projects/example/assets/aoi',
                              training_asset='projects/example/assets/train', **kwargs)


def metric_payload(score=.8):
    return {'overall':score,'kappa':score,'producer':[score]*12,
            'confusion':[[5 if i==j else 0 for j in range(12)] for i in range(12)],
            'sampled_validation_count':60}


def request():
    return RunRequest({'request_id':'11111111-1111-4111-8111-111111111111',
                       'aoi_asset':'projects/example/assets/aoi','training_asset':'projects/example/assets/train'})


class ReferenceClientTests(unittest.TestCase):
    def oracle(self, items):
        result = subprocess.run(['node',str(ROOT/'tests/reference_client.cjs')],
                                input=json.dumps(items),text=True,capture_output=True,check=True)
        return json.loads(result.stdout)

    def test_asset_normalization_matches_extracted_gee_helper(self):
        values = [' projects/example/assets/aoi ', '"users/owner/roi"',
                  'https://code.earthengine.google.com/?asset=projects%2Fexample%2Fassets%2Faoi',
                  'label: projects/earthengine-legacy/assets/users/demo/aoi;',
                  'prefix users/demo/aoi,', 'bad', '', 'projects/example/assets/aoi%ZZ',
                  'projects/example/assets/aoi%FF']
        for value, expected in zip(values,self.oracle([{'kind':'asset','value':v} for v in values])):
            with self.subTest(value=value):
                if expected['ok']:
                    self.assertEqual(lc.normalize_asset_id(value),expected['result'])
                else:
                    with self.assertRaises(ValueError): lc.normalize_asset_id(value)

    def test_histogram_lookup_matches_extracted_gee_helper(self):
        histogram={'1':3,' 1 ':2,'02':4,'2.0':1,'0x4':5,'5e0':6,'0b110':2,'0o7':2,
                   '12':2,'13':9,'0':1,'bad':3,'':2,'1.2':1,'Infinity':2,'NaN':1,'1_0':2}
        expected=self.oracle([{'kind':'classes','value':histogram}])[0]['result']
        result=lc.build_class_lookup(histogram)
        result['counts']={str(k):v for k,v in result['counts'].items()}
        self.assertEqual(result,expected)

    def test_existing_score_conversion_matches_gee_client_block(self):
        cases=[]
        for shape in ['flat','row','column','object','null','invalid']:
            p=metric_payload(.75)
            p['producer'][7]=.1  # configured exclusion stays excluded
            p['confusion'][2]=[0]*12
            p['producer'][2]=.01  # row without samples is ignored
            if shape=='row': p['producer']=[p['producer']]
            if shape=='column': p['producer']=[[v] for v in p['producer']]
            if shape=='object': p['producer']={str(i):v for i,v in enumerate(p['producer'])}
            if shape=='null': p['producer'][0]=None
            if shape=='invalid': p['producer'][0]='invalid'
            cases.append(p)
        expected=self.oracle([{'kind':'score','value':{'prod':p['producer'],'conf':p['confusion']}} for p in cases])
        for p,ref in zip(cases,expected):
            actual=lc.score_metrics(config(),42,p)
            self.assertEqual(actual['minimum_producer_percent'],ref['result']['score'])
            self.assertEqual(actual['target_reached'],ref['result']['targetReached'])


class EngineControlTests(unittest.TestCase):
    def test_reference_preflight_order_and_branches(self):
        good={'aoiFeatures':1,'aoiAreaM2':10,'trainingFeatures':4,'classHistogram':{'1':2,'2':2}}
        self.assertEqual(lc.validate_asset_report(good)['total'],4)
        cases=[({'aoiFeatures':0},'EMPTY_AOI'),({'aoiAreaM2':0},'EMPTY_AOI'),
               ({'trainingFeatures':0},'EMPTY_TRAINING'),({'classHistogram':{'1':1,'2':1}},'INVALID_CLASSES'),
               ({'classHistogram':{'1':4}},'INSUFFICIENT_CLASSES'),
               ({'classHistogram':{'1':3,'2':1}},'INSUFFICIENT_CLASS_SAMPLES')]
        for patch_values,code in cases:
            with self.subTest(code=code),self.assertRaises(lc.EngineError) as caught:
                lc.validate_asset_report({**good,**patch_values})
            self.assertEqual(caught.exception.code,code)

    def test_fixed_scale_and_deferred_coverage_window(self):
        lc.validate_config(config(target_year=2017,year_count=20))
        for bad in [config(scale_m=30),config(trees=True),config(excluded_class_from_threshold=1000)]:
            with self.assertRaises(ValueError): lc.validate_config(bad)

    def test_target_fallback_is_checked_per_footprint(self):
        cfg=config(year_count=1)
        coverage={'train_2024':1,'aoi_2024':0,'train_2023':0,'aoi_2023':1}
        self.assertEqual(lc.coverage_missing(cfg,coverage),[])
        coverage['aoi_2023']=0
        self.assertEqual(lc.coverage_missing(cfg,coverage),['AOI 2024/2023'])
        cfg=config(year_count=2)
        self.assertIn('training area 2023',lc.coverage_missing(cfg,coverage))

    def test_no_scored_class_is_a_candidate_failure(self):
        payload=metric_payload()
        payload['confusion']=[[0]*12 for _ in range(12)]
        with self.assertRaises(lc.EngineError) as caught: lc.score_metrics(config(),42,payload)
        self.assertEqual(caught.exception.code,'NO_SCORED_CLASSES')

    def test_preflight_failure_prevents_any_candidate_build(self):
        error=lc.EngineError('EMPTY_AOI','asset_preflight','empty')
        with patch.object(lc,'prepare_inputs',side_effect=error),patch.object(lc,'build_seed_model') as build:
            with self.assertRaises(lc.EngineError): lc.search_seeds(config())
            build.assert_not_called()

    def test_failed_seed_ties_exhaustion_and_selected_graph_identity(self):
        cfg=config(seeds=(42,123,256,389))
        objects={s:{'seed':s,'final_map':object()} for s in cfg.seeds}
        scores={123:.55,256:.55,389:.50}
        def evaluate(c,s,m):
            if s==42: raise lc.EngineError('SEED_EVALUATION_FAILED','seed_search','failed')
            return lc.score_metrics(c,s,metric_payload(scores[s]))
        prepared=SimpleNamespace(asset_report={},coverage={})
        events=[]
        with patch.object(lc,'prepare_inputs',return_value=prepared) as prep, \
             patch.object(lc,'build_seed_model',side_effect=lambda c,s,**k:objects[s]) as build, \
             patch.object(lc,'_evaluate_model',side_effect=evaluate):
            output=lc.search_seeds(cfg,on_event=events.append)
        prep.assert_called_once()
        self.assertEqual(build.call_count,4)
        self.assertIs(output['model'],objects[123])
        self.assertEqual(output['best_metrics']['seed'],123)
        self.assertEqual(output['history'][0]['status'],'failed')
        self.assertEqual(events[-1]['phase'],'preparing_result')

    def test_threshold_stops_without_rebuilding_selected_model(self):
        cfg=config(seeds=(42,123,256))
        models=[]
        def build(c,s,**kw):
            model={'seed':s};models.append(model);return model
        with patch.object(lc,'prepare_inputs',return_value=SimpleNamespace(asset_report={},coverage={})), \
             patch.object(lc,'build_seed_model',side_effect=build), \
             patch.object(lc,'_evaluate_model',side_effect=lambda c,s,m:lc.score_metrics(c,s,metric_payload(.6))):
            output=lc.search_seeds(cfg)
        self.assertEqual(len(models),1)
        self.assertIs(output['model'],models[0])

    def test_all_failed_seeds_report_no_success(self):
        with patch.object(lc,'prepare_inputs',return_value=object()), \
             patch.object(lc,'build_seed_model',return_value={}), \
             patch.object(lc,'_evaluate_model',side_effect=lc.EngineError('NO_SCORED_CLASSES','seed_search','none')):
            with self.assertRaises(lc.EngineError) as caught: lc.search_seeds(config(seeds=(42,123)))
        self.assertEqual(caught.exception.code,'NO_SUCCESSFUL_SEED')
        self.assertEqual(len(caught.exception.details['history']),2)

    def test_programming_errors_do_not_silently_skip_candidates(self):
        with patch.object(lc,'prepare_inputs',return_value=object()), \
             patch.object(lc,'build_seed_model',side_effect=TypeError('bug')):
            with self.assertRaises(TypeError): lc.search_seeds(config())

    def test_terrain_fills_each_band_and_keeps_order(self):
        fake=MagicMock()
        with patch.object(lc,'ee',fake): lc.terrain_image()
        dem=fake.Image.return_value
        dem.select.assert_called_once_with('elevation')
        dem.select.return_value.unmask.assert_called_once_with(0)
        fake.Terrain.slope.return_value.unmask.assert_called_once_with(0)
        fake.Terrain.aspect.return_value.unmask.assert_called_once_with(0)
        fake.Image.cat.assert_called_once_with([
            dem.select.return_value.unmask.return_value,
            fake.Terrain.slope.return_value.unmask.return_value,
            fake.Terrain.aspect.return_value.unmask.return_value])

    def test_national_and_aoi_graphs_are_distinct_and_final_uses_aoi(self):
        cfg=config(year_count=1)
        national,aoi=MagicMock(name='national'),MagicMock(name='aoi')
        roi,points,terrain=object(),object(),object()
        prepared=lc.PreparedInputs(cfg,roi,points,terrain,{2024:'national embedding'},
                                   {2024:'aoi embedding'},{},{})
        fake=MagicMock()
        fake.Image.cat.side_effect=[national,aoi]
        temporal=[]
        def combine(images,c):
            temporal.append(images)
            return MagicMock(name='temporal'+str(len(temporal)))
        with patch.object(lc,'ee',fake),patch.object(lc,'stratified_split',return_value=('train','val')), \
             patch.object(lc,'temporal_decision',side_effect=combine):
            result=lc.build_seed_model(cfg,42,prepared=prepared)
        self.assertIs(temporal[1][2024],aoi.classify.return_value.rename.return_value.clip.return_value)
        self.assertIs(temporal[0][2024],national.classify.return_value.rename.return_value)
        aoi.classify.return_value.rename.return_value.clip.assert_called_once_with(roi)
        fake.Classifier.smileRandomForest.assert_called_once_with(numberOfTrees=500,bagFraction=.95,seed=42)
        self.assertEqual(result['seed'],42)


class AdapterTests(unittest.TestCase):
    def selected(self):
        cfg=adapter.config_from_request(request())
        metrics=lc.score_metrics(cfg,42,metric_payload())
        model={'seed':42,'final_map':object(),'yearly':{y:object() for y in cfg.years}}
        return {'model':model,'best_metrics':metrics,'history':[]}

    def worker(self, selected):
        def execute(cfg,on_event):
            for phase in ['asset_preflight','coverage_preflight']:
                on_event({'phase':phase})
            on_event({'phase':'seed_search','seed_index':1,'seed_count':14,'current_seed':42})
            on_event({'phase':'preparing_result'})
            return selected
        return execute

    def test_normalized_request_and_fixed_engine_mapping(self):
        payload=request().to_dict()
        payload['aoi_asset']='"https://code.earthengine.google.com/?asset=projects%2Fexample%2Fassets%2Faoi"'
        normalized=adapter.request_from_inputs(payload)
        self.assertEqual(normalized.to_dict(),request().to_dict())
        self.assertEqual(adapter.config_from_request(normalized).seeds,lc.DEFAULT_SEEDS)

    def test_success_yields_linked_result_and_resolvable_original_handles(self):
        selected=self.selected();statuses=[]
        with patch.object(lc,'search_seeds',side_effect=self.worker(selected)):
            output=adapter.run_request(request(),engine_commit='a'*40,on_status=statuses.append)
        self.assertEqual(output.status.to_dict()['state'],'completed')
        self.assertIs(output.model,selected['model'])
        validate_exchange(request(),output.status,output.result)
        for before,after in zip(statuses,statuses[1:]): validate_transition(before,after)
        result=output.result.to_dict()
        final=result['outputs'][0]
        self.assertIs(output.artifact_store.get(result['run_id'],final['artifact_id']),selected['model']['final_map'])
        output.result.to_json()  # No live EE object leaks into the wire payload.

    def test_preflight_failure_is_typed_and_has_no_result(self):
        def fail(cfg,on_event):
            on_event({'phase':'asset_preflight'})
            raise lc.EngineError('EMPTY_AOI','asset_preflight','AOI is empty')
        with patch.object(lc,'search_seeds',side_effect=fail):
            output=adapter.run_request(request(),engine_commit='a'*40)
        self.assertEqual(output.status.to_dict()['error']['code'],'EMPTY_AOI')
        self.assertIsNone(output.result)

    def test_unexpected_failure_is_not_exposed_as_raw_internal_text(self):
        with patch.object(lc,'search_seeds',side_effect=RuntimeError('private internal text')):
            output=adapter.run_request(request(),engine_commit='a'*40)
        self.assertNotIn('private internal text',output.status.to_json())
        self.assertEqual(output.status.to_dict()['error']['code'],'INTERNAL_ERROR')

    def test_artifact_store_failure_cannot_publish_completed_result(self):
        store=MagicMock();store.save_many.side_effect=RuntimeError('storage failure')
        with patch.object(lc,'search_seeds',side_effect=self.worker(self.selected())):
            output=adapter.run_request(request(),engine_commit='a'*40,artifact_store=store)
        self.assertEqual(output.status.to_dict()['state'],'failed')
        self.assertEqual(output.status.to_dict()['error']['code'],'OUTPUT_PREPARATION_FAILED')
        self.assertIsNone(output.result)

    def test_bad_result_does_not_register_unvalidated_artifacts(self):
        selected=self.selected();selected['model']['seed']=123
        store=MagicMock()
        with patch.object(lc,'search_seeds',side_effect=self.worker(selected)):
            output=adapter.run_request(request(),engine_commit='a'*40,artifact_store=store)
        self.assertEqual(output.status.to_dict()['state'],'failed')
        store.save_many.assert_not_called()

    def test_observer_failure_does_not_restart_or_execute_model(self):
        with patch.object(lc,'search_seeds') as run:
            with self.assertRaises(adapter.StatusDeliveryError):
                adapter.run_request(request(),engine_commit='a'*40,on_status=lambda s:1/0)
        run.assert_not_called()

    def test_provenance_is_required_before_execution(self):
        with patch.object(lc,'search_seeds') as run:
            for commit in ['', '0'*40, 'not-a-sha']:
                with self.assertRaises(ContractError): adapter.run_request(request(),engine_commit=commit)
        run.assert_not_called()


if __name__=='__main__': unittest.main()
