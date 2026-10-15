"""WP02 wire contracts. Standard library only; never imports or executes GEE.

Use from_dict()/from_json() to validate and to_dict()/to_json() to serialize.
The WP03 python/assistant_adapter.py bridge consumes these unchanged wire formats.
"""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
from uuid import UUID

VERSION = "1.0"
GEE_COMMIT = "4c92894ec292ffa549275948d8d43f6cb8f89a8b"
GEE_SHA256 = "1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4"
SEEDS = (42, 123, 256, 389, 512, 645, 778, 891, 999, 1111, 2222, 3333, 4444, 5555)
CLASS_NAMES = (
    "Forest", "Shrubland", "Grassland", "Cultivated rainfed",
    "Cultivated irrigated", "Orchards", "Bare soil/sand", "Rocks",
    "Built up", "Artificial water", "Seasonal water", "Sebkha",
)
PALETTE = (
    "002200", "185e0a", "74a56a", "fffb00", "FF8C00", "43BE0A",
    "bb6d3a", "553a17", "808080", "00008B", "15c0df", "8B4513",
)
PHASES = {
    "queued": {"queued"},
    "running": {"asset_preflight", "coverage_preflight", "seed_search", "preparing_result"},
    "exporting": {"preparing_outputs"},
    "completed": {"completed"},
    "failed": {"failed"},
}
ERROR_CODES = {
    "INVALID_REQUEST", "ASSET_ACCESS_OR_SCHEMA", "EMPTY_AOI", "EMPTY_TRAINING",
    "INVALID_CLASSES", "INSUFFICIENT_CLASSES", "INSUFFICIENT_CLASS_SAMPLES",
    "COVERAGE_QUERY_FAILED", "COVERAGE_UNAVAILABLE", "SEED_EVALUATION_FAILED",
    "NO_SCORED_CLASSES", "NO_SUCCESSFUL_SEED", "OUTPUT_PREPARATION_FAILED",
    "INTERNAL_ERROR",
}


class ContractError(ValueError):
    """Invalid wire payload or inconsistent request/status/result identity."""


def require(condition, message):
    if not condition:
        raise ContractError(message)


def obj(value, required, optional=(), path="payload"):
    require(isinstance(value, dict), f"{path}: expected object")
    require(set(required) <= value.keys(), f"{path}: missing fields {set(required) - value.keys()}")
    require(value.keys() <= set(required) | set(optional), f"{path}: unknown fields")


def text(value, path):
    require(isinstance(value, str) and bool(value.strip()), f"{path}: expected nonempty string")


def integer(value, low, high, path):
    require(type(value) is int and low <= value <= high, f"{path}: expected integer {low}..{high}")


def number(value, low, high, path, nullable=False):
    if value is None and nullable:
        return
    require(type(value) in (int, float) and low <= value <= high and math.isfinite(value),
            f"{path}: expected finite number {low}..{high}")


def uuid(value, path):
    try:
        require(isinstance(value, str) and str(UUID(value)) == value, f"{path}: expected canonical UUID")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ContractError(f"{path}: expected canonical UUID") from exc


def digest(value, length, path):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None,
            f"{path}: expected {length} lowercase hexadecimal characters")


def timestamp(value, path):
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is not None,
        f"{path}: expected UTC RFC3339 timestamp ending in Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{path}: invalid date/time") from exc


def error_object(value):
    obj(value, ("code", "phase", "message", "retryable"), path="error")
    require(isinstance(value["code"], str) and value["code"] in ERROR_CODES, "error.code: unsupported value")
    require(isinstance(value["phase"], str) and value["phase"] in {"request", "queued", "asset_preflight", "coverage_preflight",
                              "seed_search", "preparing_result", "preparing_outputs"},
            "error.phase: unsupported value")
    text(value["message"], "error.message")
    require(type(value["retryable"]) is bool, "error.retryable: expected boolean")


