"""Real EE client serialization with official offline fixtures; no server execution."""

import json
import unittest
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
