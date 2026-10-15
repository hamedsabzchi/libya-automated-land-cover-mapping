"""Real EE client serialization with official offline fixtures; no server execution."""

import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch

try:
    import ee
    from ee.apitestcase import ApiTestCase
except ModuleNotFoundError as exc:
    if exc.name != 'ee':
        raise
    ee = None
    ApiTestCase = unittest.TestCase

from python import landcover_engine as lc


def invocations(value):
    if isinstance(value, dict):
        if 'functionInvocationValue' in value:
            yield value['functionInvocationValue']
        for child in value.values():
            yield from invocations(child)
    elif isinstance(value, list):
        for child in value:
            yield from invocations(child)


@unittest.skipIf(ee is None, 'Install tests/requirements.txt for actual EE-client graph tests')
class EarthEngineGraphTests(ApiTestCase):
    def setUp(self):
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden in offline tests'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.original_install = ee.data._install_cloud_api_resource
        self.addCleanup(setattr, ee.data, '_install_cloud_api_resource', self.original_install)
        super().setUp()  # Google's static algorithm fixtures, fake API endpoints.
        self.cfg = lc.LandCoverConfig(aoi_asset='projects/example/assets/aoi',
                                      training_asset='projects/example/assets/train', year_count=2)
        self.report = {'aoiFeatures':1,'aoiAreaM2':100,'trainingFeatures':4,
                       'classHistogram':{'1':2,'2':2}}
        self.coverage = {f'{region}_{year}':1 for region in ['train','aoi'] for year in self.cfg.years}

    def prepare(self):
        with patch.object(ee.data,'computeValue',side_effect=[self.report,self.coverage]) as compute:
            prepared = lc.prepare_inputs(self.cfg)
            self.assertEqual(compute.call_count,2)
        return prepared

    def test_wp05_drive_request_restores_graph_and_uses_explicit_grid(self):
        import hashlib
        import zipfile
        from test_jobs import bundle_files
        from libya_landcover.job_store import JobStore
        from libya_landcover.jobs import import_bundle
        from libya_landcover.exports import enqueue_export, EarthEngineBackend
        files=bundle_files()
        model=lc.build_seed_model(self.cfg,42,prepared=self.prepare())
        graph=model['final_map'].serialize().encode()
        index=json.loads(files['graphs/index.json'])
        for identifier,record in index['artifacts'].items():
            record['sha256']=hashlib.sha256(graph).hexdigest()
            files['graphs/'+identifier+'.json']=graph
        files['graphs/index.json']=json.dumps(index).encode()
        with tempfile.TemporaryDirectory() as folder:
            store=JobStore(Path(folder)/'store');archive=Path(folder)/'bundle.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for name,data in files.items():z.writestr('run/'+name,data)
            source=import_bundle(store,archive)
            identifier=json.loads(files['result.json'])['outputs'][0]['artifact_id']
            job=enqueue_export(store,source['job_id'],identifier,
                               {'crs':'EPSG:32633','transform':[10,0,0,0,-10,0]},request_id=str(uuid4()))
            backend=object.__new__(EarthEngineBackend);backend.ee=ee
            with patch.object(lc,'search_seeds',side_effect=AssertionError('No seed search during export')), \
                    patch.object(ee.data,'computeValue',side_effect=AssertionError('No evaluation during preparation')):
                payload=backend.prepare(store,job)
            encoded=json.dumps(payload,allow_nan=False)
            self.assertIn('EPSG:32633',encoded)
            self.assertIn('Image.toUint8',encoded)
            self.assertEqual(payload['fileExportOptions']['fileFormat'],'GEO_TIFF')
            self.assertTrue(payload['fileExportOptions']['geoTiffOptions']['cloudOptimized'])
            self.assertEqual(payload['fileExportOptions']['driveDestination']['folder'],
                             'LibyaLandCover_'+job['ee_request_id'])
            with patch.object(ee.data,'exportImage',return_value={'name':'projects/test/operations/export1'}) as start:
                backend.start(job['job_id'],payload)
            self.assertEqual(start.call_args.args,(job['job_id'],payload))

    def test_wp04_graph_store_roundtrip_and_checksum(self):
        from libya_landcover.bundle import GraphArtifactStore
        image = lc.build_seed_model(self.cfg,42,prepared=self.prepare())['final_map']
        with tempfile.TemporaryDirectory() as folder:
            store = GraphArtifactStore(folder)
            run_id, artifact_id = str(uuid4()), str(uuid4())
            store.save_many(run_id,{artifact_id:image})
            restored = store.get(run_id,artifact_id)
            self.assertEqual(json.loads(restored.serialize()),json.loads(image.serialize()))
            with self.assertRaises(KeyError): store.get(str(uuid4()),artifact_id)
            (Path(folder)/'graphs'/(artifact_id+'.json')).write_text('{}')
            with self.assertRaisesRegex(ValueError,'checksum'): store.get(run_id,artifact_id)

    def test_wp04_probe_graph_uses_explicit_grid_and_observes_masks(self):
        from contracts import RunRequest
        from libya_landcover.evidence import capture
        model = lc.build_seed_model(self.cfg,42,prepared=self.prepare())
        request = RunRequest({'request_id':str(uuid4()),'aoi_asset':self.cfg.aoi_asset,
                             'training_asset':self.cfg.training_asset,'year_count':2})
        spec = {'crs':'EPSG:32633','transform':[10,0,0,0,-10,0],
                'points':[{'id':'a','lon':13.2,'lat':32.8}]}
        result = SimpleNamespace(to_dict=lambda:{'selection':{},'metrics':{}})
        replies = [{'normalized':['a','b'],'train':['0_a'],'validation':['0_b']},
                   {'features':[{'properties':{'probe_id':'a','final':4,'final_mask':1}}]}]
        with patch.object(ee.data,'computeValue',side_effect=replies) as compute:
            record = capture(SimpleNamespace(result=result,model=model),request,spec)
        graph = compute.call_args_list[1].args[0].serialize()
        self.assertIn('Image.reduceRegions',graph)
        self.assertIn('EPSG:32633',graph)
        self.assertIn('final_mask',graph)
        self.assertEqual(record['raster_probes']['spec'],spec)

    def test_full_candidate_and_metric_graphs_serialize_without_network(self):
        prepared = self.prepare()
        with patch.object(ee.data,'computeValue',side_effect=AssertionError('Graph build must not evaluate')):
            model = lc.build_seed_model(self.cfg,42,prepared=prepared)
            final = json.loads(model['final_map'].serialize())
            metric = json.loads(lc.metrics_dictionary(model).serialize())
        names = {f['functionName'] for f in invocations(final)}
        self.assertTrue({'Classifier.smileRandomForest','Classifier.train','Image.classify',
                         'Image.where','Image.clip','Image.sampleRegions'} <= names)
        metric_names = {f['functionName'] for f in invocations(metric)}
        self.assertIn('Collection.errorMatrix',metric_names)
        self.assertIn('ConfusionMatrix.producersAccuracy',metric_names)
        self.assertNotEqual(model['final_map'].serialize(),model['validation_map'].serialize())

    def test_split_uses_sorted_count_clamp_and_slices(self):
        prepared = self.prepare()
        train, validation = lc.stratified_split(prepared.points,self.cfg,42)
        encoded = train.serialize()
        calls = list(invocations(json.loads(encoded)))
        names = {f['functionName'] for f in calls}
        self.assertTrue({'Collection.randomColumn','Collection.limit','Number.floor','Number.min',
                         'Number.max','List.slice','Collection.flatten'} <= names)
        self.assertIn('_flex_random',encoded)
        random_calls = [f for f in calls if f['functionName']=='Collection.randomColumn']
        self.assertEqual(random_calls[0]['arguments']['seed']['constantValue'],42)
        self.assertNotEqual(train.serialize(),validation.serialize())

    def test_full_normalized_training_and_aoi_have_separate_embedding_graphs(self):
        prepared = self.prepare()
        national = prepared.national_embeddings[2024].serialize()
        aoi = prepared.aoi_embeddings[2024].serialize()
        self.assertIn('projects/example/assets/train',national)
        self.assertNotIn('projects/example/assets/aoi',national)
        self.assertIn('projects/example/assets/aoi',aoi)
        self.assertNotIn('projects/example/assets/train',aoi)
        names = [f['functionName'] for f in invocations(json.loads(national))]
        self.assertIn('Image.unmask',names)
        terrain_calls = list(invocations(json.loads(prepared.terrain.serialize())))
        self.assertEqual(sum(f['functionName']=='Image.unmask' for f in terrain_calls),3)

    def test_actual_client_query_error_maps_to_preflight_error(self):
        with patch.object(ee.data,'computeValue',side_effect=RuntimeError('example failure')):
            with self.assertRaises(lc.EngineError) as caught:
                lc.prepare_inputs(self.cfg)
        self.assertEqual(caught.exception.code,'ASSET_ACCESS_OR_SCHEMA')


if __name__=='__main__':
    unittest.main()