class JsonContract:
    def __init__(self, payload):
        # Copy through strict JSON: live EE objects and nonfinite numbers cannot leak.
        try:
            encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False)
            copied = json.loads(encoded)
        except (TypeError, ValueError) as exc:
            raise ContractError("payload must contain only finite JSON values") from exc
        self._payload = self._validate(copied)

    @classmethod
    def from_dict(cls, payload):
        return cls(payload)

    @classmethod
    def from_json(cls, value):
        def reject_constant(token):
            raise ContractError(f"Non-JSON numeric constant: {token}")

        def unique_keys(pairs):
            result = {}
            for key, item in pairs:
                require(key not in result, f"Duplicate JSON key: {key}")
                result[key] = item
            return result

        try:
            return cls(json.loads(value, parse_constant=reject_constant, object_pairs_hook=unique_keys))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ContractError("Invalid JSON document") from exc

    def to_dict(self):
        return deepcopy(self._payload)

    def to_json(self):
        return json.dumps(self._payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


class RunRequest(JsonContract):
    """Resolved typed assistant request; public model controls only."""

    def _validate(self, value):
        defaults = {
            "schema_version": VERSION, "mode": "gee_reference_v1", "class_field": "lc_code",
            "target_year": 2024, "year_count": 5, "fallback_year": 2023,
            "train_fraction": 0.7, "trees": 500,
        }
        obj(value, ("request_id", "aoi_asset", "training_asset"), defaults.keys())
        value = {**defaults, **value}
        require(value["schema_version"] == VERSION, "Unsupported schema_version")
        require(value["mode"] == "gee_reference_v1", "Unsupported mode")
        uuid(value["request_id"], "request_id")
        for name in ("aoi_asset", "training_asset"):
            text(value[name], name)
            require(re.fullmatch(r"(?:projects/[^/\s]+/assets/[^\s]+|users/[^/\s]+/[^\s]+)",
                                 value[name]) is not None, f"{name}: expected canonical asset path")
        text(value["class_field"], "class_field")
        require(value["class_field"] == value["class_field"].strip(), "class_field must be trimmed")
        integer(value["target_year"], 2017, 2024, "target_year")
        integer(value["fallback_year"], 2017, 2024, "fallback_year")
        integer(value["year_count"], 1, 20, "year_count")
        integer(value["trees"], 1, 5000, "trees")
        number(value["train_fraction"], 0.01, 0.99, "train_fraction")
        value["train_fraction"] = float(value["train_fraction"])
        return value

    def engine_config(self):
        """Reference-mode mapping for WP03; does not call the current engine."""
        v = self._payload
        return {key: v[key] for key in (
            "aoi_asset", "training_asset", "class_field", "target_year", "year_count",
            "fallback_year", "train_fraction", "trees",
        )} | {
            "target_accuracy_percent": 60.0, "excluded_class_from_threshold": 8,
            "bag_fraction": 0.95, "seeds": list(SEEDS), "scale_m": 10.0, "tile_scale": 16,
        }

    def fingerprint(self):
        canonical = {
            "schema_version": VERSION, "mode": self._payload["mode"],
            "gee_reference_commit": GEE_COMMIT, "gee_sha256": GEE_SHA256,
            "engine_config": self.engine_config(),
        }
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RunStatus(JsonContract):
    """One versioned snapshot; validate_transition checks consecutive updates."""

    def _validate(self, value):
        obj(value, ("schema_version", "run_id", "request_id", "request_fingerprint",
                    "revision", "state", "phase", "created_at", "updated_at",
                    "progress", "error", "result_id"))
        require(value["schema_version"] == VERSION, "Unsupported schema_version")
        for key in ("run_id", "request_id"):
            uuid(value[key], key)
        digest(value["request_fingerprint"], 64, "request_fingerprint")
        integer(value["revision"], 0, 2**53 - 1, "revision")
        require(isinstance(value["state"], str) and value["state"] in PHASES, "Invalid state")
        require(isinstance(value["phase"], str) and value["phase"] in PHASES[value["state"]],
                "phase incompatible with state")
        created = timestamp(value["created_at"], "created_at")
        require(timestamp(value["updated_at"], "updated_at") >= created, "updated_at precedes created_at")
        if value["phase"] == "seed_search":
            p = value["progress"]
            obj(p, ("seed_index", "seed_count", "current_seed"), path="progress")
            integer(p["seed_index"], 1, len(SEEDS), "seed_index")
            require(type(p["seed_count"]) is int and p["seed_count"] == len(SEEDS), "seed_count mismatch")
            require(type(p["current_seed"]) is int and p["current_seed"] == SEEDS[p["seed_index"] - 1],
                    "current_seed disagrees with ordered seed_index")
        else:
            require(value["progress"] is None, "progress must be null outside seed_search")
        if value["state"] == "failed":
            error_object(value["error"])
        else:
            require(value["error"] is None, "Only failed status has a terminal error")
        if value["state"] == "completed":
            uuid(value["result_id"], "result_id")
        else:
            require(value["result_id"] is None, "result_id requires completed state")
        return value


class RunResult(JsonContract):
    """Selected result metadata. Raster pixels and live EE objects stay external."""

    def _validate(self, value):
        obj(value, ("schema_version", "result_id", "run_id", "request_id", "request_fingerprint",
                    "created_at", "request", "provenance", "selection", "metrics", "outputs"))
        require(value["schema_version"] == VERSION, "Unsupported schema_version")
        for key in ("result_id", "run_id", "request_id"):
            uuid(value[key], key)
        timestamp(value["created_at"], "created_at")
        request = RunRequest(value["request"])
        require(value["request"] == request.to_dict(), "result.request must include all resolved defaults")
        require(value["request_id"] == value["request"]["request_id"], "request_id mismatch")
        require(value["request_fingerprint"] == request.fingerprint(), "request fingerprint mismatch")
        provenance = value["provenance"]
        obj(provenance, ("gee_reference_commit", "gee_sha256", "engine_commit", "engine_version"),
            path="provenance")
        require(provenance["gee_reference_commit"] == GEE_COMMIT and provenance["gee_sha256"] == GEE_SHA256,
                "GEE reference identity mismatch")
        digest(provenance["engine_commit"], 40, "engine_commit")
        text(provenance["engine_version"], "engine_version")
        selection = value["selection"]
        obj(selection, ("seed", "minimum_producer_percent", "target_reached", "stop_reason"), path="selection")
        require(type(selection["seed"]) is int and selection["seed"] in SEEDS, "Unknown selected seed")
        number(selection["minimum_producer_percent"], 0, 100, "minimum_producer_percent")
        require(type(selection["target_reached"]) is bool, "target_reached must be boolean")
        require(selection["target_reached"] == (selection["minimum_producer_percent"] >= 60),
                "target_reached disagrees with reference threshold")
        require(selection["stop_reason"] == ("target_reached" if selection["target_reached"] else "seeds_exhausted"),
                "stop_reason disagrees with target_reached")
        metrics = value["metrics"]
        obj(metrics, ("overall", "kappa", "producer", "confusion", "sampled_validation_count"), path="metrics")
        number(metrics["overall"], 0, 1, "overall", nullable=True)
        number(metrics["kappa"], -1, 1, "kappa", nullable=True)
        require(isinstance(metrics["producer"], list) and len(metrics["producer"]) == 12,
                "producer must have 12 entries in class order")
        for v in metrics["producer"]:
            number(v, 0, 1, "producer entry", nullable=True)
        matrix = metrics["confusion"]
        require(isinstance(matrix, list) and len(matrix) == 12, "confusion must have 12 rows")
        for row in matrix:
            require(isinstance(row, list) and len(row) == 12, "confusion must have 12 columns")
            for count in row:
                integer(count, 0, 2**53 - 1, "confusion count")
        integer(metrics["sampled_validation_count"], 0, 2**53 - 1, "sampled_validation_count")
        require(sum(map(sum, matrix)) == metrics["sampled_validation_count"],
                "sampled count must equal ordered confusion matrix total")
        outputs = value["outputs"]
        require(isinstance(outputs, list), "outputs must be an array")
        years = list(range(value["request"]["target_year"],
                           value["request"]["target_year"] - value["request"]["year_count"], -1))
        expected = [("final_map", value["request"]["target_year"])] + [("annual_map", y) for y in years]
        require(len(outputs) == len(expected), "Expected final map and one map per requested year")
        identifiers = set()
        for item, (kind, year) in zip(outputs, expected):
            obj(item, ("artifact_id", "kind", "year", "reference"), path="output")
            uuid(item["artifact_id"], "artifact_id")
            require(item["artifact_id"] not in identifiers, "Duplicate artifact_id")
            identifiers.add(item["artifact_id"])
            require(item["kind"] == kind and type(item["year"]) is int and item["year"] == year,
                    "Output kind/year/order mismatch")
            require(item["reference"] == "artifact://" + item["artifact_id"], "Invalid artifact reference")
        return value

    def class_table(self):
        """Presentation data from the existing GEE class-table formula; no model call."""
        metrics = self._payload["metrics"]
        matrix = metrics["confusion"]
        rows = []
        for i, (name, producer) in enumerate(zip(CLASS_NAMES, metrics["producer"])):
            total = sum(row[i] for row in matrix)
            rows.append({
                "code": i + 1, "name": name, "color": PALETTE[i],
                "producer_percent": 0 if producer is None else producer * 100,
                "user_percent": matrix[i][i] / total * 100 if total else 0,
                "samples": sum(matrix[i]),
                "status": "Excluded" if i + 1 == 8 else "Included",
            })
        return rows


def validate_transition(previous, current):
    a, b = previous.to_dict(), current.to_dict()
    for key in ("run_id", "request_id", "request_fingerprint", "created_at"):
        require(a[key] == b[key], f"Transition changed immutable {key}")
    allowed = {"queued": {"running", "failed"}, "running": {"running", "exporting", "completed", "failed"},
               "exporting": {"exporting", "completed", "failed"}, "completed": set(), "failed": set()}
    require(b["state"] in allowed[a["state"]], "Invalid state transition")
    require(b["revision"] == a["revision"] + 1, "Consecutive status revisions required")
    require(timestamp(b["updated_at"], "updated_at") >= timestamp(a["updated_at"], "updated_at"),
            "Status time moved backwards")
    phase_order = ["asset_preflight", "coverage_preflight", "seed_search", "preparing_result"]
    if a["state"] == b["state"] == "running":
        require(phase_order.index(b["phase"]) >= phase_order.index(a["phase"]), "Run phase moved backwards")
        if a["phase"] == b["phase"] == "seed_search":
            require(b["progress"]["seed_index"] >= a["progress"]["seed_index"], "Seed index moved backwards")


def validate_exchange(request, status, result=None):
    r, s = request.to_dict(), status.to_dict()
    require(s["request_id"] == r["request_id"] and s["request_fingerprint"] == request.fingerprint(),
            "Status belongs to another request")
    if result is None:
        return  # A completed polling response may precede a separate result fetch.
    d = result.to_dict()
    require(s["state"] == "completed", "Cannot deliver result for incomplete run")
    require(d["request"] == r and d["run_id"] == s["run_id"] and d["result_id"] == s["result_id"],
            "Result does not belong to this request/run/status")
    require(timestamp(s["created_at"], "created_at") <= timestamp(d["created_at"], "created_at") <=
            timestamp(s["updated_at"], "updated_at"), "Result time is outside the run interval")
