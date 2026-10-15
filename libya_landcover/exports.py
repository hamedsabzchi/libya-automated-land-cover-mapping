"""Independent, persisted GeoTIFF export jobs for retained selected EE graphs."""

import hashlib
import math
import re
from urllib.parse import urlparse

from .bundle import GraphArtifactStore, canonical_uuid, write_json
from .job_store import JobConflict, encoded
from .jobs import checked_mapping_bundle

TERMINAL = {"completed", "failed", "cancelled"}


def export_spec(value):
    if not isinstance(value, dict) or not {"crs", "transform"} <= value.keys() or value.keys() - {
            "crs", "transform", "folder_prefix", "max_pixels", "file_dimensions"}:
        raise ValueError("Export spec requires crs/transform and only documented options")
    spec = {"folder_prefix": "LibyaLandCover", "max_pixels": 100000000, "file_dimensions": 4096, **value}
    if not isinstance(spec["crs"], str) or not re.fullmatch(r"EPSG:32[67](?:0[1-9]|[1-5][0-9]|60)", spec["crs"]):
        raise ValueError("WP05 requires an explicit UTM CRS in metres")
    transform = spec["transform"]
    if (not isinstance(transform, list) or len(transform) != 6 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in transform) or
            [transform[i] for i in (0, 1, 3, 4)] != [10, 0, 0, -10]):
        raise ValueError("Use an explicit north-up 10 m affine grid [10,0,x,0,-10,y]")
    if not isinstance(spec["folder_prefix"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", spec["folder_prefix"]):
        raise ValueError("Invalid folder prefix")
    if type(spec["max_pixels"]) is not int or not 1 <= spec["max_pixels"] <= 10**13:
        raise ValueError("Invalid max_pixels")
    if type(spec["file_dimensions"]) is not int or not 256 <= spec["file_dimensions"] <= 8192 or spec["file_dimensions"] % 256:
        raise ValueError("file_dimensions must be a multiple of 256, at most 8192")
    return spec


def enqueue_export(store, mapping_job_id, artifact_id, spec, *, request_id):
    canonical_uuid(request_id)
    canonical_uuid(artifact_id)
    source = store.get(mapping_job_id)
    if source["kind"] != "mapping" or source["state"] != "completed":
        raise ValueError("Export needs a completed mapping job")
    bundle = checked_mapping_bundle(store, source)
    result = bundle["result"].to_dict()
    output = next((item for item in result["outputs"] if item["artifact_id"] == artifact_id), None)
    if output is None:
        raise ValueError("Artifact does not belong to the selected mapping run")
    return store.create("export", "export:" + request_id, {
        "mapping_job_id": mapping_job_id, "artifact_id": artifact_id, "run_id": result["run_id"],
        "output": output, "project": bundle["manifest"]["project"], "spec": export_spec(spec)},
        extra={"ee_request_id": request_id, "operation_name": None, "remote_state": None,
               "destination_uris": [], "cancel_requested": False})


def description(job):
    output = job["inputs"]["output"]
    return "lc_" + output["kind"] + "_" + str(output["year"]) + "_" + job["ee_request_id"]


class EarthEngineBackend:
    def __init__(self, project):
        import ee
        if ee.__version__ != "1.7.48":
            raise RuntimeError("The persisted export payload requires earthengine-api 1.7.48")
        ee.Initialize(project=project)
        self.ee = ee

    def prepare(self, store, job):
        ee = self.ee
        folder = store.folder(job["inputs"]["mapping_job_id"]) / "bundle"
        checked = checked_mapping_bundle(store, store.get(job["inputs"]["mapping_job_id"]))
        request = checked["request"].to_dict()
        image = GraphArtifactStore(folder).get(job["inputs"]["run_id"], job["inputs"]["artifact_id"])
        # Serialization only: selection/search is not rerun. Server evaluation may
        # recompute the retained selected classifier graph when exporting pixels.
        spec = job["inputs"]["spec"]
        task = ee.batch.Export.image.toDrive(
            image=image.toUint8().unmask(0, False), description=description(job),
            folder=spec["folder_prefix"] + "_" + job["ee_request_id"], fileNamePrefix=description(job),
            region=ee.FeatureCollection(request["aoi_asset"]).geometry(),
            crs=spec["crs"], crsTransform=spec["transform"], maxPixels=spec["max_pixels"],
            fileDimensions=spec["file_dimensions"], shardSize=256,
            fileFormat="GeoTIFF", formatOptions={"cloudOptimized": True, "noData": 0})
        payload = dict(task.config)
        payload["expression"] = ee.serializer.encode(payload["expression"], for_cloud_api=True)
        payload["workloadTag"] = "libya-wp05"
        return payload

    def start(self, request_id, payload):
        # Public low-level API allows a persisted idempotency ID. Do not set the
        # private Task._request_id or assume Task IDs equal operation names.
        return self.ee.data.exportImage(request_id, payload)

    def get(self, operation):
        return self.ee.data.getOperation(operation)

    def list(self):
        return self.ee.data.listOperations()

    def cancel(self, operation):
        self.ee.data.cancelOperation(operation)


def _export(store, job_id):
    job = store.get(job_id)
    if job["kind"] != "export":
        raise ValueError("Expected an export job")
    return job


def _backend(job, backend):
    return backend if backend is not None else EarthEngineBackend(job["inputs"]["project"])


def _apply_operation(store, job, operation):
    name = operation.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"projects/[^/]+/operations/[A-Za-z0-9_-]+", name):
        raise ValueError("Missing or invalid operation name")
    if job["operation_name"] and name != job["operation_name"]:
        raise ValueError("Operation identity changed")
    metadata = operation.get("metadata", {})
    remote = metadata.get("state", "UNKNOWN")
    state = {"PENDING": "submitted", "RUNNING": "running", "CANCELLING": "cancelling",
             "SUCCEEDED": "completed", "FAILED": "failed", "CANCELLED": "cancelled"}.get(remote, "submitted")
    # Never label done-with-error as success, even if metadata is incomplete.
    if operation.get("done"):
        if operation.get("error"):
            state = "cancelled" if operation["error"].get("code") == 1 else "failed"
        elif remote not in {"CANCELLED", "FAILED"}:
            state = "completed"
    elif state in TERMINAL:
        raise ValueError("Terminal metadata without a completed operation")
    uris = metadata.get("destinationUris", [])
    if not isinstance(uris, list):
        raise ValueError("Invalid destination URIs")
    # These are service-provided destinations, not invented public download URLs.
    destinations = [uri for uri in uris if isinstance(uri, str) and
                    urlparse(uri).scheme == "https" and urlparse(uri).hostname in {"drive.google.com", "docs.google.com"}]
    error = None
    if state == "failed":
        error = {"code": "EXPORT_FAILED", "message": "Earth Engine export failed; inspect the operation in Tasks.",
                 "remote_code": operation.get("error", {}).get("code")}
    if job["cancel_requested"] and state not in TERMINAL:
        state = "cancelling"
    return store.update(job, state=state, operation_name=name, remote_state=remote,
                        destination_uris=destinations if state == "completed" else [], error=error)


def _reconcile(store, job, backend):
    found = [op for op in backend.list() if op.get("metadata", {}).get("description") == description(job)]
    if len(found) > 1:
        raise JobConflict("Multiple operations match; inspect Earth Engine Tasks")
    return _apply_operation(store, job, found[0]) if found else job


def submit_export(store, job_id, *, backend=None):
    """Explicit submission/recovery using one stored request ID and payload.

    Unknown submission outcomes are reconciled first. Retrying this call reuses
    the same server idempotency ID; it never invents a new export behind the caller.
    """
    from .cli import read_json
    with store.lock("export-" + canonical_uuid(job_id)):
        job = _export(store, job_id)
        if job["state"] in TERMINAL or job["operation_name"]:
            return job
        client = _backend(job, backend)
        if job["state"] in {"submitting", "submission_unknown"}:
            job = _reconcile(store, job, client)
            if job["operation_name"]:
                return job
        folder = store.folder(job_id)
        folder.mkdir(parents=True, exist_ok=True)
        payload_path = folder / "export-request.json"
        if job.get("payload_sha256"):
            payload = read_json(payload_path)
            if hashlib.sha256(encoded(payload).encode()).hexdigest() != job["payload_sha256"]:
                raise ValueError("Persisted export payload checksum mismatch")
        else:
            payload = client.prepare(store, job)
            digest = hashlib.sha256(encoded(payload).encode()).hexdigest()
            write_json(payload_path, payload)
            job = store.update(job, payload_sha256=digest,
                               drive_folder=job["inputs"]["spec"]["folder_prefix"] + "_" + job["ee_request_id"],
                               filename_prefix=description(job))
        job = store.update(job, state="submitting", error=None)
        try:
            operation = client.start(job["ee_request_id"], payload)
            return _apply_operation(store, job, operation)
        except Exception as exc:
            return store.update(job, state="submission_unknown", error={"code": "SUBMISSION_UNKNOWN",
                "type": type(exc).__name__, "message": "Submission outcome unknown. Poll/reconcile or explicitly resubmit with this same job ID."})


def poll_export(store, job_id, *, backend=None):
    with store.lock("export-" + canonical_uuid(job_id)):
        job = _export(store, job_id)
        if job["state"] in TERMINAL or job["state"] == "queued":
            return job
        client = _backend(job, backend)
        # Transport failures propagate; they never turn a running export into FAILED.
        if job["operation_name"]:
            return _apply_operation(store, job, client.get(job["operation_name"]))
        return _reconcile(store, job, client)


def cancel_export(store, job_id, *, backend=None):
    with store.lock("export-" + canonical_uuid(job_id)):
        job = _export(store, job_id)
        if job["state"] in TERMINAL:
            return job
        if job["state"] == "queued":
            return store.update(job, state="cancelled", cancel_requested=True)
        client = _backend(job, backend)
        if not job["operation_name"]:
            job = _reconcile(store, job, client)
        if job["state"] in TERMINAL:
            return job
        if not job["operation_name"]:
            raise JobConflict("Unknown submission must be reconciled before cancellation can be confirmed")
        # Persist intent before the remote call. A lost response can be retried.
        job = store.update(job, state="cancelling", cancel_requested=True)
        client.cancel(job["operation_name"])
        return job  # Poll must confirm CANCELLED or an already completed result.
