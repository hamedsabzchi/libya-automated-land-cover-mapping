"""Exercise the actual in-place updater in isolation; installation and all I/O are mocked."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r'''
import asyncio, json, runpy, sys, tempfile, types, zipfile
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, 'tests')
from test_jobs import bundle_files
from libya_landcover.job_store import JobStore
from libya_landcover.map_assistant import MapAssistant
from libya_landcover.map_ui import MapUI
from libya_landcover.local_language import LocalParser
from libya_landcover.map_view import tile_spec
from libya_landcover.pilot import create_pilot
import libya_landcover
from ipyleaflet import TileLayer
from ipywidgets import Accordion, VBox, HBox

async def exercise():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        archive = root/'old.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name,data in bundle_files().items(): z.writestr('run/'+name,data)
        legacy = type('MapAssistant',(MapAssistant,),{'__module__':'libya_landcover.map_assistant',
                      'say':lambda self,text:{'type':'help','message':'old chat'}})
        generate = Mock(side_effect=AssertionError('No model inference'))
        a = legacy(JobStore(root/'store'),engine_commit='a'*40,parser=LocalParser(generate),launcher=Mock())
        mapped = a.import_archive(archive); mid = a.selected
        job = create_pilot(a.store,mid,mapped['outputs'][0]['artifact_id'],{'spec':tile_spec(36864,-339968)})
        job = a.store.update(job,state='completed',destination_uris=['https://drive.google.com/drive/folders/keep'])
        a.selected = job['job_id']; a.tile = {'mapping_id':mid,'spec':job['inputs']['spec']}
        ui = MapUI(a,connect=Mock(),download=Mock(),auto_poll=False)
        ui.live_ready = True
        ui.raster = TileLayer(url='https://example.invalid/saved/{z}/{x}/{y}')
        ui.map.add(ui.raster); ui.map_data = {'mapping_id':mid,'url':ui.raster.url}
        a._draft({'action':'pilot','mapping_job_id':mid,'artifact_id':job['inputs']['artifact_id'],'plan':{'spec':job['inputs']['spec']}})
        ui.add({'message':'retain conversation'})
        ui.message.value = 'keep unfinished message'
        old_chat = ui.chat; ui.chat = Accordion(children=[VBox(old_chat.children)],selected_index=None)
        ui.widget.children = tuple(ui.chat if w is old_chat else w for w in ui.widget.children)
        # Simulate 0.10.1, which had no fallback widget.
        ui.fallback_year.close(); del ui.fallback_year
        ui.choices.children=(ui.choices.children[0],HBox([ui.region,ui.year]),ui.prepare)
        libya_landcover.__version__ = '0.10.1'
        original = (ui.map, ui.map.comm, ui.raster, ui.raster.url, ui.map.layers, ui.grid, ui.highlight,
                    ui.map_slot, ui.tile_action, ui.downloads, a.store, a.before_live, a.launcher,
                    a.selected, a.pending, a.tile, a.store.list(), list(ui.history), ui.message.value)
        install = Mock(return_value=types.SimpleNamespace(returncode=1 if sys.argv[1]=='failure' else 0))
        module = runpy.run_path('python/update_accuracy.py')
        display = Mock()
        if sys.argv[1] == 'notebook':
            # The Start assistant upgrade path must retain this exact workspace too.
            code = ''.join(c['source'] and ''.join(c['source']) for c in json.loads(Path('python/08_wp08_map_workspace.ipynb').read_text())['cells'] if c['cell_type']=='code')
            colab=types.ModuleType('google.colab'); colab.output=Mock(); colab.files=Mock()
            ns={'ui':ui,'assistant':a,'local_parser':a.parser}
            with patch.dict(sys.modules,{'google.colab':colab}), patch('IPython.display.display',display), \
                 patch('IPython.display.clear_output'), patch('subprocess.run',install), \
                 patch('importlib.metadata.version',side_effect=lambda name:'2.6.0' if name=='torch' else '0.11.0'):
                exec(code.replace('/content/',folder+'/'),ns)
            assert ns['ui'] is ui and ns['assistant'] is a
        else:
            with patch('subprocess.run',install), patch('IPython.display.display',display):
                try:
                    returned = await module['update_accuracy'](ui)
                    assert sys.argv[1]!='failure' and returned is ui
                except RuntimeError:
                    assert sys.argv[1]=='failure'
            assert (a.store.root/'landcover-before-accuracy.zip').exists()
            ui.download.assert_called_once()
        assert original == (ui.map, ui.map.comm, ui.raster, ui.raster.url, ui.map.layers, ui.grid, ui.highlight,
                            ui.map_slot, ui.tile_action, ui.downloads, a.store, a.before_live, a.launcher,
                            a.selected, a.pending, a.tile, a.store.list(), list(ui.history), ui.message.value)
        assert not ui._busy and not ui._closed
        if sys.argv[1]!='failure':
            assert ui.fallback_year.value==2023 and ui.year.value==2024
            assert ui.choices.layout.display==''
            assert a.say('classification accuracy')['metrics']['overall']==1.0  # Offline fixture ONLY.
            assert a.parser._generate is generate
            ui.accuracy_button.click()
            assert 'Saved model accuracy' in ui.transcript.value
            ui.explain_accuracy_button.click()
            assert 'Accuracy explained' in ui.transcript.value
            ui.message.value='What does producer accuracy mean?'; ui.send.click()
            assert 'reference row total' in ui.transcript.value
            assert original[14]==a.pending and original[16]==a.store.list()
        else: assert a.say('classification accuracy')['message']=='old chat'
        a.launcher.assert_not_called(); generate.assert_not_called()
        ui.close()

with patch('socket.socket.connect',side_effect=AssertionError('Offline')), \
     patch('google.auth.default',side_effect=AssertionError('No credentials')), \
     patch('libya_landcover.map_ui.poll_export',side_effect=AssertionError('No polling')), \
     patch('libya_landcover.map_view.MapBackend.open',side_effect=AssertionError('No map request')):
    asyncio.run(exercise())
print('passed',sys.argv[1])
'''


class AccuracyUpgradeTests(unittest.TestCase):
    def scenario(self, name):
        result = subprocess.run([sys.executable, '-c', SCRIPT, name], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_current_session_keeps_map_downloads_and_pending_review(self): self.scenario('success')
    def test_failed_install_retains_work_and_backup(self): self.scenario('failure')
    def test_notebook_upgrade_preserves_existing_map_widgets(self): self.scenario('notebook')
