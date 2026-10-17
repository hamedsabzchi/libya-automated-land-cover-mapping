"""Map display/delivery/UX integration; no live credentials or classifier changes."""
import asyncio
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock,patch
import zipfile
from libya_landcover.assistant import TRIPOLI
from libya_landcover.job_store import JobStore
from libya_landcover.map_assistant import MapAssistant
from libya_landcover.map_view import PALETTE,CLASS_NAMES,feature,tile_at,tile_spec,visible_grid,MapBackend
from libya_landcover.exports import window_bounds
from test_jobs import bundle_files
ROOT=Path(__file__).resolve().parents[1]
HAS_MAP=bool(importlib.util.find_spec('ipyleaflet') and importlib.util.find_spec('pyproj'))

class LegendTests(unittest.TestCase):
    def test_exact_reference_palette_and_names(self):
        source=(ROOT/'gee/automated_land_cover_app.js').read_text()
        for name,expected in [('palette',PALETTE),('classNames',CLASS_NAMES)]:
            contents=re.search(r'var '+name+r' = \[([^]]+)\]',source).group(1)
            self.assertEqual(re.findall(r"'([^']+)'",contents),expected)

@unittest.skipUnless(HAS_MAP,'Install [map]; package CI requires it')
class GridTests(unittest.TestCase):
    def test_grid_has_no_overlap_or_shift_and_roundtrips_click(self):
        a=tile_spec(36864,-339968);b=tile_spec(37888,-339968)
        self.assertEqual(window_bounds(a)[2],window_bounds(b)[0])
        for spec in (a,b,tile_spec(-1024,0)):
            coords=feature(spec)['geometry']['coordinates'][0]
            lon=sum(p[0] for p in coords[:-1])/32;lat=sum(p[1] for p in coords[:-1])/32
            self.assertEqual(tile_at(lon,lat),spec)
        with self.assertRaises(ValueError):tile_spec(12,0)
    def test_grid_is_bounded_and_can_be_drawn_after_zoom(self):
        area=[200000,3000000,700000,3800000]
        grid,limited=visible_grid([[25,9],[35,20]],area)
        self.assertTrue(limited);self.assertEqual(grid['features'],[])
        grid,limited=visible_grid([[32.7,13.1],[32.85,13.3]],area)
        self.assertFalse(limited);self.assertGreater(len(grid['features']),0)
        self.assertLessEqual(len(grid['features']),400)

class MapServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.launcher=Mock()
        self.viewer=Mock()
        self.a=MapAssistant(JobStore(self.root/'store'),engine_commit='a'*40,launcher=self.launcher,viewer=self.viewer)
        self.archive=self.root/'old.zip'
        with zipfile.ZipFile(self.archive,'w') as out:
            for name,data in bundle_files().items():out.writestr('run/'+name,data)
    def test_identical_queued_request_does_not_create_another_preview(self):
        draft=self.a.prepare_mapping();self.a.confirm(draft['draft_id'])
        response=self.a.prepare_mapping()
        self.assertEqual(response['state'],'queued');self.assertIsNone(self.a.pending)
        self.launcher.assert_called_once();self.assertEqual(len(self.a.store.list(kind='mapping')),1)
    def test_existing_completed_map_is_reused(self):
        result=self.a.import_archive(self.archive);request=result['request']
        self.a.profile={k:v for k,v in request.items() if k not in {'request_id','schema_version','mode'}}
        self.a.profile['project']='example-project'
        response=self.a.prepare_mapping()
        self.assertEqual(response['job_id'],result['job_id']);self.assertIsNone(self.a.pending)
        self.launcher.assert_not_called()
    def test_selected_tile_needs_review_and_change_invalidates_it(self):
        result=self.a.import_archive(self.archive);mid=result['job_id']
        self.assertEqual(self.a.prepare_pilot()['type'],'help')
        spec=tile_spec(36864,-339968)
        artifact=result['outputs'][0]['artifact_id']
        self.viewer.plan.return_value=(artifact,{'spec':spec,'selection':'map_grid'})
        self.a.choose_tile(spec,mid);preview=self.a.prepare_pilot()
        self.assertEqual(preview['settings']['plan']['spec'],spec)
        self.assertFalse(self.a.store.list(kind='export'))
        self.a.choose_tile(tile_spec(37888,-339968),mid)
        with self.assertRaises(ValueError):self.a.confirm(preview['draft_id'])
        self.launcher.assert_not_called()
    def test_legend_help_and_status_use_grounded_tools(self):
        self.assertIn('Cultivated irrigated',self.a.say('What do the colours mean?')['message'])
        self.assertIn('Connect Google',self.a.say('What should I do next?')['message'])
        self.a.import_archive(self.archive)
        with patch.object(self.a,'refresh',return_value={'state':'running'}) as check:
            self.assertEqual(self.a.say('Is my map ready?')['state'],'running');check.assert_called_once()
        self.assertFalse(self.a.store.list(kind='export'))

    def test_selected_tile_confirmation_and_backup_preserve_scope(self):
        result=self.a.import_archive(self.archive);mid=result['job_id']
        spec=tile_spec(36864,-339968)
        self.viewer.plan.return_value=(result['outputs'][0]['artifact_id'],{'spec':spec,'selection':'map_grid'})
        self.a.choose_tile(spec,mid);draft=self.a.prepare_pilot()
        def finish(store,identifier):
            return store.update(store.get(identifier),state='completed',remote_state='SUCCEEDED',destination_uris=['https://drive.google.com/#folders/fixture'])
        with patch('libya_landcover.assistant.submit_export',side_effect=finish) as submit:
            response=self.a.confirm(draft['draft_id'])
            with self.assertRaises(ValueError):self.a.confirm(draft['draft_id'])
            submit.assert_called_once()
        self.assertEqual(response['coverage'],'selected_tile_only')
        backup=self.a.save_backup(self.root/'tile.zip')
        other=MapAssistant(JobStore(self.root/'recovered'),engine_commit='a'*40)
        restored=other.import_archive(backup)
        self.assertEqual(restored['coverage'],'selected_tile_only')
        self.assertEqual(restored['spec'],spec)
        self.assertEqual(restored['source'],'uploaded_archive_snapshot')
        self.assertEqual(restored['destination_uris'],response['destination_uris'])

