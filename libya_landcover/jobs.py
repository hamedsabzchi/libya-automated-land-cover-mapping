"""Persistent mapping work and adoption of already completed WP04 bundles."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import zipfile

from contracts import RunRequest, RunResult, RunStatus, validate_exchange
from contracts.models import GEE_SHA256
from .bundle import canonical_uuid, write_json
from .job_store import JobConflict, encoded

MAX_BUNDLE_BYTES = 100 * 1024 * 1024


def project_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,127}", value):
        raise ValueError("Supply an explicit Earth Engine project")
    return value


def validate_bundle(read):
    """read(relative_path) supplies bytes. Returns only whitelisted required files."""
    files = {}
    def document(name):
        data = read(name)
        if len(data) > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle file exceeds size limit")
        files[name] = data
        # Strict JSON decoder shared with contracts: no duplicate keys or NaN.
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate JSON key")
                result[key] = value
            return result
        def reject(value):
            raise ValueError("Nonfinite JSON")
        return json.loads(data, object_pairs_hook=unique, parse_constant=reject)

    request = RunRequest(document("request.json"))
    status = RunStatus(document("status.json"))
    result = RunResult(document("result.json"))
    validate_exchange(request, status, result)
    if status.to_dict()["state"] != "completed":
        raise ValueError("Only completed mapping bundles can be imported/exported")
    manifest = document("manifest.json")
    payload = result.to_dict()
    if (manifest.get("bundle_state") != "completed" or manifest.get("gee_sha256") != GEE_SHA256 or
            manifest.get("engine_commit") != payload["provenance"]["engine_commit"] or
            manifest.get("engine_commit") == "0" * 40 or
            manifest.get("representation") != "serialized_graphs_not_geotiffs"):
        raise ValueError("Bundle manifest and result provenance differ")
    project_id(manifest.get("project"))
    index = document("graphs/index.json")
    if (index.get("run_id") != payload["run_id"] or index.get("ee_version") != "1.7.48" or
            index.get("representation") != "earthengine_serialized_graph" or
            set(index.get("artifacts", {})) != {item["artifact_id"] for item in payload["outputs"]}):
        raise ValueError("Graph index does not match result")
    for identifier, entry in index["artifacts"].items():
        canonical_uuid(identifier)
        if entry["file"] != identifier + ".json":
            raise ValueError("Invalid graph path")
        name = "graphs/" + entry["file"]
        document(name)
        if hashlib.sha256(files[name]).hexdigest() != entry["sha256"]:
            raise ValueError("Graph checksum mismatch")
    if sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds size limit")
    return {"request": request, "result": result, "manifest": manifest, "files": files}


def bundle_digest(checked):
    return hashlib.sha256(encoded({name: hashlib.sha256(data).hexdigest()
                                  for name, data in checked["files"].items()}).encode()).hexdigest()


def checked_mapping_bundle(store, job):
    checked = load_bundle(store.folder(job["job_id"]) / "bundle")
    if job["origin"] == "imported":
        if bundle_digest(checked) != job["inputs"]["bundle_digest"]:
            raise ValueError("Imported mapping bundle changed")
    elif (checked["request"].to_dict() != job["inputs"]["request"] or
          checked["manifest"]["project"] != job["inputs"]["project"] or
          checked["manifest"]["engine_commit"] != job["inputs"]["engine_commit"]):
        raise ValueError("Mapping bundle belongs to different work")
    if job.get("bundle_digest") and bundle_digest(checked) != job["bundle_digest"]:
        raise ValueError("Completed mapping bundle changed")
    return checked


def load_bundle(directory):
    directory = Path(directory)
    def read(name):
        path = directory / name
        if path.is_symlink() or path.resolve().is_relative_to(directory.resolve()) is False:
            raise ValueError("Bundle symlinks are not supported")
        if path.stat().st_size > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle file exceeds size limit")
        return path.read_bytes()
    return validate_bundle(read)


def import_bundle(store, archive):
    """Import only checked result/manifest/graph files; never execute uploaded code."""
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)) or len(names) > 500:
            raise ValueError("Duplicate or excessive archive entries")
        if sum(item.file_size for item in members) > MAX_BUNDLE_BYTES:
            raise ValueError("Archive exceeds uncompressed size limit")
        for item in members:
            path = Path(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Unsafe archive member")
        if "run/result.json" not in names:
            raise ValueError("Expected a WP04 archive with run/result.json")
        checked = validate_bundle(lambda name: source.read("run/" + name))
    digest = bundle_digest(checked)
    result = checked["result"].to_dict()
    with store.lock("import"):
        job = store.create("mapping", "import:" + result["run_id"],
                           {"bundle_digest": digest, "project": checked["manifest"]["project"],
                            "source_run_id": result["run_id"]}, state="importing", extra={"origin": "imported"})
        if job["state"] == "completed":
            checked_mapping_bundle(store, job)
            return job
        folder = store.folder(job["job_id"])
        folder.mkdir(parents=True, exist_ok=True)
        pending, target = folder / "bundle.pending", folder / "bundle"
        if not target.exists():
            if pending.exists():
                shutil.rmtree(pending)
            pending.mkdir()
            for name, content in checked["files"].items():
                path = pending / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            pending.rename(target)
        checked_mapping_bundle(store, job)
        return store.update(job, state="completed", result_id=result["result_id"], run_id=result["run_id"])


def enqueue_mapping(store, request, *, project, engine_commit):
    if not isinstance(request, RunRequest):
        raise ValueError("Pass a validated RunRequest")
    if not re.fullmatch(r"[0-9a-f]{40}", engine_commit) or engine_commit == "0" * 40:
        raise ValueError("Actual engine source commit is required")
    return store.create("mapping", "mapping:" + request.to_dict()["request_id"],
                        {"request": request.to_dict(), "project": project_id(project), "engine_commit": engine_commit},
                        extra={"origin": "queued"})


def work_one(store, job_id=None):
    """Run one mapping request. Invoke from a separate process for background work.

    Crash recovery never retries an uncertain model run automatically. The process
    lock must be acquired before inspecting old running jobs or claiming a new one.
    """
    from . import cli
    with store.lock("mapping-worker"):
        if job_id is not None:
            target = store.get(job_id)
            if target["kind"] != "mapping":
                raise ValueError("Worker target must be a mapping job")
        for old in store.list(kind="mapping", state="running"):
            try:
                checked = checked_mapping_bundle(store, old)
                result = checked["result"].to_dict()
                store.update(old, state="completed", result_id=result["result_id"], run_id=result["run_id"],
                             bundle_digest=bundle_digest(checked), error=None)
            except (OSError, ValueError, KeyError):
                store.update(old, state="interrupted", error={"code": "WORKER_INTERRUPTED",
                    "message": "Previous worker ended without a verified completed bundle. No automatic retry."})
        jobs = store.list(kind="mapping", state="queued")
        if job_id is not None:
            jobs = [job for job in jobs if job["job_id"] == job_id]
        if not jobs:
            return None
        job = jobs[0]
        job = store.update(job, state="running")
        folder = store.folder(job["job_id"])
        folder.mkdir(parents=True, exist_ok=True)
        write_json(folder / "request.json", job["inputs"]["request"])
        try:
            code = cli.main(["run", str(folder / "request.json"), "--project", job["inputs"]["project"],
                             "--engine-commit", job["inputs"]["engine_commit"], "--output", str(folder / "bundle")])
            if code == 0:
                checked = checked_mapping_bundle(store, job)
                result = checked["result"].to_dict()
                return store.update(job, state="completed", result_id=result["result_id"], run_id=result["run_id"],
                                    bundle_digest=bundle_digest(checked))
            return store.update(job, state="failed", error={"code": "MAPPING_FAILED", "exit_code": code,
                                "message": "Inspect the saved engine status/manifest; no automatic retry."})
        except Exception as exc:
            return store.update(job, state="failed", error={"code": "WORKER_ERROR", "type": type(exc).__name__,
                                "message": "Worker failed; no automatic retry."})


def mapping_status(store, job_id):
    job = store.get(job_id)
    if job["kind"] != "mapping":
        return job
    path = store.folder(job_id) / "bundle" / "status.jsonl"
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            try:
                job["engine_status"] = RunStatus.from_json(line).to_dict()
                break
            except ValueError:
                continue  # An active worker may be between writing/flushing a line.
    else:
        final = store.folder(job_id) / "bundle" / "status.json"
        if final.exists():
            job["engine_status"] = RunStatus.from_json(final.read_text()).to_dict()
    return job
