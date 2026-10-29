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
    def test_initial_view_contains_extent_without_browser_round_trip(self):
        import math
        from libya_landcover.notebook_map import view_for_bounds
        for bounds in ([[32.6,13],[33,13.6]],[[25,9],[35,24]],[[70,10],[78,20]]):
            center,zoom=view_for_bounds(bounds)
            def point(lat,lon):
                return ((lon+180)/360*256*2**zoom,
                        (1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*256*2**zoom)
            cx,cy=point(*center)
            for lat,lon in bounds:
                x,y=point(lat,lon)
                self.assertLessEqual(abs(x-cx),320)
                self.assertLessEqual(abs(y-cy),220)
        with self.assertRaises(ValueError):view_for_bounds([[None,13],[33,14]])

    def test_browser_null_bounds_reproduce_without_ee_and_safe_map_recovers(self):
        from ipyleaflet import Map
        from traitlets import TraitError
        from libya_landcover.notebook_map import NotebookMap,valid_bounds
        old=Map();self.addCleanup(old.close)
        with self.assertRaisesRegex(TraitError,"'east'.*NoneType"):
            old.set_state({'east':None})
        current=NotebookMap();self.addCleanup(current.close)
        good={'south':32.6,'north':33.0,'west':13.0,'east':13.6}
        current.set_state(good)
        self.assertTrue(valid_bounds(current.bounds))
        before=current.bounds
        for missing in (None,float('nan'),float('inf'),float('-inf')):
            # Match the no-view JS frame; do not mix its south/north with old bounds.
            current.set_state({'south':90,'north':-90,'west':missing,'east':missing,'zoom':7})
            self.assertEqual(current.bounds,before)
            self.assertEqual(current.zoom,7)
        current.set_state({'left':10,'right':100,'top':20,'bottom':200})
        pixels=current.pixel_bounds
        current.set_state({'left':None,'right':None,'top':None,'bottom':None})
        self.assertEqual(current.pixel_bounds,pixels)
        current.set_state({**good,'east':14.0})
        self.assertEqual(current.bounds,((32.6,13.0),(33.0,14.0)))
        for invalid in (None,(),((None,13),(33,14)),((33,14),(32,13))):
            self.assertFalse(valid_bounds(invalid))

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
        from test_jobs import Backend
        self.network=patch('socket.socket.connect',side_effect=AssertionError('Offline test: network access prohibited'))
        self.network.start();self.addCleanup(self.network.stop)
        self.remote=Backend();self.remote.response={'metadata':{'state':'RUNNING'}}
        self.backend_patch=patch('libya_landcover.exports._backend',return_value=self.remote)
        self.backend_patch.start();self.addCleanup(self.backend_patch.stop)
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
        from ipyleaflet import TileLayer
        self.assertFalse([layer for layer in self.ui.map.layers if isinstance(layer,TileLayer)])
        self.ui.connection.click()
        await asyncio.sleep(.02)
        self.assertIsNotNone(self.ui.raster)
        self.assertIn('Land-cover classes',self.ui.legend.value)
        tiles=[layer for layer in self.ui.map.layers if isinstance(layer,TileLayer)]
        self.assertEqual(tiles,[self.ui.raster])
        self.assertEqual(tiles[0].url,self.viewer.open.return_value['url'])
        self.assertIn('Google Earth Engine',tiles[0].attribution)
        self.ui.open_button.click();await asyncio.sleep(.02)
        self.assertEqual([layer for layer in self.ui.map.layers if isinstance(layer,TileLayer)],[self.ui.raster])
        self.assertIn(self.ui.grid,self.ui.map.layers)
        self.assertIn(self.ui.outline,self.ui.map.layers)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.assertIsNotNone(self.a.tile);self.assertFalse(self.ui.tile_action.disabled)
        artifact=self.a.describe()['outputs'][0]['artifact_id']
        self.viewer.plan.return_value=(artifact,{'spec':self.a.tile['spec']})
        self.ui._action(self.a.prepare_pilot)
        self.assertIn('Download this selected tile',self.ui.preview.value)
        self.assertFalse(self.store.list(kind='export'))
        self.assertEqual(self.ui.refresh.layout.display,'')
    async def test_saved_map_to_tile_download_and_reopen_without_new_mapping(self):
        from test_jobs import Backend
        from libya_landcover.map_ui import MapUI
        backend=Backend()
        self.assertIn('Connect Google',self.ui.next_step.value)
        self.ui.connection.click();await asyncio.sleep(.02)
        self.assertIn('Wait for colours',self.ui.next_step.value)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        chosen=self.a.tile['spec']
        self.assertIn('Create tile download',self.ui.next_step.value)
        artifact=self.a.describe()['outputs'][0]['artifact_id']
        self.viewer.plan.return_value=(artifact,{'spec':chosen,'selection':'map_grid'})
        with patch('libya_landcover.exports._backend',return_value=backend):
            self.ui._action(self.a.prepare_pilot)
            self.assertEqual(self.ui.mapping_review.children,())
            self.assertEqual(self.ui.download_review.children,(self.ui.review_box,))
            self.assertIn('above the map',self.ui.next_step.value)
            self.assertEqual(backend.starts,[])
            self.ui.confirm.click()
            identifier=self.a.selected
            self.assertEqual(self.store.get(identifier)['state'],'submitted')
            self.assertEqual(len(backend.starts),1)
            self.assertIn('do not submit it again',self.ui.next_step.value)
            self.assertEqual(self.ui.download_review.children,())
            backend.response={'metadata':{'state':'RUNNING'}}
            self.ui.refresh.click()
            self.assertEqual(self.store.get(identifier)['state'],'running')
            backend.response={'done':True,'metadata':{'state':'SUCCEEDED','destinationUris':['https://drive.google.com/drive/folders/test-output']}}
            self.ui.refresh.click()
            self.assertEqual(self.store.get(identifier)['state'],'completed')
            self.assertIn('Tile download',self.ui.progress.value)
            self.assertIn('test-output',self.ui.progress.value)
            self.assertIn('Save work for later',self.ui.next_step.value)
            # Re-reviewing the same tile reuses its operation, never starts another.
            self.ui.tile_action.click()
            self.assertEqual(self.a.selected,identifier)
            self.assertEqual(len(backend.starts),1)
        self.a.launcher.assert_not_called()
        self.assertIsNotNone(self.ui.raster)
        self.ui.backup.click()
        archive=self.store.root/'landcover-workspace.zip'
        self.assertTrue(archive.exists())
        restored=MapAssistant(JobStore(Path(self.tmp.name)/'next-session'),engine_commit='a'*40,viewer=self.viewer,launcher=Mock())
        from libya_landcover.workspace import restore_workspace
        restore_workspace(restored,archive);result=restored.describe()
        self.assertEqual(result['coverage'],'selected_tile_only')
        self.assertEqual(result['spec'],chosen)
        reopened=MapUI(restored,connect=Mock(),auto_poll=False);self.addCleanup(reopened.close)
        self.assertIn('test-output',reopened.progress.value)
        self.assertIn('Save work for later',reopened.next_step.value)
        restored.launcher.assert_not_called()
        self.assertEqual(len(backend.starts),1)

    async def test_missing_drive_uri_shows_recorded_folder_without_fabricating_link(self):
        from libya_landcover.pilot import create_pilot
        result=self.a.describe()
        job=create_pilot(self.store,self.mid,result['outputs'][0]['artifact_id'],{'spec':tile_spec(36864,-339968)})
        self.store.update(job,state='completed',drive_folder='Recorded_Folder',destination_uris=[])
        self.a.selected=job['job_id'];self.ui.sync()
        self.assertIn('Recorded_Folder',self.ui.progress.value)
        self.assertIn('Find the folder',self.ui.next_step.value)
        self.assertNotIn('href=',self.ui.progress.value)

    async def test_status_widgets_share_one_snapshot_and_do_not_mix_running_with_completed(self):
        self.ui.connection.click();await asyncio.sleep(.02)
        stale={**self.store.get(self.mid),'state':'running'}
        with patch.object(self.ui,'_mapping',return_value=stale), patch.object(self.a,'describe',wraps=self.a.describe) as describe:
            self.ui.sync()
        describe.assert_called_once()
        self.assertIn('completed',self.ui.progress.value)
        self.assertNotIn('Wait while your map is prepared',self.ui.next_step.value)
        self.assertIn('<b>3. Explore & download</b>',self.ui.flow.value)
        self.assertFalse(self.ui.fit.disabled)
        self.assertEqual(self.ui.legend.layout.display,'')
        self.assertEqual(self.ui.raster.bounds,self.viewer.open.return_value['bounds'])
        self.assertTrue(self.ui.raster.no_wrap)

    async def test_display_check_only_on_click_keeps_map_and_exports_unchanged(self):
        self.assertTrue(self.ui.check_display.disabled)
        diagnostic={'state':'timeout','message':'A display tile timed out.', 'scope':'one_display_tile_from_colab'}
        with patch('libya_landcover.display_diagnostics.check_display_tile',return_value=diagnostic) as check:
            self.ui.connection.click();await asyncio.sleep(.02)
            self.ui.sync();check.assert_not_called()
            self.ui.check_display.click();check.assert_called_once()
            self.assertIn('timed out',self.ui.display_status.value)
            self.assertEqual(self.store.get(self.mid)['state'],'completed')
            self.assertFalse(self.store.list(kind='export'))
            self.a.launcher.assert_not_called()
            self.assertIsNotNone(self.ui.raster)
            self.assertFalse(self.ui.fit.disabled)
            saved=self.store.root/'landcover-display-check.json'
            self.assertEqual(json.loads(saved.read_text())['mapping_job_id'],self.mid)
            self.ui.download=Mock();self.ui._save(False)
            self.ui.download.assert_called_once_with(str(saved))

    async def test_restore_empty_view_keeps_selection_and_review_without_backend_calls(self):
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        selected=self.a.tile.copy()
        artifact=self.a.describe()['outputs'][0]['artifact_id']
        self.viewer.plan.return_value=(artifact,{'spec':selected['spec']})
        self.ui._action(self.a.prepare_pilot);pending=self.a.pending
        old_map=self.ui.map
        # Simulate a stale display with no layer views.
        old_map.layers=()
        self.viewer.reset_mock();self.a.launcher.reset_mock()
        self.ui.restore_display.click()
        self.assertIsNone(old_map.comm)
        self.assertIsNot(self.ui.map,old_map)
        self.assertEqual(self.a.tile,selected)
        self.assertEqual(self.a.pending,pending)
        self.assertEqual(self.ui.map.layers,(self.ui.raster,self.ui.outline,self.ui.grid,self.ui.highlight))
        self.assertTrue(self.ui.highlight.data['features'])
        self.assertTrue(self.ui.grid.data['features'])
        self.assertLess(self.ui.widget.children.index(self.ui.tile_action),self.ui.widget.children.index(self.ui.map_slot))
        self.assertFalse(self.ui.tile_action.disabled)
        self.viewer.open.assert_not_called();self.viewer.plan.assert_not_called()
        self.a.launcher.assert_not_called();self.assertFalse(self.store.list(kind='export'))

    async def test_in_place_repair_uses_same_assistant_and_store(self):
        from libya_landcover.map_ui import restore_live_workspace
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.viewer.plan.return_value=(self.a.describe()['outputs'][0]['artifact_id'],{'spec':self.a.tile['spec']})
        self.ui._action(self.a.prepare_pilot);pending=self.a.pending
        old_map=self.ui.map;tile=self.a.tile.copy();selected=self.a.selected
        self.viewer.reset_mock()
        with patch('IPython.display.display'):
            repaired=restore_live_workspace(self.ui)
        self.addCleanup(repaired.close)
        self.assertIs(repaired.assistant,self.a)
        self.assertIs(repaired.assistant.store,self.store)
        self.assertEqual(self.a.selected,selected);self.assertEqual(self.a.tile,tile)
        self.assertEqual(self.a.pending,pending)
        self.assertTrue(repaired.live_ready);self.assertFalse(repaired.tile_action.disabled)
        self.assertIsNone(old_map.comm);self.assertTrue(self.ui._closed)
        self.viewer.open.assert_not_called();self.a.launcher.assert_not_called()
        self.assertFalse(self.store.list(kind='export'))

    async def test_one_click_download_is_not_lost_during_poll_and_link_stays_visible(self):
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.viewer.plan.return_value=(self.a.describe()['outputs'][0]['artifact_id'],{'spec':self.a.tile['spec']})
        self.ui._polling=True
        self.ui.tile_action.click()
        self.ui._polling=False
        identifier=self.a.selected
        self.assertEqual(self.store.get(identifier)['state'],'submitted')
        self.assertEqual(len(self.remote.starts),1)
        self.assertIn('Waiting for Earth Engine',self.ui.downloads.value)
        self.ui.tile_action.click();self.assertEqual(len(self.remote.starts),1)
        self.a.selected=self.mid;self.ui.sync()
        self.remote.response={'done':True,'metadata':{'state':'SUCCEEDED','destinationUris':['https://drive.google.com/drive/folders/live-result']}}
        await self.ui._poll_once();self.ui.sync()
        self.assertIn('live-result',self.ui.downloads.value)
        self.assertEqual(self.a.selected,self.mid)
        self.a.launcher.assert_not_called()

    async def test_fresh_user_creates_map_once_without_second_review_button(self):
        from libya_landcover.map_ui import MapUI
        a=MapAssistant(JobStore(Path(self.tmp.name)/'new-user'),engine_commit='a'*40,viewer=self.viewer,launcher=Mock())
        ui=MapUI(a,connect=Mock(),auto_poll=False);self.addCleanup(ui.close)
        ui.connection.click()
        self.assertEqual(ui.prepare.description,'Create map')
        ui.prepare.click();identifier=a.selected
        self.assertEqual(a.store.get(identifier)['state'],'queued')
        self.assertIsNone(a.pending);a.launcher.assert_called_once()
        ui.prepare.click();a.launcher.assert_called_once()
        self.assertEqual(a.selected,identifier)

    async def test_failed_export_preparation_shows_reason_without_claiming_a_download(self):
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.viewer.plan.return_value=(self.a.describe()['outputs'][0]['artifact_id'],{'spec':self.a.tile['spec']})
        with patch.object(self.remote,'prepare',side_effect=RuntimeError('Export preparation unavailable')):
            self.ui.tile_action.click()
        self.assertIn('Export preparation unavailable',self.ui.downloads.value)
        self.assertNotIn('Open download in Google Drive',self.ui.downloads.value)
        self.assertFalse(self.remote.starts)

    async def test_poll_recovers_lost_submission_without_starting_again(self):
        from libya_landcover.exports import description
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.viewer.plan.return_value=(self.a.describe()['outputs'][0]['artifact_id'],{'spec':self.a.tile['spec']})
        self.remote.fail_start=True;self.ui.tile_action.click()
        job=self.store.get(self.a.selected)
        self.assertEqual(job['state'],'submission_unknown');self.assertIsNone(job['operation_name'])
        self.remote.operations=[{'name':'projects/example-project/operations/reconciled','metadata':{'state':'RUNNING','description':description(job)}}]
        await self.ui._poll_once();self.ui.sync()
        self.assertEqual(self.store.get(job['job_id'])['state'],'running')
        self.assertEqual(len(self.remote.starts),1)

    async def test_imported_running_export_checks_automatically_without_refresh_click(self):
        from libya_landcover.workspace import save_workspace,restore_workspace
        from libya_landcover.exports import description
        from libya_landcover.map_ui import MapUI
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.viewer.plan.return_value=(self.a.describe()['outputs'][0]['artifact_id'],{'spec':self.a.tile['spec']})
        self.ui.tile_action.click();job=self.store.get(self.a.selected)
        archive=save_workspace(self.a,self.store.root/'all.zip')
        restored=MapAssistant(JobStore(Path(self.tmp.name)/'restored-all'),engine_commit='a'*40,viewer=self.viewer,launcher=Mock())
        restore_workspace(restored,archive)
        ui=MapUI(restored,connect=Mock(),auto_poll=False);self.addCleanup(ui.close);ui.live_ready=True
        self.remote.response={'done':True,'metadata':{'state':'SUCCEEDED','description':description(job),'destinationUris':['https://drive.google.com/drive/folders/recovered-result']}}
        await ui._poll_once();ui.sync()
        self.assertIn('recovered-result',ui.downloads.value)
        self.assertEqual(restored.describe()['state'],'completed')
        self.assertEqual(len(self.remote.starts),1)

    async def test_upgrade_without_open_view_retains_work_and_connection_state(self):
        from libya_landcover.map_ui import restore_live_workspace
        with patch('IPython.display.display'):
            repaired=restore_live_workspace(self.ui)
        self.addCleanup(repaired.close)
        self.assertIs(repaired.assistant,self.a)
        self.assertFalse(repaired.live_ready)
        self.assertIsNotNone(repaired.map.comm)
        self.assertTrue(self.ui._closed)

    async def test_unified_updater_preserves_pending_review_history_and_all_job_ids(self):
        import runpy
        self.ui.connection.click();await asyncio.sleep(.02)
        self.ui.year.value=2023
        self.ui.message.value='Keep this unsent message'
        self.ui.map.center=(32.8,13.2);self.ui.map.zoom=10
        self.ui._map_click(type='click',coordinates=[32.8,13.2])
        self.viewer.plan.return_value=(self.a.describe()['outputs'][0]['artifact_id'],{'spec':self.a.tile['spec']})
        self.ui._action(self.a.prepare_pilot);pending=self.a.pending
        identifiers=[j['job_id'] for j in self.store.list()];history=list(self.ui.history)
        self.ui.download=Mock()
        update=runpy.run_path(str(ROOT/'python/update_workspace.py'))['update_current_workspace']
        with patch('subprocess.run',return_value=Mock(returncode=0)),patch('IPython.display.display'):
            repaired=await update(self.ui)
        self.addCleanup(repaired.close)
        self.assertEqual(self.a.pending,pending);self.assertEqual(repaired.history,history)
        self.assertEqual([j['job_id'] for j in self.store.list()],identifiers)
        self.assertTrue(repaired.live_ready);self.assertIs(repaired.assistant,self.a)
        self.assertEqual(repaired.year.value,2023)
        self.assertEqual(repaired.message.value,'Keep this unsent message')
        self.assertEqual(repaired.map.center,[32.8,13.2]);self.assertEqual(repaired.map.zoom,10)
        backup=self.store.root/'landcover-before-update.zip'
        self.ui.download.assert_called_once_with(str(backup))
        with zipfile.ZipFile(backup) as archive:self.assertIn('workspace.json',archive.namelist())
        self.assertFalse(self.remote.starts);self.a.launcher.assert_not_called()

    async def test_repair_cell_updates_display_only_in_existing_runtime(self):
        import runpy
        self.ui.connection.click();await asyncio.sleep(.02)
        old_guard=self.a.before_live
        helper=runpy.run_path(str(ROOT/'python/repair_map_display.py'))['repair_current_display']
        # Failed installation must leave the current UI usable.
        with patch('subprocess.run',return_value=Mock(returncode=1)):
            with self.assertRaisesRegex(RuntimeError,'could not install'):helper(self.ui)
        self.assertFalse(self.ui._closed);self.assertEqual(self.a.before_live,old_guard)
        self.viewer.reset_mock()
        with patch('subprocess.run',return_value=Mock(returncode=0)) as install, patch('IPython.display.display'):
            repaired=helper(self.ui)
        self.addCleanup(repaired.close)
        self.assertIn('--no-deps',install.call_args.args[0])
        self.assertIs(repaired.assistant,self.a);self.assertTrue(repaired.live_ready)
        self.assertIs(repaired.assistant.store,self.store)
        self.viewer.open.assert_not_called();self.a.launcher.assert_not_called()
        self.assertFalse(self.store.list(kind='export'))

    async def test_failed_preparation_exposes_reason_and_one_click_report_without_rerun(self):
        self.ui.connection.click();await asyncio.sleep(.02)
        draft=self.a.prepare_mapping();self.a.confirm(draft['draft_id'])
        job=self.store.get(self.a.selected)
        self.store.update(job,state='failed',error={'code':'MAPPING_FAILED','exit_code':3})
        folder=self.store.folder(job['job_id'])/'bundle';folder.mkdir(parents=True,exist_ok=True)
        (folder/'manifest.json').write_text(json.dumps({'bundle_state':'initialization_failed','error_type':'EEException',
            'failure_details':[{'error_type':'EEException','detail':'Project access denied https://example.test/?token=private'}],
            'extra':'DO_NOT_INCLUDE'}))
        self.ui.download=Mock();self.ui.sync()
        self.assertIn('Map preparation failed',self.ui.step.value)
        self.assertIn('Project access denied',self.ui.failure_panel.value)
        self.assertEqual(self.ui.map.layout.display,'none')
        self.assertIn('Download failure report',self.ui.next_step.value)
        self.assertEqual(self.ui.failure_report.layout.display,'')
        self.assertNotIn('private',self.ui.failure_panel.value)
        self.assertNotIn('DO_NOT_INCLUDE',self.ui.failure_panel.value)
        self.a.launcher.reset_mock();self.viewer.reset_mock()
        self.ui.failure_report.click()
        saved=self.store.root/'landcover-mapping-failure.json'
        self.ui.download.assert_called_once_with(str(saved))
        report=json.loads(saved.read_text())['result']
        self.assertEqual(report['job_id'],job['job_id'])
        self.assertEqual(report['runner_failure']['bundle_state'],'initialization_failed')
        self.assertNotIn('private',json.dumps(report))
        self.a.launcher.assert_not_called();self.viewer.open.assert_not_called()
        self.assertFalse(self.store.list(kind='export'))

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

    async def test_closed_workspace_closes_map_comm_and_null_view_does_not_affect_aoi(self):
        self.ui.connection.click();await asyncio.sleep(.02)
        actual_bounds=self.ui.map_data['bounds']
        self.ui.map.set_state({'east':None,'west':None,'south':90,'north':-90})
        self.ui._draw_grid()
        self.assertEqual(self.ui.map_data['bounds'],actual_bounds)
        self.assertTrue(self.ui.grid.data['features'])
        self.assertEqual(self.store.get(self.mid)['state'],'completed')
        self.a.launcher.assert_not_called()
        self.ui.close()
        self.assertIsNone(self.ui.map.comm)

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
            polygon={'type':'Polygon','coordinates':[[[13,32],[14,32],[14,33],[13,33],[13,32]]]}
            geometry={'wgs_bounds':[[[13,32],[14,32],[14,33],[13,33],[13,32]]],
                'utm_bounds':[[[300000,3500000],[410000,3500000],[410000,3650000],[300000,3650000],[300000,3500000]]]}
            with patch.object(ee,'Initialize'), patch.object(ee.data,'computeValue',side_effect=[polygon,geometry]) as compute, \
                 patch.object(ee.Image,'getMapId',autospec=True,return_value={'tile_fetcher':SimpleNamespace(url_format='https://example.test/{z}/{x}/{y}')}) as mapid:
                view=backend.open(source['job_id'])
            self.assertEqual(view['bounds'],[[32,13],[33,14]])
            self.assertEqual(mapid.call_args.args[1],{'min':1,'max':12,'palette':PALETTE})
            expression=mapid.call_args.args[0].serialize()
            self.assertIn('Image.clip',expression)
            self.assertIn(view['request']['aoi_asset'],expression)
            self.assertNotIn('GeometryConstructors.Rectangle',expression)
            self.assertIn('Geometry.bounds',compute.call_args.args[0].serialize())
            self.assertEqual(view['outline']['geometry'],polygon)
            outline_graph=compute.call_args_list[0].args[0].serialize()
            self.assertNotIn('Geometry.coordinates',outline_graph)
            self.assertIn('Geometry.simplify',outline_graph)
            self.assertIn('Geometry.transform',outline_graph)
            collection={'type':'GeometryCollection','geometries':[polygon,{'type':'GeometryCollection','geometries':[{'type':'Point','coordinates':[13.2,32.8]}]}]}
            with patch.object(ee,'Initialize'), patch.object(ee.data,'computeValue',side_effect=[collection,geometry]), \
                 patch.object(ee.Image,'getMapId',return_value={'tile_fetcher':SimpleNamespace(url_format='https://example.test/{z}/{x}/{y}')}):
                collection_view=backend.open(source['job_id'])
            self.assertEqual(collection_view['outline']['geometry'],collection)
            self.assertNotIn('coordinates',collection_view['outline']['geometry'])
            self.assertEqual(collection_view['bounds'],view['bounds'])
            if HAS_MAP:
                from ipyleaflet import GeoJSON
                layer=GeoJSON(data=collection_view['outline'])
                self.assertEqual(layer.data['geometry'],collection)
                layer.close()
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
