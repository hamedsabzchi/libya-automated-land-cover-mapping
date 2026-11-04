"""Fresh-user journey in one notebook. Remote compute/auth are mocked explicitly."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from contracts import RunRequest
from libya_landcover.assistant import Assistant
from libya_landcover.chat_ui import ChatUI
from libya_landcover.job_store import JobStore
from libya_landcover.pilot import centered_spec
from test_jobs import bundle_files


class OneNotebookTests(unittest.TestCase):
    def setUp(self):
        try:
            import ipywidgets
        except ImportError:
            self.skipTest("Install [chat] to exercise widgets; package CI requires it")
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launcher = Mock()
        self.assistant = Assistant(JobStore(self.root / 'store'), engine_commit='a'*40, launcher=self.launcher)
        self.connect = Mock()
        self.ui = ChatUI(self.assistant, connect=self.connect, download=Mock())

    def finish_mapping(self):
        """Stand in for completed EE computation, preserving the real request envelope."""
        job = self.assistant.store.get(self.assistant.selected)
        request = RunRequest(job['inputs']['request'])
        files = bundle_files()
        files['request.json'] = request.to_json().encode()
        for name in ('result.json', 'status.json'):
            value = json.loads(files[name]); value['request_id'] = request.to_dict()['request_id']
            value['request_fingerprint'] = request.fingerprint()
            if name == 'result.json': value['request'] = request.to_dict()
            files[name] = json.dumps(value).encode()
        manifest = json.loads(files['manifest.json']); manifest['project'] = job['inputs']['project']
        files['manifest.json'] = json.dumps(manifest).encode()
        for name, data in files.items():
            path = self.assistant.store.folder(job['job_id']) / 'bundle' / name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        self.assistant.store.update(job, state='completed')

    def test_fresh_user_to_download_without_upload_or_another_notebook(self):
        ui = self.ui
        self.assertIsNone(ui.restore.selected_index)
        self.assertEqual(ui.choices.layout.display, 'none')
        self.assertIn('1. Connect Google', ui.step.value)
        self.assertEqual(self.assistant.jobs(), [])
        ui.connection.click(); self.connect.assert_called_once()
        self.assertIn('2. Choose your map', ui.step.value)
        self.assertEqual(ui.choices.layout.display, '')
        ui.year.value = 2024; ui.prepare.click()
        self.assertIn('2024', ui.preview.value)
        self.launcher.assert_not_called()
        ui.confirm.click(); self.launcher.assert_called_once()
        self.assertIn('waiting to start', ui.progress.value)
        self.assertEqual(ui.pilot.layout.display, 'none')
        self.finish_mapping(); ui.refresh.click()
        self.assertEqual(ui.pilot.layout.display, '')
        self.assertIn('Map preparation finished', ui.progress.value)
        plan = {'spec': centered_spec([400000, 3600000])}
        def submitted(store, identifier):
            return store.update(store.get(identifier), state='running', remote_state='RUNNING')
        with patch('libya_landcover.assistant.plan_pilot', return_value=plan), \
             patch('libya_landcover.assistant.submit_export', side_effect=submitted) as submit:
            ui.pilot.click(); submit.assert_not_called()
            self.assertIn('not the whole study area', ui.preview.value)
            self.assertEqual(ui.confirm.description, 'Create sample file')
            ui.confirm.click(); submit.assert_called_once()
        def completed(store, identifier):
            return store.update(store.get(identifier), state='completed', remote_state='SUCCEEDED',
                destination_uris=['https://drive.google.com/#folders/test-output'])
        with patch('libya_landcover.assistant.poll_export', side_effect=completed):
            ui.refresh.click()
        self.assertIn('https://drive.google.com/#folders/test-output', ui.progress.value)
        self.assertIn('not the whole study area', ui.progress.value)
        ui.backup.click()
        self.assertTrue((self.assistant.store.root / 'landcover-saved-work.zip').is_file())
        self.assertEqual(len(self.assistant.store.list(kind='mapping')), 1)
        self.assertEqual(len(self.assistant.store.list(kind='export')), 1)

    def test_year_change_invalidates_review(self):
        self.ui.connection.click(); self.ui.prepare.click()
        old = self.assistant.pending
        self.ui.year.value = 2023
        self.assertIsNone(self.assistant.pending)
        self.assertTrue(self.ui.confirm.disabled)
        self.assertEqual(self.assistant.store.get(old)['state'], 'discarded')
        self.launcher.assert_not_called()

    def test_status_on_first_visit_tells_user_how_to_start(self):
        self.ui.message.value = 'status'; self.ui.send.click()
        self.assertIn('There is no map yet', self.ui.transcript.value)
        self.assertNotIn('Upload a previous result ZIP', self.ui.transcript.value)
        self.launcher.assert_not_called()

    def test_rerender_reselects_existing_work_without_new_job(self):
        self.ui.connection.click(); self.ui.prepare.click(); self.ui.confirm.click()
        job_id = self.assistant.selected
        other = Assistant(self.assistant.store, engine_commit='a'*40, launcher=self.launcher)
        reopened = ChatUI(other, connect=Mock())
        self.assertEqual(other.selected, job_id)
        self.assertIn('waiting to start', reopened.progress.value)
        self.launcher.assert_called_once()

    def test_closed_interface_cannot_start_old_request(self):
        self.ui.connection.click(); self.ui.prepare.click(); self.ui.close()
        self.ui.confirm.click()
        self.launcher.assert_not_called()



class NotebookEntryTests(unittest.TestCase):
    def test_single_start_notebook_has_no_prerequisite_upload(self):
        path = Path(__file__).resolve().parents[1] / 'python/07_wp07_free_english_assistant.ipynb'
        notebook = json.loads(path.read_text())
        code = [c for c in notebook['cells'] if c['cell_type'] == 'code']
        self.assertEqual(len(code), 1)
        source = ''.join(code[0]['source'])
        compile(source, str(path), 'exec')
        self.assertIn('start_assistant()', source)
        self.assertIn('display_chat', source)
        self.assertNotIn('OpenAIParser', source)
        self.assertNotIn('files.upload', source)
        self.assertTrue(all(not c.get('outputs') for c in code))


if __name__ == '__main__': unittest.main()
