"""Synchronous WP03 bridge; durable jobs, access control and downloads are later work."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from uuid import uuid4

from contracts import ContractError, RunRequest, RunResult, RunStatus, validate_exchange, validate_transition
from contracts.models import GEE_COMMIT, GEE_SHA256
from . import landcover_engine as engine


def request_from_inputs(payload):
    """Normalize supported pasted asset inputs, then apply the WP02 typed boundary."""
    if not isinstance(payload, dict):
        raise ContractError("Request must be an object")
    values = deepcopy(payload)
    try:
        for key in ("aoi_asset", "training_asset"):
            if key in values:
                if not isinstance(values[key], str):
                    raise ValueError(f"{key} must be a string")
                values[key] = engine.normalize_asset_id(values[key], key)
        if isinstance(values.get("class_field"), str):
            values["class_field"] = values["class_field"].strip()
    except ValueError as exc:
        raise ContractError(str(exc)) from exc
    return RunRequest(values)


def config_from_request(request):
    config = request.engine_config()
    config["seeds"] = tuple(config["seeds"])
    return engine.normalized_config(engine.LandCoverConfig(**config))


class MemoryArtifactStore:
    """Session-local EE image handles; deliberately not durable or an HTTP service."""

    def __init__(self):
        self._entries = {}

    def save_many(self, run_id, entries):
        # Validate the whole batch before mutating; caller supplies unique IDs.
        if any((run_id, key) in self._entries for key in entries):
            raise ValueError("Artifact already exists")
        self._entries.update({(run_id, key): value for key, value in entries.items()})

    def get(self, run_id, artifact_id):
        return self._entries[(run_id, artifact_id)]


@dataclass
class Execution:
    status: RunStatus
    result: RunResult | None
    artifact_store: object
    model: dict | None = None
    history: list | None = None
    diagnostic_exception: Exception | None = None


class StatusDeliveryError(RuntimeError):
    """A caller's observer failed; do not silently restart the model."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _wire_float(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _wire_count(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or int(value) != value:
        raise ValueError("Expected a nonnegative integer count from Earth Engine")
    return int(value)


def _result_payload(request, run_id, selected, engine_commit, engine_version, created_at):
    metrics, model = selected["best_metrics"], selected["model"]
    if model["seed"] != metrics["seed"]:
        raise ValueError("Selected graph and metric seed differ")
    config = config_from_request(request)
    entries, outputs = {}, []
    images = [("final_map", config.target_year, model["final_map"])]
    images.extend(("annual_map", year, model["yearly"][year]) for year in config.years)
    for kind, year, image in images:
        identifier = str(uuid4())
        entries[identifier] = image
        outputs.append({"artifact_id": identifier, "kind": kind, "year": year,
                        "reference": "artifact://" + identifier})
    result = RunResult({
        "schema_version": "1.0", "result_id": str(uuid4()), "run_id": run_id,
        "request_id": request.to_dict()["request_id"], "request_fingerprint": request.fingerprint(),
        "created_at": created_at, "request": request.to_dict(),
        "provenance": {"gee_reference_commit": GEE_COMMIT, "gee_sha256": GEE_SHA256,
                       "engine_commit": engine_commit, "engine_version": engine_version},
        "selection": {"seed": metrics["seed"], "minimum_producer_percent": metrics["minimum_producer_percent"],
                      "target_reached": metrics["target_reached"],
                      "stop_reason": "target_reached" if metrics["target_reached"] else "seeds_exhausted"},
        "metrics": {"overall": _wire_float(metrics["overall"]), "kappa": _wire_float(metrics["kappa"]),
                    "producer": [_wire_float(v) for v in metrics["producer"]],
                    "confusion": [[_wire_count(v) for v in row] for row in metrics["confusion"]],
                    "sampled_validation_count": _wire_count(metrics["sampled_validation_count"])},
        "outputs": outputs,
    })
    return result, entries


def run_request(request, *, engine_commit, engine_version=engine.ENGINE_VERSION,
                artifact_store=None, on_status=None, clock=_now):
    """Execute a validated request with a caller-initialized EE session.

    No authentication, automatic retry, export or persistent storage is performed.
    A provided artifact_store must atomically implement save_many(run_id, entries).
    The returned MemoryArtifactStore is usable only while this Python process lives.
    """
    if not isinstance(request, RunRequest):
        raise ContractError("Pass a validated RunRequest")
    if (not isinstance(engine_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", engine_commit)
            or engine_commit == "0" * 40):
        raise ContractError("Supply the actual nonzero engine Git commit SHA before starting")
    if not isinstance(engine_version, str) or not engine_version.strip():
        raise ContractError("engine_version is required")
    config = config_from_request(request)
    store = artifact_store if artifact_store is not None else MemoryArtifactStore()
    run_id, created = str(uuid4()), clock()
    current = RunStatus({"schema_version": "1.0", "run_id": run_id,
                         "request_id": request.to_dict()["request_id"],
                         "request_fingerprint": request.fingerprint(), "revision": 0,
                         "state": "queued", "phase": "queued", "created_at": created,
                         "updated_at": created, "progress": None, "error": None, "result_id": None})

    def notify():
        if on_status:
            try:
                on_status(RunStatus(current.to_dict()))
            except Exception as exc:
                raise StatusDeliveryError("Status observer failed; execution was not automatically retried") from exc

    def update(state, phase, *, progress=None, error=None, result_id=None):
        nonlocal current
        old = current.to_dict()
        new = RunStatus({**old, "revision": old["revision"] + 1, "updated_at": clock(),
                         "state": state, "phase": phase, "progress": progress,
                         "error": error, "result_id": result_id})
        validate_transition(current, new)
        current = new
        notify()

    def progress(event):
        payload = None
        if event["phase"] == "seed_search":
            payload = {key: event[key] for key in ("seed_index", "seed_count", "current_seed")}
        update("running", event["phase"], progress=payload)

    notify()
    selected = None
    try:
        selected = engine.search_seeds(config, on_event=progress)
        result, entries = _result_payload(request, run_id, selected, engine_commit, engine_version, clock())
        try:
            store.save_many(run_id, entries)
        except Exception as exc:
            raise engine.EngineError("OUTPUT_PREPARATION_FAILED", "preparing_outputs",
                                     "Selected map references could not be registered.") from exc
        # Validate linkage/time before publishing a completed status to the observer.
        old = current.to_dict()
        completed = RunStatus({**old, "revision": old["revision"] + 1, "updated_at": clock(),
                               "state": "completed", "phase": "completed", "progress": None,
                               "result_id": result.to_dict()["result_id"]})
        validate_transition(current, completed)
        validate_exchange(request, completed, result)
        current = completed
        notify()
        return Execution(current, result, store, selected["model"], selected["history"])
    except StatusDeliveryError:
        raise
    except Exception as exc:
        if isinstance(exc, engine.EngineError):
            error = {"code": exc.code, "phase": exc.phase, "message": str(exc), "retryable": exc.retryable}
        else:
            phase = current.to_dict()["phase"]
            error = {"code": "INTERNAL_ERROR", "phase": phase,
                     "message": "The engine or result adapter could not complete this request.", "retryable": False}
        update("failed", "failed", error=error)
        return Execution(current, None, store, history=selected["history"] if selected else None,
                         diagnostic_exception=exc)
