"""Offline regressions for the separate website; never contact Google."""
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from website.service import (
    EE_SCOPE, GOOGLE_METADATA, WebsiteError, accept_result, accuracy_rows,
    auth_configuration_error, bind_identity, make_request, report_bytes,
    request_key, run_operation,
)
from website.worker import execute, safe_error


def request(project="user-project-a"):
    return make_request(project, "projects/test-project/assets/region",
                        "projects/test-project/assets/training", 2025, 2024)


def result():
    matrix = [[0] * 12 for _ in range(12)]
    matrix[0][0], matrix[1][0], matrix[1][1] = 8, 2, 6
    return {"request": request(), "created_at": "2026-11-04T00:00:00Z",
            "metrics": {"confusion": matrix, "producer": [1, .75] + [None] * 10,
                        "overall": .875, "kappa": .75, "sampled_validation_count": 16},
            "history": [], "image": "saved-image", "geometry": "saved-geometry"}


def auth():
    return {"client_id": "client", "client_secret": "secret", "cookie_secret": "random",
            "redirect_uri": "https://example.org/oauth2callback",
            "server_metadata_url": GOOGLE_METADATA, "expose_tokens": ["access"],
            "client_kwargs": {"scope": "openid profile email " + EE_SCOPE}}


class WebsiteServiceTests(unittest.TestCase):
    def test_request_preserves_engine_defaults_and_both_years(self):
        r = request()
        self.assertEqual(r["project"], "user-project-a")
        self.assertEqual(r["config"]["target_year"], 2025)
        self.assertEqual(r["config"]["fallback_year"], 2024)
        self.assertEqual(r["config"]["trees"], 500)
        self.assertEqual(len(r["config"]["seeds"]), 14)
        self.assertEqual(r["config"]["aoi_asset"], "projects/test-project/assets/region")
        self.assertEqual(request_key(r), request_key(json.loads(json.dumps(r))))

    def test_missing_project_and_invalid_year_rejected_before_api(self):
        with self.assertRaises(ValueError):
            request("")
        with self.assertRaises(ValueError):
            make_request("user-project-a", "projects/p/assets/a", "projects/p/assets/b", 2030, 2024)

    def test_owner_project_and_numeric_aliases_cannot_start_a_worker(self):
        for project in ("practical-proxy-441422-n6", "123456789012", "projects/practical-proxy-441422-n6"):
            with self.subTest(project=project):
                with self.assertRaises(ValueError):
                    request(project)
                malformed = request()
                malformed["project"] = project
                with patch("website.service.subprocess.run") as spawn:
                    for action in ("connect", "map", "display"):
                        with self.assertRaises(WebsiteError):
                            run_operation(action, "token", malformed)
                    spawn.assert_not_called()

    def test_shared_owner_assets_do_not_change_compute_project(self):
        r = make_request("visitor-project", "projects/practical-proxy-441422-n6/assets/Libya/Tripoli",
                         "projects/practical-proxy-441422-n6/assets/Libya/TD3-attept1-tripoli", 2024, 2023)
        self.assertEqual(r["project"], "visitor-project")

    def test_auth_requires_api_scope_and_access_token_exposure(self):
        self.assertIsNone(auth_configuration_error(auth()))
        self.assertTrue(auth_configuration_error({}))
        for key, value in (("expose_tokens", []), ("client_kwargs", {"scope": "openid email"}),
                           ("server_metadata_url", "https://untrusted.example"),
                           ("redirect_uri", "http://example.org/oauth2callback")):
            settings = auth()
            settings[key] = value
            self.assertTrue(auth_configuration_error(settings), key)

    def test_all_classes_render_without_nonexistent_user_metric(self):
        saved = result()["metrics"]
        self.assertNotIn("user", saved)
        rows = accuracy_rows(saved)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0]["User accuracy (%)"], 80)
        self.assertEqual(rows[1]["User accuracy (%)"], 100)
        self.assertIsNone(rows[2]["User accuracy (%)"])
        self.assertIsNone(rows[2]["Producer accuracy (%)"])
        saved["producer"] = [[x] for x in saved["producer"]]
        self.assertEqual(accuracy_rows(saved), rows)

    def test_reports_exclude_credentials_and_map_urls(self):
        saved = result()
        saved.update(access_token="NEVER-IN-REPORT", tile_url="private-map-url")
        report = report_bytes(saved).decode()
        for hidden in ("NEVER-IN-REPORT", "private-map-url", "saved-image", "saved-geometry"):
            self.assertNotIn(hidden, report)
        self.assertEqual(json.loads(report)["metrics"], saved["metrics"])

    def test_identity_changes_clear_previous_work_and_settings(self):
        a, b = {}, {}
        bind_identity(a, "person-a")
        bind_identity(b, "person-b")
        accept_result(a, result())
        self.assertNotIn("website_result", b)
        bind_identity(a, "person-a")
        self.assertIn("website_result", a)
        bind_identity(a, "person-b")
        self.assertEqual(a, {"website_subject": "person-b"})

    def test_process_transport_keeps_token_off_argv_and_result(self):
        calls = []
        def runner(argv, **kwargs):
            payload = json.loads(kwargs["input"])
            calls.append((argv, kwargs, payload))
            return subprocess.CompletedProcess(argv, 0, json.dumps({"ok": True, "result": {"project": payload["request"]["project"]}}))
        with patch("website.service.subprocess.run", side_effect=runner):
            a = run_operation("connect", "token-a", request("person-a-project"))
            b = run_operation("connect", "token-b", request("person-b-project"))
        self.assertNotEqual(a, b)
        self.assertEqual([c[2]["access_token"] for c in calls], ["token-a", "token-b"])
        for argv, kwargs, payload in calls:
            self.assertEqual(argv, [sys.executable, "-m", "website.worker"])
            self.assertNotIn(payload["access_token"], " ".join(argv))
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_timeout_and_malformed_worker_output_are_safe(self):
        for failure in (subprocess.TimeoutExpired("worker", 1), OSError("secret detail")):
            with patch("website.service.subprocess.run", side_effect=failure):
                with self.assertRaises(WebsiteError) as ctx:
                    run_operation("map", "secret-token", request())
                self.assertNotIn("secret", str(ctx.exception))
        bad = subprocess.CompletedProcess([], 1, "traceback secret-token")
        with patch("website.service.subprocess.run", return_value=bad):
            with self.assertRaises(WebsiteError) as ctx:
                run_operation("connect", "secret-token", request())
            self.assertNotIn("secret-token", str(ctx.exception))

    def test_expired_quota_permission_errors_do_not_leak_raw_messages(self):
        for raw, code in (("401 expired Bearer SECRET", "AUTH_EXPIRED"),
                          ("429 quota Bearer SECRET", "QUOTA_LIMIT"),
                          ("403 permission Bearer SECRET", "ACCESS_DENIED"),
                          ("unknown https://example.org?token=SECRET", "EE_REQUEST_FAILED")):
            error = safe_error(RuntimeError(raw))
            self.assertEqual(error["code"], code)
            self.assertNotIn("SECRET", json.dumps(error))


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.ee = Mock()
        self.ee.data.getAsset.return_value = {"type": "TABLE"}
        self.modules = patch.dict(sys.modules, {"ee": self.ee})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_initializes_only_supplied_identity_and_project(self):
        execute({"action": "connect", "access_token": "token-a", "request": request("person-a-project")})
        execute({"action": "connect", "access_token": "token-b", "request": request("person-b-project")})
        calls = self.ee.Initialize.call_args_list
        self.assertEqual([c.kwargs["credentials"].token for c in calls], ["token-a", "token-b"])
        self.assertEqual([c.kwargs["project"] for c in calls], ["person-a-project", "person-b-project"])
        self.assertEqual([c.kwargs["credentials"].quota_project_id for c in calls], ["person-a-project", "person-b-project"])
        self.ee.Authenticate.assert_not_called()

    def test_worker_itself_rejects_owner_before_initializing_ee(self):
        r = request()
        r["project"] = "practical-proxy-441422-n6"
        for action in ("connect", "map", "display"):
            with self.assertRaises(ValueError):
                execute({"action": action, "access_token": "token", "request": r})
        self.ee.Initialize.assert_not_called()

    def test_mapping_uses_reference_search_and_saves_before_display(self):
        model = {"final_map": Mock(), "roi": Mock()}
        model["final_map"].serialize.return_value = "selected-image"
        model["roi"].geometry.return_value.serialize.return_value = "selected-geometry"
        selected = {"model": model, "best_metrics": result()["metrics"], "history": []}
        with patch("python.landcover_engine.search_seeds", return_value=selected) as search:
            saved = execute({"action": "map", "access_token": "token", "request": request()})
        self.assertEqual(search.call_args.args[0].trees, 500)
        search.assert_called_once()
        self.assertEqual(saved["image"], "selected-image")
        self.assertEqual(saved["metrics"], result()["metrics"])
        model["final_map"].getMapId.assert_not_called()
        model["final_map"].clip.assert_not_called()

    def test_display_reuses_graph_and_uses_bounds_for_collections(self):
        self.ee.Geometry.return_value.bounds.return_value.coordinates.return_value.getInfo.return_value = [
            [[10, 30], [14, 30], [14, 34], [10, 34], [10, 30]]]
        self.ee.Image.return_value.getMapId.return_value = {"tile_fetcher": Mock(url_format="https://earthengine.example/tiles/{z}/{x}/{y}")}
        with patch("python.landcover_engine.search_seeds") as search:
            displayed = execute({"action": "display", "access_token": "token", "request": request(), "result": result()})
        search.assert_not_called()
        self.ee.Geometry.return_value.bounds.assert_called_once_with(1, "EPSG:4326")
        self.ee.Geometry.return_value.coordinates.assert_not_called()
        self.assertEqual(displayed["bounds"], [[30, 10], [34, 14]])


if __name__ == "__main__":
    unittest.main()
