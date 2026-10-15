"""WP04 orchestration, persistence and evidence boundaries. No live EE jobs."""

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from contracts import RunRequest, RunStatus, RunResult, validate_exchange
from contracts.models import GEE_SHA256
from libya_landcover import cli, evidence
from libya_landcover.bundle import GraphArtifactStore
from python import landcover_engine as engine

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    result = json.loads((ROOT / 'contracts/examples/result.json').read_text())
    return {'schema_version':'wp04.1','source':'python','gee_sha256':GEE_SHA256,
            'config':RunRequest(result['request']).engine_config(),
            'selection':result['selection'],'metrics':result['metrics'],
            'splits':{'normalized':['a','b','c','d'], 'train':['0_a','1_c'], 'validation':['0_b','1_d']},
            'raster_probes':None}


def probes():
    return {'crs':'EPSG:32633','transform':[10,0,0,0,-10,0],
            'points':[{'id':'p1','lon':13.2,'lat':32.8}]}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def call(self, argv):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = cli.main(argv)
        return code, output.getvalue(), errors.getvalue()

    def args(self):
        return ['run',str(ROOT / 'contracts/examples/request.json'),'--project','example-project',
                '--engine-commit','a'*40,'--output',str(self.directory/'run')]

    def test_validate_never_initializes_ee(self):
        with patch.object(cli,'initialize') as initialize:
            code, text, _ = self.call(['validate',str(ROOT/'contracts/examples/request.json')])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(text)['engine_config']['seeds'],list(engine.DEFAULT_SEEDS))
        initialize.assert_not_called()

    def test_bad_commit_and_existing_output_rejected_before_ee(self):
        with patch.object(cli,'initialize') as initialize:
            args = self.args();args[args.index('--engine-commit')+1]='0'*40
            self.assertEqual(self.call(args)[0],2)
            (self.directory/'run').mkdir()
            self.assertEqual(self.call(self.args())[0],2)
        initialize.assert_not_called()

    def test_initialization_failure_is_recorded_without_claiming_model_failure(self):
        with patch.object(cli,'initialize',side_effect=RuntimeError('secret error text')):
            code, output, errors = self.call(self.args())
        self.assertEqual(code,3)
        self.assertNotIn('secret',output+errors)
        manifest = cli.read_json(self.directory/'run/manifest.json')
        self.assertEqual(manifest['bundle_state'],'initialization_failed')
        self.assertFalse((self.directory/'run/result.json').exists())

    def successful_worker(self, config, on_event):
        for phase in ('asset_preflight','coverage_preflight'):
            on_event({'phase':phase})
        on_event({'phase':'seed_search','seed_index':1,'seed_count':14,'current_seed':42})
        on_event({'phase':'preparing_result'})
        metrics = fixture()['metrics'] | {'seed':42,'minimum_producer_percent':100,'target_reached':True}
        image = SimpleNamespace(serialize=lambda:'{"fixture":true}')
        return {'model':{'seed':42,'final_map':image,'yearly':{y:image for y in config.years}},
                'history':[], 'best_metrics':metrics}

    def test_run_persists_linked_result_jsonl_and_atomic_graph_batch(self):
        with patch.object(cli,'initialize'), patch.object(engine,'search_seeds',side_effect=self.successful_worker):
            code, _, _ = self.call(self.args())
        self.assertEqual(code,0)
        folder = self.directory/'run'
        request = RunRequest(cli.read_json(folder/'request.json'))
        result = RunResult(cli.read_json(folder/'result.json'))
        status = RunStatus(cli.read_json(folder/'status.json'))
        validate_exchange(request,status,result)
        lines = (folder/'status.jsonl').read_text().splitlines()
        self.assertEqual(len(lines),6)
        self.assertEqual(json.loads(lines[-1])['state'],'completed')
        index = cli.read_json(folder/'graphs/index.json')
        self.assertEqual(set(index['artifacts']),{o['artifact_id'] for o in result.to_dict()['outputs']})
        self.assertEqual(cli.read_json(folder/'manifest.json')['bundle_state'],'completed')

    def test_capture_failure_keeps_successful_model_and_is_nonzero(self):
        with patch.object(cli,'initialize'), patch.object(engine,'search_seeds',side_effect=self.successful_worker), \
                patch.object(cli,'capture',side_effect=RuntimeError('private')):
            code, _, _ = self.call(self.args()+['--capture-evidence'])
        self.assertEqual(code,4)
        manifest = cli.read_json(self.directory/'run/manifest.json')
        self.assertEqual((manifest['bundle_state'],manifest['evidence_state']),('completed','failed'))
        self.assertTrue((self.directory/'run/result.json').exists())

    def test_graph_batch_failure_rolls_back_and_rejects_path_ids(self):
        store = GraphArtifactStore(self.directory)
        good = SimpleNamespace(serialize=lambda:'{}')
        bad = SimpleNamespace(serialize=lambda:'not JSON')
        with self.assertRaises(ValueError):
            store.save_many(str(uuid4()),{str(uuid4()):good,str(uuid4()):bad})
        self.assertFalse((self.directory/'graphs').exists())
        self.assertFalse((self.directory/'graphs.pending').exists())
        with self.assertRaises(ValueError):
            store.save_many(str(uuid4()),{'../elsewhere':good})
        self.assertFalse((self.directory/'graphs.pending').exists())

    def test_reference_session_retains_original_bytes_and_refuses_overwrite(self):
        reference = ROOT/'gee/automated_land_cover_app.js'
        original = reference.read_bytes()
        output = self.directory/'session.js'
        args = ['prepare-reference','--reference',str(reference),'--output',str(output)]
        self.assertEqual(self.call(args)[0],0)
        self.assertEqual(output.read_bytes()[:len(original)],original)
        self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(),GEE_SHA256)
        self.assertEqual(self.call(args)[0],2)
        changed = self.directory/'changed.js';changed.write_bytes(original+b'\n')
        args[args.index('--reference')+1]=str(changed)
        args[args.index('--output')+1]=str(self.directory/'rejected.js')
        self.assertEqual(self.call(args)[0],2)
        self.assertFalse((self.directory/'rejected.js').exists())

    def test_duplicate_and_nonfinite_json_are_rejected(self):
        path = self.directory/'bad.json'
        for data in ('{"x":1,"x":2}','{"x":NaN}'):
            path.write_text(data)
            with self.assertRaises(ValueError): cli.read_json(path)


