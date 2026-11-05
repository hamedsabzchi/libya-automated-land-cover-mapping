"""Simple website workflow with Google OAuth and per-session saved results."""
from __future__ import annotations

import time

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from python.landcover_engine import (
    CLASS_NAMES, CLASS_PALETTE, CLASS_VALUES, EMBEDDING_FIRST_YEAR, EMBEDDING_LAST_YEAR,
)
from website.service import (
    WebsiteError, accept_result, accuracy_rows, auth_configuration_error,
    bind_identity, make_request, report_bytes, request_key, run_operation,
)

SETUP_URL = "https://github.com/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/docs/website.md"
TRIPOLI_AOI = "projects/practical-proxy-441422-n6/assets/Libya/Tripoli"
TRIPOLI_TRAINING = "projects/practical-proxy-441422-n6/assets/Libya/TD3-attept1-tripoli"


def show_error(exc):
    st.error(str(exc))
    st.caption("Support code: " + exc.code)


def open_display(token, result):
    with st.spinner("Opening your saved map… No model training is repeated."):
        try:
            st.session_state.website_display = run_operation(
                "display", token, result["request"], result=result,
            )
            st.session_state.pop("website_display_error", None)
        except WebsiteError as exc:
            st.session_state.website_display_error = {"code": exc.code, "message": str(exc)}


def render_map(display):
    bounds = display["bounds"]
    center = [(bounds[0][i] + bounds[1][i]) / 2 for i in (0, 1)]
    m = folium.Map(location=center, tiles=None, zoom_start=8)
    folium.TileLayer(
        tiles=display["tile_url"], name="Land cover",
        attr="Google Earth Engine · Google Satellite Embedding",
        overlay=True, control=True, max_zoom=20,
    ).add_to(m)
    m.fit_bounds(bounds)
    folium.LayerControl().add_to(m)
    # No map-click reruns: viewing a tile must not start new model work.
    st_folium(m, height=530, use_container_width=True, returned_objects=[], key="website_map")
    columns = st.columns(3)
    for i, (code, name, color) in enumerate(zip(CLASS_VALUES, CLASS_NAMES, CLASS_PALETTE)):
        columns[i % 3].markdown(
            f'<span style="display:inline-block;width:12px;height:12px;background:#{color};'
            f'border:1px solid #777"></span> {code} · {name}', unsafe_allow_html=True,
        )
    st.caption("Colours load from Earth Engine as you explore. Blank areas may be masked or still loading. "
               "Preparing a map does not mean every display tile has finished.")


