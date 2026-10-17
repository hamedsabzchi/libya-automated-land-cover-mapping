"""Isolated old-package upgrade; pip, Colab, auth and inference are mocked."""
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r'''
import json, sys, tempfile, types, subprocess
from pathlib import Path
from unittest.mock import Mock, patch
import libya_landcover
from libya_landcover.assistant import Assistant
from libya_landcover.job_store import JobStore
from libya_landcover.local_language import LocalParser
from ipyleaflet import Map, GeoJSON
scenario = sys.argv[1]
nb = json.loads(Path('python/08_wp08_map_workspace.ipynb').read_text())
source = ''.join(next(c for c in nb['cells'] if c['cell_type']=='code')['source'])
colab = types.ModuleType('google.colab'); colab.files = Mock(); colab.output = Mock()
with tempfile.TemporaryDirectory() as folder:
    old = Assistant(JobStore(Path(folder)/'assistant-store'), engine_commit='a'*40)
    old.prepare_mapping(); draft = old.pending
    keep = old.store.root/'saved-work.txt'; keep.write_text('preserve me')
    widget = Mock()
    old_ui = types.SimpleNamespace(widget=widget, map=Mock())
    detached_map=Map(layers=(GeoJSON(name='Download grid'),GeoJSON(name='Selected download tile')))
    unrelated_map=Map()
    parser = LocalParser(lambda _: '{}', device='test')
    if scenario == 'active': old.store.create('mapping', 'existing', {}, state='running')
    libya_landcover.__version__ = '0.8.1'
    ns = {'assistant':old, 'ui':old_ui, 'local_parser':parser}
    commands = Mock(side_effect=subprocess.CalledProcessError(1,['pip'])) if scenario=='install_failure' else Mock()
    messages = []
    def display(value, **kwargs):
        messages.append(getattr(value,'data','widget')); return Mock()
    with patch.dict(sys.modules,{'google.colab':colab}), \
         patch('IPython.display.display',side_effect=display), patch('IPython.display.clear_output'), \
         patch('subprocess.run',commands), \
         patch('importlib.metadata.version',side_effect=lambda name:'2.6.0' if name=='torch' else '0.8.2'), \
         patch('socket.socket.connect',side_effect=AssertionError('No network')):
        exec(source.replace('/content/',folder+'/'),ns)
        assert keep.read_text()=='preserve me' and old.store.database.exists()
        if scenario=='active':
            commands.assert_not_called();widget.close.assert_not_called()
            old_ui.map.close.assert_not_called()
            assert detached_map.comm is not None
            assert ns['assistant'] is old and old.pending==draft
            assert any('update is paused' in str(m) for m in messages)
        elif scenario=='install_failure':
            commands.assert_called_once();widget.close.assert_not_called()
            old_ui.map.close.assert_not_called()
            assert detached_map.comm is not None
            assert ns['assistant'] is old and old.pending==draft
        else:
            commands.assert_called_once();widget.close.assert_called_once()
            old_ui.map.close.assert_called_once()
            assert detached_map.comm is None
            assert ns['assistant'] is not old and ns['assistant'].store.root==old.store.root
            assert ns['assistant'].pending is None and old.store.get(draft)['state']=='discarded'
            assert ns['local_parser']._generate is parser._generate
            assert sys.modules['libya_landcover'].__version__=='0.8.2'
            try: old.before_live()
            except ValueError: pass
            else: raise AssertionError('Old controls were not retired')
            exec(source.replace('/content/',folder+'/'),ns)
            commands.assert_called_once()
            assert not any('Disconnect and delete' in str(m) for m in messages)
        assert unrelated_map.comm is not None
        detached_map.close();unrelated_map.close()
print('passed',scenario)
'''

@unittest.skipUnless(importlib.util.find_spec('ipyleaflet'), 'Package CI installs [map] for startup UI checks')
class StartupUpgradeTests(unittest.TestCase):
    def check_scenario(self, scenario):
        result = subprocess.run([sys.executable,'-c',SCRIPT,scenario],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_loaded_old_package_upgrades_and_keeps_work(self): self.check_scenario('upgrade')
    def test_active_mapping_blocks_upgrade_without_retiring_ui(self): self.check_scenario('active')
    def test_install_failure_preserves_previous_interface(self): self.check_scenario('install_failure')
