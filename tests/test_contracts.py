"""WP02 boundary tests: serialization/identity/state, never scientific evaluation."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from contracts import (
    ContractError, RunRequest, RunResult, RunStatus,
    validate_exchange, validate_transition,
)
from contracts.models import GEE_SHA256

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "contracts" / "examples"


def fixture(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.request = RunRequest(fixture("request.json"))

    def test_gee_is_byte_identical_to_wp01(self):
        expected = {
            "gee/automated_land_cover_app.js": GEE_SHA256,
        }
        for path, digest in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)

    def test_all_examples_and_round_trips(self):
        kinds = {"request.json": RunRequest, "request-resolved.json": RunRequest,
                 "status-running.json": RunStatus, "status-completed.json": RunStatus,
                 "status-failed.json": RunStatus, "result.json": RunResult}
        for name, cls in kinds.items():
            with self.subTest(name=name):
                value = cls.from_json((EXAMPLES / name).read_text())
                self.assertEqual(value.to_dict(), cls.from_json(value.to_json()).to_dict())

    def test_defaults_and_fixed_reference_settings(self):
        r = self.request.to_dict()
        self.assertEqual(r, fixture("request-resolved.json"))
        cfg = self.request.engine_config()
        self.assertEqual((cfg["scale_m"], cfg["target_accuracy_percent"], cfg["excluded_class_from_threshold"],
                          cfg["bag_fraction"], cfg["tile_scale"]), (10, 60, 8, .95, 16))
        self.assertEqual(cfg["seeds"], [42,123,256,389,512,645,778,891,999,1111,2222,3333,4444,5555])

    def test_fingerprint_is_stable_and_excludes_submission_id(self):
        resolved = fixture("request-resolved.json")
        self.assertEqual(self.request.fingerprint(), RunRequest(resolved).fingerprint())
        resolved["request_id"] = "44444444-4444-4444-8444-444444444444"
        self.assertEqual(self.request.fingerprint(), RunRequest(resolved).fingerprint())
        resolved["trees"] = 501
        self.assertNotEqual(self.request.fingerprint(), RunRequest(resolved).fingerprint())

    def test_public_request_cannot_override_hidden_model_settings(self):
        for key, value in {"scale_m":30, "seeds":[1], "bag_fraction":.5,
                           "target_accuracy_percent":90, "excluded_class_from_threshold":1,
                           "tile_scale":4, "stop_when_target_reached":False}.items():
            with self.subTest(field=key), self.assertRaises(ContractError):
                RunRequest({**fixture("request.json"), key:value})

    def test_request_rejects_missing_assets_types_ranges_and_unknown_versions(self):
        mutations = {"target_year":[2025,2024.5,"2024",True], "year_count":[0,21,True],
                     "trees":[0,5001,500.5,True], "train_fraction":[0,1,True,"0.7"],
                     "schema_version":["2.0"], "class_field":["", " lc_code "],
                     "aoi_asset":["", "Fezzan", "https://code.earthengine.google.com/?asset=users/demo/aoi"]}
        for key, values in mutations.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ContractError):
                    RunRequest({**fixture("request.json"), key:value})
        for key in ["aoi_asset", "training_asset", "request_id"]:
            payload = fixture("request.json")
            del payload[key]
            with self.assertRaises(ContractError):
                RunRequest(payload)

    def test_typed_request_does_not_replace_reference_coverage_preflight(self):
        payload = {**fixture("request.json"), "target_year":2017, "year_count":20}
        self.assertEqual(RunRequest(payload).to_dict()["year_count"], 20)

    def test_legacy_and_user_asset_paths(self):
        for path in ["users/example/aoi", "projects/earthengine-legacy/assets/users/example/aoi"]:
            RunRequest({**fixture("request.json"), "aoi_asset":path})

    def test_duplicate_keys_nonfinite_and_live_objects_are_rejected(self):
        for raw in ['{"request_id":"a","request_id":"b"}', '{"value":NaN}', '{"value":Infinity}']:
            with self.assertRaises(ContractError):
                RunRequest.from_json(raw)
        for value in [float("nan"), float("inf"), object()]:
            with self.assertRaises(ContractError):
                RunRequest({**fixture("request.json"), "train_fraction":value})

    def test_serialized_copies_do_not_mutate_contract(self):
        changed = self.request.to_dict()
        changed["trees"] = 1
        self.assertEqual(self.request.to_dict()["trees"], 500)

    def test_status_requires_consistent_state_and_terminal_fields(self):
        for patch in [{"phase":"completed"}, {"result_id":"33333333-3333-4333-8333-333333333333"},
                      {"error":{"code":"INTERNAL_ERROR"}}, {"state":[]}, {"progress":None}]:
            with self.subTest(patch=patch), self.assertRaises(ContractError):
                RunStatus({**fixture("status-running.json"), **patch})
        completed = fixture("status-completed.json")
        with self.assertRaises(ContractError):
            RunStatus({**completed, "result_id":None})

    def test_seed_progress_matches_reference_order(self):
        for progress in [{"seed_index":0,"seed_count":14,"current_seed":42},
                         {"seed_index":2,"seed_count":14,"current_seed":42},
                         {"seed_index":1,"seed_count":13,"current_seed":42}]:
            with self.assertRaises(ContractError):
                RunStatus({**fixture("status-running.json"), "progress":progress})

    def test_error_and_timestamp_validation(self):
        for stamp in ["2026-10-15", "2026-02-30T10:00:00Z", "2026-10-15T12:00:00+02:00", "2026-10-14T10:00:00Z"]:
            with self.assertRaises(ContractError):
                RunStatus({**fixture("status-running.json"), "updated_at":stamp})
        for key, value in [("code", []), ("phase", []), ("retryable", "yes")]:
            payload = fixture("status-failed.json")
            payload["error"][key] = value
            with self.assertRaises(ContractError):
                RunStatus(payload)

    def test_valid_run_transitions_and_completed_exchange(self):
        seed = RunStatus(fixture("status-running.json"))
        preparing = RunStatus({**seed.to_dict(), "revision":4, "phase":"preparing_result", "progress":None})
        done = RunStatus(fixture("status-completed.json"))
        validate_transition(seed, preparing)
        validate_transition(preparing, done)
        validate_exchange(self.request, done, RunResult(fixture("result.json")))

    def test_backward_states_revisions_and_identity_are_rejected(self):
        original = RunStatus(fixture("status-running.json"))
        patches = [{"revision":3}, {"revision":5}, {"revision":4, "phase":"asset_preflight", "progress":None},
                   {"revision":4, "run_id":"55555555-5555-4555-8555-555555555555"}]
        for patch in patches:
            with self.assertRaises(ContractError):
                validate_transition(original, RunStatus({**original.to_dict(), **patch}))
        completed = RunStatus(fixture("status-completed.json"))
        with self.assertRaises(ContractError):
            validate_transition(completed, RunStatus({**original.to_dict(), "revision":6}))

    def test_result_metric_shape_and_count_consistency(self):
        for field, value in [("producer", [1.0]*11), ("confusion", [[10]*12]*11),
                             ("sampled_validation_count",119), ("overall",2)]:
            payload = fixture("result.json")
            payload["metrics"][field] = value
            with self.assertRaises(ContractError):
                RunResult(payload)

    def test_nullable_metrics_keep_raw_null_and_reference_display_fallback(self):
        payload = fixture("result.json")
        payload["metrics"]["producer"][0] = None
        payload["metrics"]["kappa"] = None
        result = RunResult(payload)
        self.assertIsNone(result.to_dict()["metrics"]["producer"][0])
        self.assertEqual(result.class_table()[0]["producer_percent"], 0)

    def test_class_table_preserves_reference_formula_and_class_order(self):
        payload = fixture("result.json")
        payload["metrics"]["confusion"][1][0] = 5
        payload["metrics"]["sampled_validation_count"] = 125
        table = RunResult(payload).class_table()
        self.assertEqual([row["code"] for row in table], list(range(1,13)))
        self.assertAlmostEqual(table[0]["user_percent"], 10/15*100)
        self.assertEqual(table[1]["samples"], 15)
        self.assertEqual(table[7]["status"], "Excluded")
        self.assertEqual(table[4]["name"], "Cultivated irrigated")

    def test_result_reference_and_selection_are_bound_to_fixed_model(self):
        for field, value in [("seed",1), ("target_reached",False), ("stop_reason","seeds_exhausted")]:
            payload = fixture("result.json")
            payload["selection"][field] = value
            with self.assertRaises(ContractError):
                RunResult(payload)
        payload = fixture("result.json")
        payload["provenance"]["gee_sha256"] = "0"*64
        with self.assertRaises(ContractError):
            RunResult(payload)

    def test_result_requires_all_requested_annual_maps_and_unique_artifacts(self):
        for mode in ("missing", "duplicate", "wrong_year", "public_url"):
            payload = fixture("result.json")
            if mode == "missing": payload["outputs"].pop()
            if mode == "duplicate": payload["outputs"][1]["artifact_id"] = payload["outputs"][0]["artifact_id"]
            if mode == "wrong_year": payload["outputs"][1]["year"] = 2020
            if mode == "public_url": payload["outputs"][0]["reference"] = "https://example.com/map"
            with self.subTest(mode=mode), self.assertRaises(ContractError):
                RunResult(payload)

    def test_exchange_cannot_mix_requests_or_runs(self):
        done = RunStatus(fixture("status-completed.json"))
        result = RunResult(fixture("result.json"))
        other = RunRequest({**fixture("request.json"), "request_id":"44444444-4444-4444-8444-444444444444"})
        with self.assertRaises(ContractError):
            validate_exchange(other, done, result)
        payload = fixture("result.json")
        payload["run_id"] = "55555555-5555-4555-8555-555555555555"
        with self.assertRaises(ContractError):
            validate_exchange(self.request, done, RunResult(payload))
        with self.assertRaises(ContractError):
            validate_exchange(self.request, RunStatus(fixture("status-running.json")), result)

    def test_result_request_and_creation_time_cannot_drift(self):
        payload = fixture("result.json")
        payload["request"]["trees"] = 600
        with self.assertRaises(ContractError):
            RunResult(payload)
        payload = fixture("result.json")
        payload["created_at"] = "2026-10-15T10:05:00Z"
        with self.assertRaises(ContractError):
            validate_exchange(self.request, RunStatus(fixture("status-completed.json")), RunResult(payload))

    def test_cli_validates_exchange_without_earth_engine(self):
        command = [sys.executable, "-m", "contracts", "exchange", str(EXAMPLES/"request.json"),
                   str(EXAMPLES/"status-completed.json"), str(EXAMPLES/"result.json")]
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("Valid request/status/result exchange", run.stdout)


if __name__ == "__main__":
    unittest.main()
