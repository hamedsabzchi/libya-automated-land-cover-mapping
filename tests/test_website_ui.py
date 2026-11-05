"""Streamlit AppTest checks; no real login, Google API or map tile requests."""
import copy
import importlib.util
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from test_website_service import auth, result
from website.service import WebsiteError

HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None


class User(dict):
    @property
    def is_logged_in(self):
        return self.get("logged_in", True)

    @property
    def tokens(self):
        return {"access": "TEST-ACCESS-TOKEN"}


@unittest.skipUnless(HAS_STREAMLIT, "Install the separate website requirements to run UI tests")
class WebsiteUITests(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        self.user = User(sub="person-a", email="person-a@example.org", exp=time.time() + 3600)
        self.calls = []
        self.fail_action = None

        def operation(action, token, request, **kwargs):
            self.calls.append((action, token, request))
            if action == self.fail_action:
                raise WebsiteError("TEST_FAILURE", "The requested operation did not finish.")
            if action == "map":
                saved = result()
                saved["request"] = request
                return saved
            if action == "display":
                return {"tile_url": "https://example.org/{z}/{x}/{y}", "bounds": [[30, 10], [34, 14]]}
            return {"connected": True}

        for p in (patch("streamlit.secrets", {"auth": auth()}),
                  patch("streamlit.user", self.user),
                  patch("website.ui.run_operation", side_effect=operation),
                  patch("website.ui.st_folium", return_value={})):
            p.start()
            self.addCleanup(p.stop)
        self.app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))

    def fill(self):
        self.app.run()
        self.app.radio(key="website_area_choice").set_value("Custom data").run()
        self.app.text_input(key="website_project").input("person-a-project")
        self.app.text_input(key="website_aoi").input("projects/test-project/assets/region")
        self.app.text_input(key="website_training").input("projects/test-project/assets/training")
        return self

    def button(self, label):
        return next(b for b in self.app.button if b.label == label)

    def test_missing_owner_setup_is_clear_and_does_not_call_google(self):
        with patch("streamlit.secrets", {}):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertIn("website owner", self.app.warning[0].value)
        self.assertTrue(self.button("Sign in with Google").disabled)
        self.assertEqual(self.calls, [])

    def test_tripoli_requires_only_visitor_project_and_opens_map(self):
        from website.ui import TRIPOLI_AOI, TRIPOLI_TRAINING
        self.app.run()
        self.assertTrue(self.app.text_input(key="website_aoi").disabled)
        self.app.text_input(key="website_project").input("visitor-project")
        self.button("Create map").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual([c[0] for c in self.calls], ["connect", "map", "display"])
        request = self.calls[1][2]
        self.assertEqual(request["project"], "visitor-project")
        self.assertEqual(request["config"]["aoi_asset"], TRIPOLI_AOI)
        self.assertEqual(request["config"]["training_asset"], TRIPOLI_TRAINING)

    def test_switching_back_to_tripoli_does_not_use_custom_assets(self):
        from website.ui import TRIPOLI_AOI
        self.fill()
        # Submit custom values first, then switch the visible study-area choice.
        self.button("Check access").click().run()
        self.app.radio(key="website_area_choice").set_value("Tripoli (configured data)").run()
        self.button("Create map").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.calls[-2][2]["config"]["aoi_asset"], TRIPOLI_AOI)

    def test_failed_access_never_starts_mapping(self):
        self.fill()
        self.fail_action = "connect"
        self.button("Create map").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual([c[0] for c in self.calls], ["connect"])
        self.assertNotIn("website_result", self.app.session_state)

    def test_missing_secrets_file_is_handled(self):
        import streamlit as st
        from unittest.mock import Mock
        missing = Mock()
        missing.get.side_effect = st.errors.StreamlitSecretNotFoundError("No secrets file")
        with patch("streamlit.secrets", missing):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertIn("website owner", self.app.warning[0].value)
        self.assertEqual(self.calls, [])

    def test_google_login_is_offered_instead_of_private_key_upload(self):
        self.user["logged_in"] = False
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.button("Sign in with Google").label, "Sign in with Google")
        self.assertEqual(self.calls, [])

    def test_no_colab_exit_and_no_owner_compute(self):
        self.fill()
        links = self.app.get("link_button")
        self.assertFalse(any("colab" in str(link.proto).lower() for link in links))
        self.app.text_input(key="website_project").input("practical-proxy-441422-n6")
        self.button("Create map").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.calls, [])
        self.assertIn("owner's project cannot be used", self.app.error[0].value)

    def test_previously_saved_owner_result_can_be_read_but_not_refreshed(self):
        from website.service import run_operation
        self.fill()
        saved = result()
        saved["request"]["project"] = "practical-proxy-441422-n6"
        self.app.session_state.website_result = saved
        self.app.run()
        with patch("website.ui.run_operation", side_effect=run_operation), \
             patch("website.service.subprocess.run") as spawn:
            self.button("Open / refresh saved map").click().run()
        self.assertFalse(self.app.exception)
        spawn.assert_not_called()
        self.assertEqual(len(self.app.metric), 3)
        self.assertEqual(self.app.session_state.website_result, saved)
        self.assertEqual(self.app.session_state.website_display_error["code"], "COMPUTE_PROJECT_NOT_ALLOWED")

    def test_2025_fallback_and_results_survive_rerun_without_retraining(self):
        self.fill()
        self.app.selectbox(key="website_target").select(2025)
        self.app.selectbox(key="website_fallback").select(2024)
        self.button("Create map").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual([c[0] for c in self.calls], ["connect", "map", "display"])
        self.assertEqual(self.calls[1][2]["config"]["target_year"], 2025)
        self.assertEqual(self.calls[1][2]["config"]["fallback_year"], 2024)
        self.assertEqual(len(self.app.metric), 3)
        self.app.run()
        self.assertEqual(len(self.app.metric), 3)
        self.assertEqual(len(self.calls), 3)
        self.button("Create map").click().run()
        self.assertEqual(len(self.calls), 3)

    def test_access_check_does_not_train_and_missing_project_stops(self):
        self.app.run()
        self.button("Create map").click().run()
        self.assertEqual(self.calls, [])
        self.fill()
        self.button("Check access").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual([c[0] for c in self.calls], ["connect"])

    def test_map_display_failure_preserves_accuracy_and_can_retry_only_display(self):
        self.fill()
        self.fail_action = "display"
        self.button("Create map").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.metric), 3)
        self.assertIn("website_result", self.app.session_state)
        self.fail_action = None
        self.button("Open / refresh saved map").click().run()
        self.assertEqual([c[0] for c in self.calls], ["connect", "map", "display", "display"])

    def test_failed_new_mapping_preserves_previous_result(self):
        self.fill()
        self.button("Create map").click().run()
        old = copy.deepcopy(self.app.session_state.website_result)
        self.fail_action = "map"
        self.app.selectbox(key="website_target").select(2025)
        self.button("Create map").click().run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state.website_result, old)

    def test_expired_login_still_shows_report_but_blocks_new_work(self):
        self.fill()
        self.button("Create map").click().run()
        self.user["exp"] = time.time() - 1
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.metric), 3)
        self.assertTrue(self.button("Create map").disabled)
        self.assertTrue(self.button("Open / refresh saved map").disabled)

    def test_account_change_removes_previous_result(self):
        self.fill()
        self.button("Create map").click().run()
        self.user["sub"] = "person-b"
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.metric), 0)
        self.assertEqual(self.app.text_input(key="website_project").value, "")


if __name__ == "__main__":
    unittest.main()