@unittest.skipUnless(HAS_MAP,'Install [map]; package CI requires it')
class MapUiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from libya_landcover.map_ui import MapUI
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=JobStore(Path(self.tmp.name)/'store');self.viewer=Mock()
        self.a=MapAssistant(self.store,engine_commit='a'*40,viewer=self.viewer,launcher=Mock())
        archive=Path(self.tmp.name)/'old.zip'
        with zipfile.ZipFile(archive,'w') as out:
            for name,data in bundle_files().items():out.writestr('run/'+name,data)
        self.a.import_archive(archive);self.mid=self.a.mapping_id()
        self.viewer.open.return_value={'mapping_id':self.mid,'request':dict(TRIPOLI),'artifact_id':'unused',
            'url':'https://earthengine.googleapis.com/test/{z}/{x}/{y}',
            'bounds':[[32.6,13.0],[33,13.6]],'area_xy':[300000,3500000,450000,3700000],
            'outline':{'type':'Feature','properties':{},'geometry':{'type':'Polygon','coordinates':[[[13,32.6],[13.6,32.6],[13.6,33],[13,33],[13,32.6]]]}}}
        self.ui=MapUI(self.a,connect=Mock(),auto_poll=False);self.addCleanup(self.ui.close)
    async def test_open_map_choose_tile_and_review_in_one_ui(self):
        self.ui.connection.click()
        await asyncio.sleep(.02)
        self.assertIsNotNone(self.ui.raster)
        self.assertIn('Land-cover classes',self.ui.legend.value)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.assertIsNotNone(self.a.tile);self.assertFalse(self.ui.tile_action.disabled)
        artifact=self.a.describe()['outputs'][0]['artifact_id']
        self.viewer.plan.return_value=(artifact,{'spec':self.a.tile['spec']})
        self.ui.tile_action.click()
        self.assertIn('Download this selected tile',self.ui.preview.value)
        self.assertFalse(self.store.list(kind='export'))
        self.assertEqual(self.ui.refresh.layout.display,'')
    async def test_auto_poll_never_submits_and_stops_on_close(self):
        from libya_landcover.pilot import create_pilot
        result=self.a.describe();spec=tile_spec(36864,-339968)
        job=create_pilot(self.store,self.mid,result['outputs'][0]['artifact_id'],{'spec':spec})
        self.store.update(job,state='running',operation_name='projects/example-project/operations/a')
        self.a.selected=job['job_id'];self.ui.live_ready=True;self.ui.poll_seconds=.01
        def finish(store,identifier):return store.update(store.get(identifier),state='completed',destination_uris=['https://drive.google.com/#folders/fixture'])
        with patch('libya_landcover.map_ui.poll_export',side_effect=finish) as poll,patch('libya_landcover.assistant.submit_export') as submit:
            self.ui._poll_task=asyncio.create_task(self.ui._poll_loop());await asyncio.sleep(.08)
            self.assertIn('fixture',self.ui.progress.value);submit.assert_not_called();poll.assert_called_once()
            self.ui.close();await asyncio.sleep(.03);poll.assert_called_once()

    async def test_errors_are_visible_outside_chat_and_existing_map_reopens(self):
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui.new.click()
        self.assertIsNone(self.ui.map_data)
        self.ui._action(lambda:self.a.describe(self.mid));await asyncio.sleep(.02)
        self.assertIsNotNone(self.ui.raster)
        self.assertEqual(self.viewer.open.call_count,2)
        self.ui._action(lambda:(_ for _ in ()).throw(ValueError('Tile is outside the study area')))
        self.assertIn('outside the study area',self.ui.notice.value)
        self.assertIsNone(self.ui.chat.selected_index)

    async def test_display_failure_preserves_job_and_exposes_server_diagnostic(self):
        from libya_landcover.map_view import MapDisplayError
        self.viewer.open.side_effect=MapDisplayError('request_land_cover_layer',RuntimeError('User memory limit exceeded. https://example.test/?access_token=secret'))
        self.ui.connection.click();await asyncio.sleep(.02)
        self.assertIsNone(self.ui.map_data)
        self.assertEqual(self.store.get(self.mid)['state'],'completed')
        self.assertIn('User memory limit exceeded',self.ui.notice.value)
        self.assertIn('request_land_cover_layer',self.ui.notice.value)
        self.assertNotIn('secret',self.ui.notice.value)
        self.assertNotIn('Connect Google and open',self.ui.progress.value)
        self.assertIn('Open your prepared map',self.ui.step.value)
        self.assertIn('<b>2. Prepare map</b>',self.ui.flow.value)
        self.ui._save(False)
        diagnostic=json.loads((self.store.root/'landcover-display-error.json').read_text())
        self.assertEqual(diagnostic['selected_job_id'],self.mid)
        self.ui._ensure_map();await asyncio.sleep(.02)
        self.viewer.open.assert_called_once()
        self.a.launcher.assert_not_called()
        self.assertFalse(self.store.list(kind='export'))
        self.viewer.open.side_effect=None
        self.ui.open_button.click();await asyncio.sleep(.02)
        self.assertIsNotNone(self.ui.raster)
        self.assertIsNone(self.ui.last_error)
        self.assertEqual(self.ui.notice.value,'')
        self.assertIn('<b>3. Explore & download</b>',self.ui.flow.value)


from test_ee_graphs import ee, ApiTestCase

