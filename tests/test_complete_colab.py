"""Complete Colab startup with real widgets and mocked installation/inference/Google."""
import ast
import asyncio
import gc
import json
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / 'python/Libya_Land_Cover_Assistant.ipynb'
SCRIPT = r'''
import json, sys, tempfile, types, zipfile
from pathlib import Path
from unittest.mock import Mock, patch
import libya_landcover
from libya_landcover.job_store import JobStore
from libya_landcover.map_assistant import MapAssistant
from libya_landcover.map_ui import MapUI
from libya_landcover.local_language import LocalParser
sys.path.insert(0,'tests')
from test_jobs import bundle_files

scenario=sys.argv[1]
notebook=json.loads(Path('python/Libya_Land_Cover_Assistant.ipynb').read_text())
source=''.join(next(c for c in notebook['cells'] if c['cell_type']=='code')['source'])
colab=types.ModuleType('google.colab');colab.files=Mock();colab.output=Mock()
generator=Mock(side_effect=AssertionError('No inference during startup'))
parser=LocalParser(generator,device='test')
install=Mock(); load=Mock(return_value=parser)
ns={'__name__':'__main__'}
with tempfile.TemporaryDirectory() as folder:
    previous=None
    if scenario in {'closed','helper_closed','reopen'}:
        store=JobStore(Path(folder)/'assistant-store')
        previous_assistant=MapAssistant(store,engine_commit='a'*40,parser=parser,launcher=Mock())
        archive=Path(folder)/'saved.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for name,data in bundle_files().items():z.writestr('run/'+name,data)
        previous_assistant.import_archive(archive)
        previous=MapUI(previous_assistant,connect=Mock(),download=Mock(),auto_poll=False)
        previous.message.value='Keep this message'
        records=store.list()
        ns.update(ui=previous,assistant=previous_assistant,local_parser=parser)
        if scenario in {'closed','helper_closed'}:previous.close()
    if scenario.startswith('helper'):
        source=Path('python/update_accuracy.py').read_text()
    starter=Path('python/start_assistant.py').read_text().replace('/content/',folder+'/').encode()
    with patch.dict(sys.modules,{'google.colab':colab}), \
         patch('IPython.display.display',return_value=Mock()),patch('IPython.display.clear_output'), \
         patch('subprocess.run',install),patch('libya_landcover.local_language.LocalParser.load',load), \
         patch('importlib.metadata.version',side_effect=lambda name:'2.6.0' if name=='torch' else '0.12.0'), \
         patch('urllib.request.urlopen',return_value=__import__('io').BytesIO(starter)) as fetch, \
         patch('socket.socket.connect',side_effect=AssertionError('No network')), \
         patch('google.auth.default',side_effect=AssertionError('No credentials')), \
         patch('libya_landcover.map_view.MapBackend.open',side_effect=AssertionError('No map request')):
        if scenario=='fresh':
            # Remove the root after mocks resolve their targets: startup sees no
            # imported package, ui, assistant or previous uploaded backup.
            del sys.modules['libya_landcover']
        exec(source.replace('/content/',folder+'/'),ns)
        ui=ns['ui'];a=ns['assistant']
        assert ui.assistant is a and not ui._closed
        assert ui.year.description=='Target year' and ui.fallback_year.description=='Fallback year'
        assert ui.year.value==2024 and ui.fallback_year.value==2023
        assert 2025 in ui.year.options and 2025 in ui.fallback_year.options
        assert ui.accuracy_button.description=='Model accuracy'
        assert ui.explain_accuracy_button.description=='Explain accuracy'
        assert ui.tile_action.description=='Create tile download'
        assert 'Land-cover classes' in ui.legend.value
        assert ui.chat in ui.widget.children and ui.map in ui.map_slot.children
        assert ui.backup is not None and ui.restore is not None and ui.downloads is not None
        assert a.parser._generate is generator
        if scenario=='fresh':install.assert_called_once()
        else:install.assert_not_called()
        if scenario.startswith('helper'):
            fetch.assert_called_once()
            assert '/'+ns['SERVICE_COMMIT']+'/python/start_assistant.py' in fetch.call_args.args[0]
            assert ns['accuracy_update_task'] is ui  # no orphan background task
        else:fetch.assert_not_called()
        if previous is not None:
            assert a.store.list()==records
            previous_assistant.launcher.assert_not_called()
        if scenario=='reopen':
            assert ui is previous and a is previous_assistant
            assert ui.message.value=='Keep this message'
            callback=ui._browser_callback
            exec(source.replace('/content/',folder+'/'),ns)
            assert ns['ui'] is ui and ns['assistant'] is a
            assert ui._browser_callback!=callback
            colab.output.unregister_callback.assert_called_with(callback[1])
            load.assert_not_called()
            assert a.store.list()==records
        elif previous is not None:
            assert ui is not previous and a.selected==previous_assistant.selected
        else:
            assert a.store.list()==[]
            assert not ui.live_ready
        generator.assert_not_called()
        colab.files.download.assert_not_called()
        ui.close()
print('passed',scenario)
'''