class EvidenceTests(unittest.TestCase):
    def test_missing_rasters_cannot_report_match(self):
        left=fixture();right=deepcopy(left);right['source']='gee'
        report=evidence.compare(left,right)
        self.assertEqual(report['status'],'incomplete')
        self.assertEqual(report['missing_observations'],['raster_probes'])
        self.assertFalse(report['full_raster_parity_proven'])

    def complete_pair(self):
        left=fixture()
        row={'probe_id':'p1'}
        for name in ['final','y2024','y2023','y2022','y2021','y2020']:
            row[name]=4;row[name+'_mask']=1
        left['raster_probes']={'spec':probes(),'values':[row]}
        right=deepcopy(left);right['source']='gee'
        return left,right

    def test_complete_observations_match_but_never_claim_whole_raster(self):
        left,right=self.complete_pair()
        right['splits']['train'].reverse()
        report=evidence.compare(left,right)
        self.assertEqual(report['status'],'observations_match')
        self.assertFalse(report['full_raster_parity_proven'])

    def test_config_seed_id_mask_and_pixel_discrepancies_are_detected(self):
        for field in ('config','selection','splits','raster_probes'):
            left,right=self.complete_pair()
            if field=='config': right[field]['target_year']=2023; right['raster_probes']=None
            if field=='selection': right[field]['seed']=123
            if field=='splits': right[field]['train'][0]='changed'
            if field=='raster_probes': right[field]['values'][0]['final_mask']=0
            self.assertEqual(evidence.compare(left,right)['status'],'different')

    def test_bad_sources_empty_evidence_and_incomplete_rows_rejected(self):
        left,right=self.complete_pair()
        for broken in ({}, dict(right,source='python'), dict(right,gee_sha256='0'*64)):
            with self.assertRaises(ValueError): evidence.compare(left,broken)
        right['raster_probes']['values'][0].pop('final_mask')
        with self.assertRaises(ValueError): evidence.compare(left,right)

    def test_probe_plan_rejects_unbounded_duplicate_or_singular_specs(self):
        for item in ({},dict(probes(),transform=[0]*6),dict(probes(),points=[]),
                     dict(probes(),points=probes()['points']*2)):
            with self.assertRaises(ValueError): evidence.validate_probes(item)

    def test_float_tolerance_does_not_hide_different_counts(self):
        left,right=self.complete_pair()
        right['metrics']['overall']-=1e-10
        self.assertEqual(evidence.compare(left,right)['status'],'observations_match')
        right['metrics']['confusion'][0][0]+=1
        right['metrics']['sampled_validation_count']+=1
        self.assertEqual(evidence.compare(left,right)['status'],'different')