def render_result(result, token, can_call):
    config = result["request"]["config"]
    st.subheader(f"Your saved result · {config['target_year']}")
    display = st.session_state.get("website_display")
    if display:
        render_map(display)
    if "website_display_error" in st.session_state:
        error = st.session_state.website_display_error
        st.warning("Map display could not open. Your result and accuracy report are still saved in this session.")
        st.caption(error["message"] + " Support code: " + error["code"])
    if st.button("Open / refresh saved map", disabled=not can_call):
        open_display(token, result)
        st.rerun()
    st.subheader("Accuracy report")
    st.download_button("Download accuracy report", report_bytes(result),
                       file_name=f"land-cover-{config['target_year']}-accuracy.json",
                       mime="application/json", on_click="ignore")
    st.caption("This report contains settings and validation results, not TIFF pixels or login credentials.")
    metrics = result["metrics"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Overall accuracy", "Not available" if metrics["overall"] is None else f"{metrics['overall'] * 100:.2f}%")
    c2.metric("Kappa", "Not available" if metrics["kappa"] is None else f"{metrics['kappa']:.4f}")
    c3.metric("Validation samples", metrics.get("sampled_validation_count") or 0)
    st.caption("Saved model validation, not a separate assessment of the visible map tile. "
               "Reading these numbers starts no Earth Engine calculation.")
    with st.expander("Accuracy by class and confusion matrix"):
        st.dataframe(pd.DataFrame(accuracy_rows(metrics)), hide_index=True, width="stretch")
        st.write("Producer accuracy: correct reference samples within a class. "
                 "User accuracy: correct predictions within a predicted class. "
                 "A missing value means the measure is unavailable.")
        st.caption("Confusion matrix: rows = reference; columns = predicted.")
        st.dataframe(pd.DataFrame(metrics["confusion"], index=[f"Reference {c}" for c in CLASS_VALUES],
                                  columns=[f"Predicted {c}" for c in CLASS_VALUES]), width="stretch")
    with st.expander("Saved model settings"):
        st.json(result["request"])
    st.caption("Keep this tab connected and download the report before signing out. "
               "A browser reload, sign-out or server restart can end this temporary session.")


def main():
    st.set_page_config(page_title="Libya Land-Cover Website", layout="wide")
    st.title("Libya Land-Cover Map")
    st.write("Choose a study area and year. Create and explore your land-cover map here.")
    st.caption("1. Sign in   →   2. Choose your map   →   3. Explore your result")
    st.caption("No code or notebooks to run. Processing uses your own authorized Earth Engine project.")
    try:
        auth = dict(st.secrets.get("auth", {}))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        auth = {}
    problem = auth_configuration_error(auth)
    if problem:
        st.warning("Map creation is not available yet. The website owner needs to activate Google sign-in.")
        st.write("There is nothing for visitors to configure on this page. Once activated, "
                 "you will sign in, choose your map and view the result here.")
        st.button("Sign in with Google", type="primary", disabled=True)
        with st.expander("Website owner setup"):
            st.write(problem)
            st.link_button("Configure Google sign-in", SETUP_URL)
            st.caption("This is a one-time hosting setup. No password or secret belongs in GitHub or chat.")
        return

    if not st.user.is_logged_in:
        st.session_state.clear()
        if st.button("Sign in with Google", type="primary"):
            st.login()
        st.caption("Google will ask permission to use Earth Engine on your behalf. "
                   "Your selected project supplies the Earth Engine quota; you need permission to use it.")
        return

    subject = st.user.get("sub")
    if not subject:
        st.error("Google sign-in did not provide an account identifier. Sign out and try again.")
        if st.button("Sign out"):
            st.session_state.clear()
            st.logout()
        return
    bind_identity(st.session_state, subject)
    st.write("Signed in as " + str(st.user.get("email", "your Google account")))
    if st.button("Sign out / change Google account"):
        st.session_state.clear()
        st.logout()
        return
    token = st.user.tokens.get("access")
    expired = float(st.user.get("exp", 0)) <= time.time()
    can_call = bool(token) and not expired
    if not can_call:
        st.warning("Google authorization needs renewing. Download any saved report below, then sign out "
                   "and sign in again. No new Earth Engine work will start.")

    st.subheader("Choose your map")
    study_area = st.radio("Study area", ["Tripoli (configured data)", "Custom data"],
                          key="website_area_choice", horizontal=True)
    if study_area == "Tripoli (configured data)":
        st.caption("Tripoli's boundary and training data are already selected. "
                   "Your Google account must have permission to read them.")
    with st.expander("Why do I need a processing project?"):
        st.write("Earth Engine assigns processing allowance to a registered Google Cloud project. "
                 "Use a project belonging to you or your organization, so this website does not use "
                 "the owner's allowance. A Google account alone does not provide this access. "
                 "If you do not have an approved project, ask your organization's administrator to arrange one.")
    with st.form("website_settings"):
        project = st.text_input("Your processing project ID", key="website_project",
                                placeholder="your-earth-engine-project")
        c1, c2 = st.columns(2)
        years = list(range(EMBEDDING_FIRST_YEAR, EMBEDDING_LAST_YEAR + 1))
        target = c1.selectbox("Target year", years, index=years.index(2024), key="website_target")
        fallback = c2.selectbox("Fallback year", years, index=years.index(2023), key="website_fallback")
        st.caption("Fallback year is used by the reference model when its fallback rule applies.")
        with st.expander("Study-area data", expanded=study_area == "Custom data"):
            custom_aoi = st.text_input("Study-area boundary asset", key="website_aoi",
                                      value=TRIPOLI_AOI, disabled=study_area != "Custom data")
            custom_training = st.text_input("Training-data asset", key="website_training",
                                           value=TRIPOLI_TRAINING, disabled=study_area != "Custom data")
        aoi, training = ((TRIPOLI_AOI, TRIPOLI_TRAINING) if study_area != "Custom data"
                         else (custom_aoi, custom_training))
        with st.expander("Additional settings"):
            year_count = st.number_input("Years combined", min_value=1, max_value=20, value=5, step=1)
            class_field = st.text_input("Training class field", value="lc_code")
            st.caption("The existing engine uses 500 trees and its reference seed search. "
                       "The annual window must have available embedding data.")
        create = st.form_submit_button("Create map", type="primary", disabled=not can_call)
        with st.expander("Optional access check"):
            check = st.form_submit_button("Check access", disabled=not can_call)
        st.caption("Create map checks your access automatically and opens the result when ready. "
                   "Keep this page open while it works.")

    if check or create:
        try:
            request = make_request(project, aoi, training, target, fallback, year_count, class_field)
        except ValueError as exc:
            st.error(str(exc))
        else:
            existing = st.session_state.get("website_result")
            if create and existing and request_key(existing["request"]) == request_key(request):
                st.info("This map is already prepared in this session. Showing its saved result; no new training was started.")
            else:
                try:
                    with st.spinner("Checking your project and asset access…"):
                        run_operation("connect", token, request)
                    if check:
                        st.success("Project and both assets are accessible. You can now create your map.")
                    if create:
                        with st.spinner("Preparing your map with the reference engine. Keep this tab open; one click is enough."):
                            result = run_operation("map", token, request)
                        accept_result(st.session_state, result)
                        open_display(token, result)
                except WebsiteError as exc:
                    show_error(exc)

    result = st.session_state.get("website_result")
    if result:
        render_result(result, token, can_call)


if __name__ == "__main__":
    main()
