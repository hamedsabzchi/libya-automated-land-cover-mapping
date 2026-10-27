"""Single-owner chat tools over the existing engine, ledger and pilot exporter.

Conversation/LLM output never executes work. A separate confirm(draft_id) call
consumes a persisted preview. The reference engine and contracts are untouched.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4
import zipfile

from contracts import RunRequest
from .bundle import write_json
from .chat_language import GuidedParser, HELP, GUIDED_HELP, IntentError, validate_intent
from .job_store import now
from .jobs import checked_mapping_bundle, enqueue_mapping, mapping_status, project_id
from .exports import poll_export, submit_export
from .pilot import adopt_archive, create_pilot, plan_pilot, recover_pilot, save_handoff

TRIPOLI = {
    "project": "practical-proxy-441422-n6",
    "aoi_asset": "projects/practical-proxy-441422-n6/assets/Libya/Tripoli",
    "training_asset": "projects/practical-proxy-441422-n6/assets/Libya/TD3-attept1-tripoli",
    "target_year": 2024,
}


def launch_worker(store, job_id):
    """Separate process: target exactly the confirmed job, never the next queue item."""
    folder = store.folder(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    # Do not pass the optional language-model key to the EE-only worker.
    environment = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
    with (folder / "worker.log").open("ab") as log:
        process = subprocess.Popen([sys.executable, "-m", "libya_landcover", "jobs",
            "--store", str(store.root), "work-one", "--job-id", job_id],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            env=environment, start_new_session=True)
    return process.pid


class Assistant:
    def __init__(self, store, *, engine_commit, profile=None, parser=None, launcher=None, before_live=None):
        if not re.fullmatch(r"[0-9a-f]{40}", engine_commit or "") or engine_commit == "0" * 40:
            raise ValueError("Supply the installed engine source commit")
        self.store, self.engine_commit = store, engine_commit
        self.profile = dict(TRIPOLI if profile is None else profile)
        project_id(self.profile["project"])
        RunRequest({"request_id": str(uuid4()), **{k: v for k, v in self.profile.items() if k != "project"}})
        self.parser, self.launcher = parser or GuidedParser(), launcher or launch_worker
        self.before_live = before_live or (lambda: None)
        self.pending = None  # Restart never restores an executable confirmation button.
        self.selected = None
        self.clarification = None

    def jobs(self):
        return [dict(job_id=j["job_id"], kind=j["kind"], state=j["state"], updated_at=j["updated_at"])
                for j in self.store.list() if j["kind"] in {"mapping", "export", "assistant_snapshot"}]

    def _choose(self, identifier=None):
        identifier = identifier or self.selected
        if identifier is None:
            raise ValueError("There is no map yet. Connect Google, choose a year, and click Review my map to get started.")
        job = self.store.get(identifier)
        if job["kind"] not in {"mapping", "export", "assistant_snapshot"}:
            raise ValueError("Choose a mapping or export job")
        self.selected = job["job_id"]
        return job

    def discard(self):
        if self.pending:
            draft = self.store.get(self.pending)
            if draft["state"] == "prepared":
                self.store.update(draft, state="discarded")
        self.pending = None

    def _draft(self, inputs):
        draft = self.store.create("assistant_draft", "draft:" + str(uuid4()), inputs, state="prepared")
        self.pending = draft["job_id"]
        return {"type": "preview", "message": "Please review these settings. Nothing has started yet.",
                "draft_id": self.pending, "settings": inputs,
                "scope": "Mapping produces saved graphs. Pilot exports one small window; neither delivers the entire AOI TIFF."}

    def prepare_mapping(self, settings=None):
        """The form and chat use the same validation/confirmation boundary."""
        self.discard()
        parsed = validate_intent({"action": "mapping", "settings": settings or {}, "job_id": None, "question": None})
        request = RunRequest({**{k: v for k, v in self.profile.items() if k != "project"},
                              **parsed["settings"], "request_id": str(uuid4())})
        return self._draft({"action": "mapping", "project": self.profile["project"],
            "engine_commit": self.engine_commit, "request": request.to_dict()})

    def prepare_pilot(self, job_id=None):
        self.discard()
        mapping = self._choose(job_id)
        if mapping["kind"] in {"export", "assistant_snapshot"}:
            mapping = self.store.get(mapping["inputs"]["mapping_job_id"])
        if mapping["kind"] != "mapping" or mapping["state"] != "completed":
            raise ValueError("Select a completed mapping or import a previous result first.")
        checked = checked_mapping_bundle(self.store, mapping)
        artifact = next(o["artifact_id"] for o in checked["result"].to_dict()["outputs"] if o["kind"] == "final_map")
        self.before_live()
        plan = plan_pilot(self.store, mapping["job_id"])
        return self._draft({"action": "pilot", "mapping_job_id": mapping["job_id"],
            "artifact_id": artifact, "plan": plan})

    def say(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise IntentError("Message must contain 1–4000 characters")
        context = {"active_profile": self.profile, "pending_request": None,
                   "previous_clarification": self.clarification}
        if self.pending:
            old = self.store.get(self.pending)
            if old["state"] == "prepared" and old["inputs"]["action"] == "mapping":
                context["pending_request"] = old["inputs"]["request"]
        # Every new message invalidates the old confirmation, including parse errors.
        self.discard()
        parsed = validate_intent(self.parser.parse(text, context))
        action = parsed["action"]
        self.clarification = None
        if action == "mapping":
            settings = context["pending_request"] or {k: v for k, v in self.profile.items() if k != "project"}
            request = RunRequest({**settings, **parsed["settings"], "request_id": str(uuid4())})
            return self._draft({"action": "mapping", "project": self.profile["project"],
                "engine_commit": self.engine_commit, "request": request.to_dict()})
        if action == "pilot":
            return self.prepare_pilot(parsed["job_id"])
        if action == "jobs":
            return {"type": "jobs", "message": "Here are your saved jobs. This list does not query Earth Engine.", "jobs": self.jobs()}
        if action in {"status", "result"}:
            return self.describe(parsed["job_id"])
        if action == "clarify":
            self.clarification = {"request": text, "question": parsed["question"]}
            return {"type": "clarify", "message": parsed["question"] or HELP}
        return {"type": "help", "message": GUIDED_HELP if isinstance(self.parser, GuidedParser) else HELP}

    def confirm(self, draft_id):
        with self.store.lock("assistant-confirm"):
            draft = self.store.get(draft_id)
            if draft_id != self.pending or draft["kind"] != "assistant_draft" or draft["state"] != "prepared":
                raise ValueError("Preview expired/already consumed. Prepare and review a new request.")
            data = draft["inputs"]
            self.before_live()
            if data["action"] == "mapping" and any(j["state"] in {"queued", "running"}
                    for j in self.store.list(kind="mapping")):
                raise ValueError("A mapping is already queued or running. Check that job first; no new work was created.")
            # Persist consumption BEFORE any remote work. Uncertainty is not retried automatically.
            draft = self.store.update(draft, state="consumed")
            self.pending = None
            job = None
            try:
                if data["action"] == "mapping":
                    job = enqueue_mapping(self.store, RunRequest(data["request"]),
                        project=data["project"], engine_commit=data["engine_commit"])
                    self.selected = job["job_id"]
                    self.store.update(draft, target_job_id=job["job_id"])
                    self.launcher(self.store, job["job_id"])
                elif data["action"] == "pilot":
                    job = create_pilot(self.store, data["mapping_job_id"], data["artifact_id"], data["plan"])
                    self.selected = job["job_id"]
                    self.store.update(draft, target_job_id=job["job_id"])
                    job = submit_export(self.store, job["job_id"])
                else:
                    raise ValueError("Unsupported confirmed action")
            except Exception as exc:
                return {"type": "execution_error", "message": "Execution could not be confirmed. Check the job status before trying again; there is no automatic retry.",
                        "error_type": type(exc).__name__, "job_id": job["job_id"] if job else None}
            return self.describe(job["job_id"])

    def import_archive(self, path):
        """Import checked graphs and display archived evidence; no live EE call."""
        self.discard()
        adopted = adopt_archive(self.store, path)
        mapping = adopted["mapping"]
        self.selected = mapping["job_id"]
        context = adopted["context"]
        if context is not None:
            old = context["export"]
            snapshot = self.store.create("assistant_snapshot",
                "snapshot:" + mapping["job_id"] + ":" + old["job_id"] + ":" + str(old["revision"]),
                {"mapping_job_id": mapping["job_id"], "context": context}, state="recorded")
            self.selected = snapshot["job_id"]
        return self.describe()

    def describe(self, job_id=None):
        job = self._choose(job_id)
        if job["kind"] == "assistant_snapshot":
            context = job["inputs"]["context"]
            return self._export_summary(context["export"], identifier=job["job_id"],
                source="uploaded_archive_snapshot", observed_at=context.get("created_at"),
                mapping_job_id=job["inputs"]["mapping_job_id"])
        if job["kind"] == "export":
            return self._export_summary(job, identifier=job["job_id"], source="local_ledger",
                observed_at=job["updated_at"], mapping_job_id=job["inputs"]["mapping_job_id"])
        status = mapping_status(self.store, job["job_id"])
        response = {"type": "mapping", "job_id": job["job_id"], "state": job["state"],
            "source": "local_ledger", "observed_at": now(), "error": job.get("error"),
            "engine_status": status.get("engine_status"), "runner_failure": status.get("runner_failure"),
            "message": "This is the mapping-engine status. A completed mapping contains saved map graphs; it does not mean the entire area has been delivered as a TIFF."}
        if job["state"] == "completed":
            checked = checked_mapping_bundle(self.store, job)
            result = checked["result"].to_dict()
            response.update(request=result["request"], outputs=result["outputs"],
                provenance=result["provenance"], raster_included=False,
                exports=[j["job_id"] for j in self.store.list(kind="export")
                         if j["inputs"]["mapping_job_id"] == job["job_id"]])
        return response

    @staticmethod
    def _export_summary(job, *, identifier, source, observed_at, mapping_job_id):
        spec = job["inputs"]["spec"]
        pilot = "pixel_window" in spec
        return {"type": "export", "job_id": identifier, "original_job_id": job["job_id"],
            "mapping_job_id": mapping_job_id, "source": source, "observed_at": observed_at,
            "state": job["state"], "remote_state": job.get("remote_state"),
            "operation_name": job.get("operation_name"), "remote_metadata": job.get("remote_metadata"),
            "error": job.get("error"), "destination_uris": job.get("destination_uris", []),
            "drive_folder": job.get("drive_folder"), "spec": spec,
            "coverage": "pilot_window_only" if pilot else "requested_full_region",
            "message": ("This result covers one pilot window only. It does not confirm delivery of the entire area. " if pilot else "") +
                "This status belongs to the recorded time. The TIFF has not been inspected here and class areas have not been calculated."}

    def refresh(self, job_id=None):
        job = self._choose(job_id)
        if job["kind"] == "assistant_snapshot":
            self.before_live()
            restored = recover_pilot(self.store, job["inputs"]["mapping_job_id"], job["inputs"]["context"])
            self.selected = restored["job_id"]
        elif job["kind"] == "export":
            self.before_live()
            poll_export(self.store, job["job_id"])
        # Mapping is a local worker; poll_export also keeps terminal records local.
        return self.describe()

    def save_backup(self, destination):
        """Portable selected completed mapping or pilot handoff; no API keys/chat text."""
        job = self._choose()
        if job["kind"] == "export":
            if "pixel_window" not in job["inputs"]["spec"]:
                raise ValueError("Use the WP05 notebook to back up a full-area export")
            save_handoff(self.store, job["job_id"], {"spec": job["inputs"]["spec"]}, destination,
                         service_commit=self.engine_commit)
        else:
            mapping = self.store.get(job["inputs"]["mapping_job_id"]) if job["kind"] == "assistant_snapshot" else job
            if mapping["state"] != "completed":
                raise ValueError("Portable result backup requires a completed mapping; keep this runtime for active mapping work")
            checked = checked_mapping_bundle(self.store, mapping)
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as target:
                for name, data in checked["files"].items():
                    target.writestr("run/" + name, data)
                if job["kind"] == "assistant_snapshot":
                    context = job["inputs"]["context"]
                    target.writestr("pilot-context.json", json.dumps(context, ensure_ascii=False))
                    target.writestr("pilot-events.json", json.dumps(context.get("recovery_history", {}).get("events", [])))
        return Path(destination)

    def save_report(self, destination):
        report = {"schema_version": "wp06-report.1", "created_at": now(), "result": self.describe(),
                  "note": "Metadata only; no raster pixels, area statistics, credentials or chat transcript."}
        write_json(destination, report)
        return Path(destination)