@unittest.skipIf(ee is None, 'Requires pinned EE client')
class MapBackendGraphTests(ApiTestCase):
    def setUp(self):
        self.network=patch('socket.socket.connect',side_effect=AssertionError('No network'))
        self.network.start();self.addCleanup(self.network.stop)
        original=ee.data._install_cloud_api_resource
        self.addCleanup(setattr,ee.data,'_install_cloud_api_resource',original)
        super().setUp()

    def test_full_map_and_selected_export_restore_identical_retained_graph(self):
        import hashlib
        from types import SimpleNamespace
        from uuid import uuid4
        from libya_landcover.jobs import import_bundle
        from libya_landcover.exports import EarthEngineBackend,enqueue_export
        files=bundle_files();graph=ee.Image.constant(4).rename('lc').serialize().encode()
        index=json.loads(files['graphs/index.json'])
        for identifier,record in index['artifacts'].items():
            record['sha256']=hashlib.sha256(graph).hexdigest()
            files['graphs/'+identifier+'.json']=graph
        files['graphs/index.json']=json.dumps(index).encode()
        with tempfile.TemporaryDirectory() as folder:
            store=JobStore(Path(folder)/'store');archive=Path(folder)/'bundle.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for name,data in files.items():z.writestr('run/'+name,data)
            source=import_bundle(store,archive);backend=MapBackend(store)
            geometry={'outline':[[[13,32],[14,32],[14,33],[13,33],[13,32]]],
                'outline_type':'Polygon','wgs_bounds':[[[13,32],[14,32],[14,33],[13,33],[13,32]]],
                'utm_bounds':[[[300000,3500000],[410000,3500000],[410000,3650000],[300000,3650000],[300000,3500000]]]}
            with patch.object(ee,'Initialize'), patch.object(ee.data,'computeValue',return_value=geometry) as compute, \
                 patch.object(ee.Image,'getMapId',autospec=True,return_value={'tile_fetcher':SimpleNamespace(url_format='https://example.test/{z}/{x}/{y}')}) as mapid:
                view=backend.open(source['job_id'])
            self.assertEqual(view['bounds'],[[32,13],[33,14]])
            self.assertEqual(mapid.call_args.args[1],{'min':1,'max':12,'palette':PALETTE})
            expression=mapid.call_args.args[0].serialize()
            self.assertIn('Image.clip',expression)
            self.assertIn(view['request']['aoi_asset'],expression)
            self.assertNotIn('GeometryConstructors.Rectangle',expression)
            self.assertIn('Geometry.bounds',compute.call_args.args[0].serialize())
            from libya_landcover.map_view import MapDisplayError
            with patch.object(ee,'Initialize'), patch.object(ee.Image,'getMapId',side_effect=RuntimeError('Test layer error')):
                with self.assertRaises(MapDisplayError) as failure:backend.open(source['job_id'])
            self.assertEqual(failure.exception.stage,'request_land_cover_layer')
            self.assertEqual(failure.exception.detail,'Test layer error')
            with patch.object(ee,'Initialize'), patch.object(ee.Image,'getMapId',return_value={'tile_fetcher':SimpleNamespace(url_format='unused')}), patch.object(ee.data,'computeValue',side_effect=RuntimeError('Test geometry error')):
                with self.assertRaises(MapDisplayError) as failure:backend.open(source['job_id'])
            self.assertEqual(failure.exception.stage,'read_study_area_boundary')
            spec=tile_spec(36864,-339968)
            with patch.object(ee,'Initialize'),patch.object(ee.data,'computeValue',return_value=100) as compute:
                artifact,plan=backend.plan(source['job_id'],spec)
            self.assertIn('Geometry.intersection',compute.call_args.args[0].serialize())
            self.assertEqual(plan['spec'],spec)
            with patch.object(ee,'Initialize'),patch.object(ee.data,'computeValue',return_value=0):
                with self.assertRaisesRegex(ValueError,'outside'):backend.plan(source['job_id'],spec)
            job=enqueue_export(store,source['job_id'],artifact,spec,request_id=str(uuid4()))
            export=object.__new__(EarthEngineBackend);export.ee=ee
            with patch.object(ee.batch.Export.image,'toDrive',wraps=ee.batch.Export.image.toDrive) as drive:
                payload=export.prepare(store,job)
            self.assertEqual(drive.call_args.kwargs['crsTransform'],[10,0,0,0,-10,0])
            expected=ee.Geometry.Rectangle(window_bounds(spec),proj='EPSG:32633',geodesic=False)
            self.assertEqual(drive.call_args.kwargs['region'].serialize(),expected.serialize())
            self.assertEqual(payload['maxPixels']['value'],'1048576')
            self.assertEqual(payload['fileExportOptions']['geoTiffOptions']['noData']['floatValue'],0)
            self.assertEqual((store.folder(source['job_id'])/'bundle/graphs'/index['artifacts'][artifact]['file']).read_bytes(),graph)
