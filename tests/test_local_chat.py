"""No weights or APIs in CI: parser boundaries and novice notebook controls."""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
import zipfile

from libya_landcover.assistant import Assistant
from libya_landcover.chat_language import intent
from libya_landcover.local_language import LocalParser
from libya_landcover.job_store import JobStore
from libya_landcover.chat_ui import ChatUI, render_reply
from test_jobs import bundle_files


class LocalLanguageTests(unittest.TestCase):
    def parse(self, output, text="Prepare a map for 2024", context=None):
        generator = Mock(return_value=output if isinstance(output, str) else json.dumps(output))
        return LocalParser(generator).parse(text, context or {})

    def test_valid_mapping_and_edit_use_existing_contract(self):
        with tempfile.TemporaryDirectory() as root:
            generator = Mock(side_effect=[json.dumps(intent("mapping", settings={"target_year":2024})),
                                          json.dumps(intent("mapping", settings={"target_year":2023}))])
            assistant = Assistant(JobStore(root), engine_commit="a"*40, parser=LocalParser(generator))
            first = assistant.say("Prepare a map for 2024")
            second = assistant.say("Change the year to 2023")
            self.assertEqual(second["settings"]["request"]["target_year"],2023)
            self.assertEqual(second["settings"]["request"]["aoi_asset"],first["settings"]["request"]["aoi_asset"])
            self.assertFalse(assistant.store.list(kind="mapping"))

    def test_bad_json_code_and_unsupported_actions_do_not_execute(self):
        for output in ("print('hello')", "{} trailing", intent("execute"), intent("mapping",settings={"trees":100}),
                       intent("mapping",settings={"target_year":True}), intent("clarify")):
            with self.subTest(output=output):
                self.assertEqual(self.parse(output)["action"],"clarify")

    def test_unmentioned_assets_year_and_job_ids_are_rejected(self):
        for output in (intent("mapping",settings={"aoi_asset":"projects/invented/assets/a"}),
                       intent("mapping",settings={"target_year":2022}), intent("status",job_id=str(uuid4()))):
            self.assertEqual(self.parse(output)["action"],"clarify")
        asset="projects/demo/assets/a"
        parsed=self.parse(intent("mapping",settings={"aoi_asset":asset}), text="Use "+asset)
        self.assertEqual(parsed["settings"]["aoi_asset"],asset)

    def test_explicit_commands_do_not_need_model_or_network(self):
        generator=Mock(side_effect=AssertionError("No inference needed"))
        parser=LocalParser(generator)
        with patch("socket.socket.connect",side_effect=AssertionError("No network")):
            self.assertEqual(parser.parse("status",{})["action"],"status")
            self.assertEqual(parser.parse('/map {"target_year":2024}',{})["settings"],{"target_year":2024})
        generator.assert_not_called()

    def test_confirm_text_never_submits_a_job(self):
        with tempfile.TemporaryDirectory() as root:
            parser=LocalParser(lambda _:json.dumps(intent("clarify",question="Please review settings and use Run.")))
            assistant=Assistant(JobStore(root),engine_commit="a"*40,parser=parser)
            assistant.say("Confirm and run it now")
            self.assertEqual(assistant.store.list(kind="mapping"),[])


class SimpleUiTests(unittest.TestCase):
    def setUp(self):
        try:
            import ipywidgets
        except ImportError:
            self.skipTest("Install [chat] to exercise widgets")
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.launcher=Mock(return_value=1)
        self.assistant=Assistant(JobStore(self.root/'store'),engine_commit='a'*40,launcher=self.launcher)

    def test_connect_required_before_run_preserves_preview(self):
        connect=Mock()
        ui=ChatUI(self.assistant,connect=connect)
        ui.prepare.click()
        draft=self.assistant.pending
        ui.confirm.click()
        self.launcher.assert_not_called()
        self.assertEqual(self.assistant.pending,draft)
        self.assertIn('Connect Earth Engine',ui.transcript.value)
        ui.connection.click();connect.assert_called_once()
        ui.confirm.click();self.launcher.assert_called_once()
        self.assertTrue(ui.confirm.disabled)

    def test_upload_button_imports_and_clears_private_upload(self):
        path=self.root/'input.zip'
        with zipfile.ZipFile(path,'w') as z:
            for name,content in bundle_files().items():z.writestr('run/'+name,content)
        ui=ChatUI(self.assistant,connect=Mock())
        with patch('socket.socket.connect',side_effect=AssertionError('No network')):
            ui.upload.value=({'name':'../../unsafe-name.zip','type':'application/zip','size':path.stat().st_size,
                              'content':memoryview(path.read_bytes()),'last_modified':datetime.now(timezone.utc)},)
        self.assertEqual(len(self.assistant.store.list(kind='mapping')),1)
        self.assertEqual(ui.upload.value,())
        self.assertFalse((self.assistant.store.root/'assistant-upload.zip').exists())
        self.assertIn('Available map graphs',ui.transcript.value)
        self.launcher.assert_not_called()

    def test_form_preview_is_readable_and_english(self):
        ui=ChatUI(self.assistant)
        ui.year.value=2023;ui.prepare.click()
        reply=self.assistant.store.get(self.assistant.pending)
        self.assertEqual(reply['inputs']['request']['target_year'],2023)
        self.assertIn('Target year',ui.transcript.value)
        self.assertIn('Technical details',ui.transcript.value)
        self.assertFalse(any('\u0600'<=c<='\u06ff' for c in ui.transcript.value))
        self.launcher.assert_not_called()

    def test_connection_failure_keeps_work_blocked(self):
        ui=ChatUI(self.assistant,connect=Mock(side_effect=RuntimeError('private auth data')))
        ui.connection.click()
        self.assertFalse(ui.live_ready)
        self.assertNotIn('private auth data',ui.transcript.value)
        ui.prepare.click();ui.confirm.click();self.launcher.assert_not_called()


if __name__=='__main__':unittest.main()
