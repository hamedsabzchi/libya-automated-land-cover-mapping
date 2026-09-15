from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_expected_files_exist():
    expected = [
        "README.md",
        "CITATION.cff",
        "gee/automated_land_cover_app.js",
        "python/landcover_engine.py",
        "python/01_test_gee_connection.py",
        "python/02_landcover_colab.ipynb",
        "python/requirements.txt",
        ".github/workflows/static-tests.yml",
    ]
    for relative in expected:
        assert (ROOT / relative).is_file(), relative


def test_personal_branding_and_no_institutional_authorship():
    js = (ROOT / "gee/automated_land_cover_app.js").read_text(encoding="utf-8")
    assert "By: Hamed Sabzchi Dehkharghani" in js
    assert "FAO-NSL Geospatial Unit" not in js
    assert "Food and Agriculture Organization of the United Nations" not in js
    assert "FAO_LandCover_Exports" not in js


def test_current_embedding_period_and_inputs_are_explicit():
    js = (ROOT / "gee/automated_land_cover_app.js").read_text(encoding="utf-8")
    engine = (ROOT / "python/landcover_engine.py").read_text(encoding="utf-8")
    for text in (js, engine):
        assert "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL" in text
        assert "USGS/SRTMGL1_003" in text
        assert "2017" in text
        assert "2024" in text
    assert "var yearBox = input('Assessment / priority year', 2024);" in js
    assert "var fallbackBox = input('Fallback year for the priority year', 2023);" in js
    assert "'Assessment year', 2017, 2024" in js
    assert "'Fallback year', 2017, 2024" in js


def test_classes_and_temporal_rules_are_present():
    js = (ROOT / "gee/automated_land_cover_app.js").read_text(encoding="utf-8")
    assert "var classValues = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];" in js
    assert "class4Count.gte(2)" in js
    assert "class5Count.gte(2)" in js
    assert "smileRandomForest" in js
    assert "getDownloadURL" in js
    assert "FINAL VERIFIED CLASS-DATA DOWNLOAD CORRECTION" in js


def test_complete_gee_script_is_not_shortened():
    js_path = ROOT / "gee/automated_land_cover_app.js"
    text = js_path.read_text(encoding="utf-8")
    assert js_path.stat().st_size > 90000
    assert "GENERATE FIRST 20 DOWNLOAD LINKS" in text
    assert "Empty/outside-AOI grid cells will be skipped automatically" in text


def test_notebook_is_valid_json_and_uses_safe_dynamic_import():
    path = ROOT / "python/02_landcover_colab.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook.get("cells", [])
    )
    assert "sys.modules[spec.name] = lc" in source
    assert "public_input_smoke_test" in source


def test_readme_has_scientific_cautions_and_personal_notice():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "independent personal technical portfolio" in readme.lower()
    assert "internal stratified random hold-out" in readme.lower()
    assert "not independent external validation" in readme.lower()
    assert "Google and Google DeepMind" in readme
    assert "No open-source license" in readme