class CompleteColabTests(unittest.TestCase):
    def scenario(self, name):
        result = subprocess.run([sys.executable, '-c', SCRIPT, name], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fresh_notebook_opens_all_features_without_an_old_ui(self): self.scenario('fresh')
    def test_installed_package_with_no_ui_opens_normally(self): self.scenario('loaded_without_ui')
    def test_closed_ui_is_replaced_and_saved_work_retained(self): self.scenario('closed')
    def test_reopening_reuses_workspace_and_replaces_one_callback(self): self.scenario('reopen')
    def test_legacy_update_without_ui_opens_complete_app(self): self.scenario('helper_empty')
    def test_legacy_update_with_closed_ui_opens_complete_app(self): self.scenario('helper_closed')

    def test_both_notebooks_embed_same_complete_pinned_starter(self):
        current = json.loads(NOTEBOOK.read_text())
        legacy = json.loads((ROOT / 'python/08_wp08_map_workspace.ipynb').read_text())
        self.assertEqual(current, legacy)
        cells = [c for c in current['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(cells), 1)
        source = ''.join(cells[0]['source'])
        compile(source, str(NOTEBOOK), 'exec')
        self.assertTrue(source.endswith((ROOT / 'python/start_assistant.py').read_text()))
        self.assertFalse(cells[0]['outputs'])
        self.assertIsNone(cells[0]['execution_count'])
        self.assertNotIn('update_accuracy.py', source)
        self.assertNotIn('files.upload(', source)
        pin = next(n.value.value for n in ast.parse(source).body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'SERVICE_COMMIT' for t in n.targets))
        self.assertRegex(pin, r'^[0-9a-f]{40}$')
        updater = runpy.run_path(str(ROOT / 'python/update_accuracy.py'))
        self.assertEqual(updater['SERVICE_COMMIT'], pin)


class CompatibilityErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_background_failure_is_consumed_and_displayed(self):
        scope = runpy.run_path(str(ROOT / 'python/update_accuracy.py'))['open_or_update'].__globals__
        loop = asyncio.get_running_loop()
        errors = []
        prior_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _, context: errors.append(context))
        try:
            with patch.dict(scope, ui=Mock(_closed=False),
                            update_accuracy=AsyncMock(side_effect=RuntimeError('offline install failed')),
                            show_update_error=Mock()):
                task = scope['open_or_update']()
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                self.assertTrue(task.done())
                scope['show_update_error'].assert_called_once()
                del task
                gc.collect()
                await asyncio.sleep(0)
                self.assertEqual(errors, [])
        finally:
            loop.set_exception_handler(prior_handler)

    async def test_failed_start_download_is_shown_without_background_exception(self):
        scope = runpy.run_path(str(ROOT / 'python/update_accuracy.py'))['open_or_update'].__globals__
        with patch.dict(scope, ui=None, show_update_error=Mock()), \
             patch('urllib.request.urlopen', side_effect=OSError('No connection')):
            self.assertIsNone(scope['open_or_update']())
            scope['show_update_error'].assert_called_once()

    async def test_awaited_legacy_entry_can_start_without_an_old_ui(self):
        scope = runpy.run_path(str(ROOT / 'python/update_accuracy.py'))['update_accuracy'].__globals__
        ui = object()
        with patch.dict(scope, open_complete_assistant=Mock(return_value=ui)):
            self.assertIs(await scope['update_accuracy'](None), ui)


if __name__ == '__main__': unittest.main()
