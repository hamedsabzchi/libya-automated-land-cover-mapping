"""Chat side-effect boundaries and honest evidence presentation; no live APIs."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
import zipfile

from contracts import RunRequest
from libya_landcover.assistant import Assistant, launch_worker
from libya_landcover.chat_language import GuidedParser, OpenAIParser, IntentError, intent
from libya_landcover.chat_ui import render_reply
from libya_landcover.job_store import JobStore
from libya_landcover.jobs import enqueue_mapping, work_one
from libya_landcover.pilot import create_pilot, save_handoff, centered_spec
from test_jobs import bundle_files


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root / "store")
        self.launcher = Mock(return_value=123)
        self.assistant = Assistant(self.store, engine_commit="a" * 40, launcher=self.launcher)
        self.archive = self.root / "mapping.zip"
        with zipfile.ZipFile(self.archive, "w") as target:
            for name, content in bundle_files().items():
                target.writestr("run/" + name, content)

    def test_preview_is_local_and_double_confirm_never_reexecutes(self):
        preview = self.assistant.say("نقشه ۲۰۲۴")
        self.assertEqual(self.store.list(kind="mapping"), [])
        self.launcher.assert_not_called()
        self.assertEqual(preview["settings"]["request"]["trees"], 500)
        result = self.assistant.confirm(preview["draft_id"])
        self.assertEqual(result["state"], "queued")
        self.launcher.assert_called_once_with(self.store, result["job_id"])
        with self.assertRaises(ValueError):
            self.assistant.confirm(preview["draft_id"])
        self.assertEqual(len(self.store.list(kind="mapping")), 1)

    def test_new_message_and_restart_expire_confirmation(self):
        first = self.assistant.say("map 2024")
        second = self.assistant.say("map 2023")
        with self.assertRaises(ValueError):
            self.assistant.confirm(first["draft_id"])
        restarted = Assistant(self.store, engine_commit="a" * 40, launcher=self.launcher)
        with self.assertRaises(ValueError):
            restarted.confirm(second["draft_id"])
        self.launcher.assert_not_called()

    def test_invalid_year_model_override_and_parse_error_never_queue(self):
        for text in ('map 2025', '/map {"trees":1}', '/map {"aoi_asset":"invalid"}'):
            with self.assertRaises(ValueError):
                self.assistant.say(text)
        old = self.assistant.say("map 2024")
        self.assistant.parser = Mock()
        self.assistant.parser.parse.side_effect = IntentError("failed")
        with self.assertRaises(IntentError):
            self.assistant.say("new request")
        with self.assertRaises(ValueError):
            self.assistant.confirm(old["draft_id"])
        self.assertEqual(self.store.list(kind="mapping"), [])

    def test_unknown_language_cannot_confirm_or_invent_analysis(self):
        for text in ("yes", "تأیید", "run arbitrary python", "calculate crop area"):
            self.assertEqual(self.assistant.say(text)["type"], "help")
        self.assertEqual(self.store.list(kind="mapping"), [])

    def test_import_describe_and_backup_without_remote_calls(self):
        with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            response = self.assistant.import_archive(self.archive)
            self.assertEqual(response["state"], "completed")
            self.assertFalse(response["raster_included"])
            self.assertNotIn("metrics", response)
            self.assertEqual(self.assistant.say("نتیجه")["outputs"], response["outputs"])
            backup = self.assistant.save_backup(self.root / "saved.zip")
            other = Assistant(JobStore(self.root / "other"), engine_commit="a" * 40)
            self.assertEqual(other.import_archive(backup)["outputs"], response["outputs"])
            self.assistant.save_report(self.root / "report.json")
        self.launcher.assert_not_called()

    def test_pilot_snapshot_is_not_claimed_live_and_roundtrips(self):
        mapping = self.assistant.import_archive(self.archive)
        artifact = mapping["outputs"][0]["artifact_id"]
        plan = {"spec": centered_spec([400000, 3600000])}
        export = create_pilot(self.store, mapping["job_id"], artifact, plan)
        export = self.store.update(export, state="completed", remote_state="SUCCEEDED",
            destination_uris=["https://drive.google.com/#folders/example"])
        path = self.root / "pilot.zip"
        save_handoff(self.store, export["job_id"], plan, path, service_commit="a" * 40)
        with patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            response = self.assistant.import_archive(path)
            self.assertEqual(response["source"], "uploaded_archive_snapshot")
            self.assertEqual(response["coverage"], "pilot_window_only")
            self.assertEqual(response["state"], "completed")
            backup = self.assistant.save_backup(self.root / "roundtrip.zip")
            other = Assistant(JobStore(self.root / "other"), engine_commit="a" * 40)
            self.assertEqual(other.import_archive(backup)["state"], "completed")
        with patch("libya_landcover.assistant.recover_pilot", return_value=export) as recovery:
            refreshed = self.assistant.refresh()
            recovery.assert_called_once()
            self.assertEqual(refreshed["source"], "local_ledger")

    def test_pilot_plan_requires_separate_confirmation_and_reuses_export_identity(self):
        mapping = self.assistant.import_archive(self.archive)
        with patch("libya_landcover.assistant.plan_pilot", return_value={"spec": centered_spec([400000, 3600000])}), \
             patch("libya_landcover.assistant.submit_export", side_effect=lambda store, identifier: store.get(identifier)) as submit:
            preview = self.assistant.say("pilot")
            submit.assert_not_called()
            self.assertEqual(self.store.list(kind="export"), [])
            result = self.assistant.confirm(preview["draft_id"])
            self.assertEqual(result["coverage"], "pilot_window_only")
            submit.assert_called_once()
            with self.assertRaises(ValueError):
                self.assistant.confirm(preview["draft_id"])
        self.launcher.assert_not_called()

    def test_worker_targets_confirmed_job_not_first_queue_item(self):
        request = json.loads(bundle_files()["request.json"])
        first = enqueue_mapping(self.store, RunRequest(request), project="example-project", engine_commit="a" * 40)
        second = enqueue_mapping(self.store, RunRequest({**request, "request_id": str(uuid4())}),
                                 project="example-project", engine_commit="a" * 40)
        with patch("libya_landcover.cli.main", return_value=1):
            result = work_one(self.store, second["job_id"])
        self.assertEqual(result["job_id"], second["job_id"])
        self.assertEqual(self.store.get(first["job_id"])["state"], "queued")
        with patch("libya_landcover.cli.main") as run:
            self.assertIsNone(work_one(self.store, second["job_id"]))
            run.assert_not_called()

    def test_worker_has_no_shell_or_openai_secret_and_no_automatic_retry(self):
        preview = self.assistant.say("map 2024")
        self.assistant.launcher = launch_worker
        with patch.dict("os.environ", {"OPENAI_API_KEY": "private-test-key"}), \
             patch("libya_landcover.assistant.subprocess.Popen") as process:
            process.return_value.pid = 123
            result = self.assistant.confirm(preview["draft_id"])
            args, kwargs = process.call_args
            self.assertEqual(args[0][-2:], ["--job-id", result["job_id"]])
            self.assertNotIn("shell", kwargs)
            self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
        other = self.assistant.say("map 2024")
        with self.assertRaises(ValueError):
            self.assistant.confirm(other["draft_id"])
        self.store.update(self.store.get(result["job_id"]), state="failed")
        self.assistant.launcher = Mock(side_effect=OSError("private detail"))
        result = self.assistant.confirm(other["draft_id"])
        self.assertEqual(result["type"], "execution_error")
        self.assertNotIn("private detail", json.dumps(result))
        with self.assertRaises(ValueError):
            self.assistant.confirm(other["draft_id"])

    def test_html_escape_and_only_service_drive_links(self):
        rendered = render_reply({"message": '<script>alert(1)</script>',
            "destination_uris": ["javascript:alert(1)", "https://drive.google.com.evil/f", "https://drive.google.com/#folders/real"]})
        self.assertNotIn("<script>", rendered)
        self.assertEqual(rendered.count('<a '), 1)

    def test_widget_send_confirm_and_selection(self):
        try:
            import ipywidgets
        except ImportError:
            self.skipTest("Install [chat] for widget integration")
        from libya_landcover.chat_ui import ChatUI
        ui = ChatUI(self.assistant)
        ui.message.value = "نقشه ۲۰۲۴"
        ui.send.click()
        self.assertFalse(ui.confirm.disabled)
        self.launcher.assert_not_called()
        ui.confirm.click()
        self.assertTrue(ui.confirm.disabled)
        self.launcher.assert_called_once()
        self.assertEqual(ui.select.value, self.assistant.selected)
        ui.refresh.click()
        self.launcher.assert_called_once()


class LanguageTests(unittest.TestCase):
    def response(self, **changes):
        value = {"action": "mapping", "target_year": 2024, "aoi_asset": None,
                 "training_asset": None, "job_id": None, "question": None, **changes}
        return {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(value)}]}]}

    def test_openai_uses_schema_and_only_supplied_context(self):
        transport = Mock(return_value=self.response())
        parser = OpenAIParser("private-key", "configured-model", transport=transport)
        parsed = parser.parse("نقشه طرابلس ۲۰۲۴", {"active_profile": {"target_year": 2024}})
        self.assertEqual(parsed, intent("mapping", settings={"target_year": 2024}))
        payload = transport.call_args.args[0]
        self.assertFalse(payload["store"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertNotIn("private-key", json.dumps(payload))
        self.assertNotIn("tools", payload)

    def test_refusal_incomplete_invalid_and_execution_intents_are_rejected(self):
        cases = [self.response(action="execute"), self.response(target_year=True), self.response(extra="code"),
            self.response(job_id="invented"), self.response(action="status"),
            {"status": "incomplete", "output": []},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]}]
        for response in cases:
            with self.subTest(response=response), self.assertRaises(IntentError):
                OpenAIParser("key", "model", transport=lambda _: response).parse("request", {})

    def test_followup_receives_pending_settings_without_job_results(self):
        with tempfile.TemporaryDirectory() as root:
            parser = Mock()
            parser.parse.side_effect = [intent("mapping", settings={"aoi_asset": "projects/demo/assets/a"}),
                                        intent("mapping", settings={"target_year": 2023})]
            assistant = Assistant(JobStore(root), engine_commit="a" * 40, parser=parser)
            first = assistant.say("map this AOI")
            second = assistant.say("change year to 2023")
            self.assertEqual(second["settings"]["request"]["aoi_asset"], "projects/demo/assets/a")
            self.assertEqual(second["settings"]["request"]["target_year"], 2023)
            self.assertEqual(parser.parse.call_args.args[1]["pending_request"], first["settings"]["request"])


if __name__ == "__main__":
    unittest.main()
