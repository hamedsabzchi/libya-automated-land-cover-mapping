"""Core Earth Engine logic for the Libya automated land-cover mapping project.

The module mirrors the modeling core of the reference JavaScript application:
annual Google Satellite Embedding predictors + SRTM terrain, class-stratified
hold-out splitting, per-year Random Forests, and the documented temporal rules.

This is an independent personal technical portfolio project by
Hamed Sabzchi Dehkharghani.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import re
from urllib.parse import unquote
from typing import Any, Dict, Iterable, Tuple

try:
    import ee
except ModuleNotFoundError as exc:
    if exc.name != "ee":
        raise
    ee = None  # Pure input/selection helpers can be checked offline.

ENGINE_VERSION = "0.3.0"

EMBEDDING_COLLECTION = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
# Modeling-core counterpart of the complete GEE application.
# It mirrors predictor construction, stratified splitting, Random Forest settings,
# temporal cultivated-class rules, validation metrics, and 2017-2024 data bounds.
# The final flexibleRunCompleteAssets path is the reference (WP01).
# Browser widgets and direct-download orchestration belong to later output work.
# Native classifier-backed images are retained; no tree-text conversion is used.
SRTM_IMAGE = "USGS/SRTMGL1_003"
EMBEDDING_FIRST_YEAR = 2017
EMBEDDING_LAST_YEAR = 2024

DEFAULT_AOI_ASSET = "projects/practical-proxy-441422-n6/assets/Libya/Fezzan"
DEFAULT_TRAINING_ASSET = "projects/practical-proxy-441422-n6/assets/Libya/TD-V4"
DEFAULT_CLASS_FIELD = "lc_code"

CLASS_VALUES: Tuple[int, ...] = tuple(range(1, 13))
CLASS_NAMES: Tuple[str, ...] = (
    "Forest", "Shrubland", "Grassland", "Cultivated rainfed",
    "Cultivated irrigated", "Orchards", "Bare soil/sand", "Rocks",
    "Built up", "Artificial water", "Seasonal water", "Sebkha",
)
CLASS_PALETTE: Tuple[str, ...] = (
    "002200", "185e0a", "74a56a", "fffb00", "FF8C00", "43BE0A",
    "bb6d3a", "553a17", "808080", "00008B", "15c0df", "8B4513",
)
DEFAULT_SEEDS: Tuple[int, ...] = (
    42, 123, 256, 389, 512, 645, 778, 891, 999, 1111, 2222, 3333, 4444, 5555,
)


@dataclass(frozen=True)
class LandCoverConfig:
    aoi_asset: str = DEFAULT_AOI_ASSET
    training_asset: str = DEFAULT_TRAINING_ASSET
    class_field: str = DEFAULT_CLASS_FIELD
    target_year: int = 2024
    year_count: int = 5
    fallback_year: int = 2023
    target_accuracy_percent: float = 60.0
    excluded_class_from_threshold: int = 8
    train_fraction: float = 0.70
    trees: int = 500
    bag_fraction: float = 0.95
    seeds: Tuple[int, ...] = DEFAULT_SEEDS
    scale_m: float = 10.0
    tile_scale: int = 16

    @property
    def years(self) -> Tuple[int, ...]:
        return tuple(self.target_year - i for i in range(self.year_count))


class EngineError(RuntimeError):
    """A reference preflight/selection failure with a stable adapter code."""

    def __init__(self, code, phase, message, *, retryable=False, details=None):
        super().__init__(message)
        self.code, self.phase, self.retryable = code, phase, retryable
        self.details = details or {}


def _require_ee():
    if ee is None:
        raise RuntimeError("Install python/requirements.txt and initialize Earth Engine before execution.")


def normalize_asset_id(value, field_name="Asset"):
    """Port of flexibleAssetId; pure normalization, no asset lookup."""
    text = str(value or "").strip()
    text = re.sub(r"^[\s\"'`]+|[\s\"'`]+$", "", text)
    text = re.sub(r"^https?://code\.earthengine\.google\.com/\?asset=", "", text, flags=re.I)
    try:
        if re.search(r"%(?![0-9a-fA-F]{2})", text):
            raise ValueError("Malformed URI escape")
        text = unquote(text, errors="strict")
    except (ValueError, UnicodeError):
        pass
    for pattern in (r"projects/earthengine-legacy/assets/[^\s\"'`]+",
                    r"projects/[^\s\"'`]+/assets/[^\s\"'`]+", r"users/[^\s\"'`]+"):
        match = re.search(pattern, text, flags=re.I)
        if match:
            text = match.group(0)
            break
    text = re.sub(r"[\s,;]+$", "", text)
    if not re.fullmatch(r"(?:projects/[^/]+/assets/.+|users/.+)", text):
        raise ValueError(f"{field_name} is not a valid Earth Engine asset ID.")
    return text


def normalized_config(config):
    result = replace(config, aoi_asset=normalize_asset_id(config.aoi_asset, "AOI asset"),
                     training_asset=normalize_asset_id(config.training_asset, "Training asset"),
                     class_field=config.class_field.strip(), seeds=tuple(config.seeds))
    validate_config(result)
    return result


def validate_config(config):
    # Typed Python boundary from WP02, not the JavaScript textbox coercion rules.
    normalize_asset_id(config.aoi_asset, "AOI asset")
    normalize_asset_id(config.training_asset, "Training asset")
    if not isinstance(config.class_field, str) or not config.class_field.strip():
        raise ValueError("Class field is empty.")
    for key, low, high in (("target_year",2017,2024), ("fallback_year",2017,2024),
                          ("year_count",1,20), ("trees",1,5000), ("tile_scale",1,64),
                          ("excluded_class_from_threshold",-999,999)):
        value = getattr(config, key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer in {low}..{high}.")
    for key, low, high in (("train_fraction",.01,.99), ("bag_fraction",.01,1),
                          ("target_accuracy_percent",0,100)):
        value = getattr(config, key)
        if type(value) not in (int,float) or not low <= value <= high or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number in {low}..{high}.")
    if type(config.scale_m) not in (int,float) or config.scale_m != 10:
        raise ValueError("The GEE reference uses a fixed 10 m scale.")
    if not config.seeds or any(type(seed) is not int for seed in config.seeds):
        raise ValueError("At least one integer random seed is required.")
    # Do not reject an early annual-window year here: GEE coverage preflight decides.


_MISSING = object()


def _js_number(value):
    """Number coercion for reference histogram keys and evaluated numeric arrays."""
    if value is _MISSING:
        return float("nan")
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, list):
        def array_text(item):
            if item is None:
                return ""
            if isinstance(item, list):
                return ",".join(array_text(v) for v in item)
            if isinstance(item, bool):
                return "true" if item else "false"
            return str(item)
        value = array_text(value)
    if isinstance(value, str):
        value = value.strip().strip("\ufeff").strip()
        if not value:
            return 0.0
        if re.fullmatch(r"0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+", value):
            return float(int(value, 0))
        if not re.fullmatch(r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|Infinity)", value):
            return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return float("nan")


def build_class_lookup(histogram):
    lookup, counts = {}, {}
    for key, count in (histogram or {}).items():
        number = _js_number(str(key))
        if math.isfinite(number) and number.is_integer() and int(number) in CLASS_VALUES:
            code = int(number)
            lookup[str(key)] = code
            counts[code] = counts.get(code, 0) + _js_number(count or 0)
    return {"lookup": lookup, "counts": counts, "total": sum(counts.values())}


def validate_asset_report(report):
    if not isinstance(report, dict) or not report:
        raise EngineError("ASSET_ACCESS_OR_SCHEMA", "asset_preflight", "No asset/schema result returned.")
    if _js_number(report.get("aoiFeatures") or 0) < 1 or _js_number(report.get("aoiAreaM2") or 0) <= 0:
        raise EngineError("EMPTY_AOI", "asset_preflight", "AOI is empty or has no valid area geometry.")
    if _js_number(report.get("trainingFeatures") or 0) < 1:
        raise EngineError("EMPTY_TRAINING", "asset_preflight", "Training asset contains no features.")
    info = build_class_lookup(report.get("classHistogram") or {})
    represented = sorted(info["counts"])
    if not represented or info["total"] < 4:
        raise EngineError("INVALID_CLASSES", "asset_preflight", "No usable class codes 1-12 or fewer than four usable features.")
    if len(represented) < 2:
        raise EngineError("INSUFFICIENT_CLASSES", "asset_preflight", "At least two represented classes are required.")
    too_small = [code for code in represented if info["counts"][code] < 2]
    if too_small:
        raise EngineError("INSUFFICIENT_CLASS_SAMPLES", "asset_preflight",
                          f"Class codes with fewer than two usable features: {too_small}.")
    return info


def coverage_missing(config, coverage):
    missing = []
    for year in config.years:
        for prefix, label in (("train", "training area"), ("aoi", "AOI")):
            count = _js_number(coverage.get(f"{prefix}_{year}") or 0)
            if year == config.target_year:
                fallback = _js_number(coverage.get(f"{prefix}_{config.fallback_year}") or 0)
                if count < 1 and fallback < 1:
                    missing.append(f"{label} {year}/{config.fallback_year}")
            elif count < 1:
                missing.append(f"{label} {year}")
    return missing


def _emit(on_event, phase, **details):
    if on_event:
        on_event({"phase": phase, **details})


def embedding_collection(year, geometry):
    start = ee.Date.fromYMD(year, 1, 1)
    result = ee.ImageCollection(EMBEDDING_COLLECTION).filterDate(start, start.advance(1, "year"))
    return result.filterBounds(geometry) if geometry is not None else result


def get_embedding(year, geometry=None):
    return embedding_collection(year, geometry).mosaic()


def build_embeddings(config, geometry):
    result = {}
    for year in config.years:
        image = get_embedding(year, geometry)
        if year == config.target_year:
            image = image.unmask(get_embedding(config.fallback_year, geometry))
        result[year] = image
    return result


def terrain_image():
    dem = ee.Image(SRTM_IMAGE)
    return ee.Image.cat([
        dem.select("elevation").unmask(0), ee.Terrain.slope(dem).unmask(0),
        ee.Terrain.aspect(dem).unmask(0),
    ]).rename(["elevation", "slope", "aspect"])


def _normalize_training(raw, config, class_info):
    lookup = ee.Dictionary(class_info["lookup"])
    def normalize(feature):
        feature = ee.Feature(feature)
        code = ee.Number(lookup.get(ee.String(feature.get(config.class_field)), -999999))
        return feature.set(config.class_field, code)
    return raw.filter(ee.Filter.notNull([config.class_field])).map(normalize).filter(
        ee.Filter.inList(config.class_field, list(CLASS_VALUES)))


def _load_checked_assets(config):
    _require_ee()
    try:
        roi, raw = ee.FeatureCollection(config.aoi_asset), ee.FeatureCollection(config.training_asset)
        report = ee.Dictionary({"aoiFeatures": roi.size(), "aoiAreaM2": roi.geometry().area(1),
                                "trainingFeatures": raw.size(),
                                "classHistogram": raw.aggregate_histogram(config.class_field)}).getInfo()
    except Exception as exc:
        raise EngineError("ASSET_ACCESS_OR_SCHEMA", "asset_preflight",
                          "The AOI/training asset or class schema could not be read.", details={"cause":str(exc)}) from exc
    class_info = validate_asset_report(report)
    return roi, _normalize_training(raw, config, class_info), report


def load_assets(config):
    config = normalized_config(config)
    roi, points, _ = _load_checked_assets(config)
    return roi, points


@dataclass(frozen=True)
class PreparedInputs:
    config: LandCoverConfig
    roi: Any
    points: Any
    terrain: Any
    national_embeddings: Dict[int, Any]
    aoi_embeddings: Dict[int, Any]
    asset_report: dict
    coverage: dict


def prepare_inputs(config, on_event=None):
    config = normalized_config(config)
    _emit(on_event, "asset_preflight")
    roi, points, asset_report = _load_checked_assets(config)
    _emit(on_event, "coverage_preflight")
    training_geometry, aoi_geometry = points.geometry(), roi.geometry()
    years = list(config.years)
    if config.fallback_year not in years:
        years.append(config.fallback_year)
    try:
        counts = {}
        for year in years:
            counts[f"train_{year}"] = embedding_collection(year, training_geometry).size()
            counts[f"aoi_{year}"] = embedding_collection(year, aoi_geometry).size()
        coverage = ee.Dictionary(counts).getInfo()
        if not isinstance(coverage, dict) or not coverage:
            raise ValueError("No coverage result returned")
    except Exception as exc:
        raise EngineError("COVERAGE_QUERY_FAILED", "coverage_preflight",
                          "Could not query annual embedding coverage.", details={"cause":str(exc)}) from exc
    missing = coverage_missing(config, coverage)
    if missing:
        raise EngineError("COVERAGE_UNAVAILABLE", "coverage_preflight",
                          "Embedding coverage is unavailable for: " + "; ".join(missing))
    return PreparedInputs(config, roi, points, terrain_image(),
                          build_embeddings(config, training_geometry.bounds(1)),
                          build_embeddings(config, aoi_geometry.bounds(1)), asset_report, coverage)


def stratified_split(points, config, seed):
    classes = points.aggregate_array(config.class_field).distinct().sort()
    def split_class(class_value):
        class_points = points.filter(ee.Filter.eq(config.class_field, ee.Number(class_value))).randomColumn(
            "_flex_random", seed).sort("_flex_random")
        count = class_points.size()
        train_count = count.multiply(config.train_fraction).floor().max(1).min(count.subtract(1))
        features = class_points.toList(count)
        return ee.Dictionary({"train": ee.FeatureCollection(features.slice(0, train_count)),
                              "val": ee.FeatureCollection(features.slice(train_count, count))})
    pieces = classes.map(split_class)
    return (ee.FeatureCollection(pieces.map(lambda item: ee.Dictionary(item).get("train"))).flatten(),
            ee.FeatureCollection(pieces.map(lambda item: ee.Dictionary(item).get("val"))).flatten())


def temporal_decision(yearly_dictionary: Dict[int, ee.Image], config: LandCoverConfig) -> ee.Image:
    """Apply the documented modal + cultivated-class temporal priority rules."""
    stack = ee.Image.cat([yearly_dictionary[y].rename(f"y{y}") for y in config.years])
    priority = stack.select(f"y{config.target_year}")
    standard = stack.reduce(ee.Reducer.mode())
    class4_count = ee.Image.constant(0)
    class5_count = ee.Image.constant(0)
    for year in config.years:
        band = stack.select(f"y{year}")
        class4_count = class4_count.add(band.eq(4))
        class5_count = class5_count.add(band.eq(5))
    return (
        standard.where(priority.eq(4).Or(priority.eq(5)), priority)
        .where(class5_count.gte(2), 5)
        .where(class4_count.gte(2), 4)
        .where(class4_count.gte(2).And(class5_count.gte(2)), priority)
        .rename("classification")
    )


def build_seed_model(config, seed, *, prepared=None):
    """Build one candidate from the final GEE path; prepare only when needed."""
    config = normalized_config(config)
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    prepared = prepared if prepared is not None else prepare_inputs(config)
    if prepared.config != config:
        raise ValueError("Prepared inputs belong to another configuration")
    roi, points, terrain = prepared.roi, prepared.points, prepared.terrain
    train, validation_points = stratified_split(points, config, seed)
    yearly_national, yearly_aoi, classifiers = {}, {}, {}
    for year in config.years:
        national = ee.Image.cat([prepared.national_embeddings[year], terrain])
        aoi = ee.Image.cat([prepared.aoi_embeddings[year], terrain])
        bands = national.bandNames()
        samples = national.sampleRegions(collection=train, properties=[config.class_field],
                                        scale=config.scale_m, tileScale=config.tile_scale,
                                        geometries=False).filter(ee.Filter.notNull(bands))
        classifier = ee.Classifier.smileRandomForest(
            numberOfTrees=config.trees, bagFraction=config.bag_fraction, seed=seed
        ).train(features=samples, classProperty=config.class_field, inputProperties=bands)
        classifiers[year] = classifier
        yearly_national[year] = national.classify(classifier).rename(f"c{year}")
        # Match the reference clip call; do not substitute national predictors.
        yearly_aoi[year] = aoi.classify(classifier).rename(f"c{year}").clip(roi)
    validation_map = temporal_decision(yearly_national, config)
    final_map = temporal_decision(yearly_aoi, config).clip(roi)
    sampled = validation_map.sampleRegions(collection=validation_points, properties=[config.class_field],
                                          scale=config.scale_m, tileScale=config.tile_scale, geometries=False)
    matrix = sampled.errorMatrix(config.class_field, "classification", list(CLASS_VALUES))
    return {"seed":seed, "roi":roi, "points":points, "train":train,
            "validation_points":validation_points, "sampled_validation_count":sampled.size(),
            "embeddings":prepared.national_embeddings, "aoi_embeddings":prepared.aoi_embeddings,
            "terrain":terrain, "classifiers":classifiers, "yearly":yearly_aoi,
            "validation_map":validation_map, "final_map":final_map, "error_matrix":matrix}


def metrics_dictionary(model):
    matrix = ee.ConfusionMatrix(model["error_matrix"])
    return ee.Dictionary({"overall":matrix.accuracy(), "kappa":matrix.kappa(),
                          "producer":matrix.producersAccuracy(), "confusion":matrix.array(),
                          "sampled_validation_count":model["sampled_validation_count"]})


def _array_values(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        # Object.values orders integer-index keys first, then other insertion keys.
        indexes = sorted((k for k in value if re.fullmatch(r"0|[1-9][0-9]*", str(k))
                          and int(k) < 2**32 - 1), key=int)
        return [value[k] for k in indexes] + [v for k,v in value.items() if k not in indexes]
    return []


def _flatten_vector(value):
    values = _array_values(value)
    if len(values) == 1 and isinstance(values[0], list):
        values = values[0]
    return [_js_number(v) for v in values]


def score_metrics(config, seed, payload):
    """Port the reference client-side conversion/score; do not redesign metrics."""
    producer = _flatten_vector(payload.get("producer"))
    confusion = _array_values(payload.get("confusion"))
    if len(confusion) == 1 and isinstance(confusion[0], list) and confusion[0] and isinstance(confusion[0][0], list):
        confusion = confusion[0]
    score, reached, scored = 100.0, True, 0
    for index, code in enumerate(CLASS_VALUES):
        row = confusion[index] if index < len(confusion) else []
        row_samples = sum(_js_number(v or 0) for v in row)
        if row_samples <= 0 or code == config.excluded_class_from_threshold:
            continue
        accuracy = (producer[index] if index < len(producer) else float("nan")) * 100
        if not math.isfinite(accuracy):
            continue
        scored += 1
        score = min(score, accuracy)
        if accuracy < config.target_accuracy_percent:
            reached = False
    if not scored:
        raise EngineError("NO_SCORED_CLASSES", "seed_search", f"Seed {seed} produced no usable validation samples.")
    return {"overall":_js_number(payload.get("overall", _MISSING)),
            "kappa":_js_number(payload.get("kappa", _MISSING)), "producer":producer,
            "confusion":confusion, "sampled_validation_count":payload.get("sampled_validation_count"),
            "minimum_producer_percent":score, "target_reached":reached, "seed":seed}


def _evaluate_model(config, seed, model):
    try:
        payload = metrics_dictionary(model).getInfo()
    except Exception as exc:
        raise EngineError("SEED_EVALUATION_FAILED", "seed_search",
                          f"Seed {seed} did not return a metric result.", details={"cause":str(exc)}) from exc
    if not isinstance(payload, dict) or not payload:
        raise EngineError("SEED_EVALUATION_FAILED", "seed_search", f"Seed {seed} returned no validation result.")
    return score_metrics(config, seed, payload)


def evaluate_seed(config, seed):
    config = normalized_config(config)
    model = build_seed_model(config, seed)
    return _evaluate_model(config, seed, model)


def search_seeds(config, seeds=None, stop_when_target_reached=True, *, on_event=None):
    """Sequential reference search. Preserve selected graph; no second build."""
    config = normalized_config(config)
    candidates = tuple(seeds) if seeds is not None else config.seeds
    if not candidates or any(type(seed) is not int for seed in candidates):
        raise ValueError("Provide at least one integer candidate seed")
    prepared = prepare_inputs(config, on_event=on_event)
    best, best_model, history, last_error = None, None, [], None
    for index, seed in enumerate(candidates, 1):
        _emit(on_event, "seed_search", seed_index=index, seed_count=len(candidates), current_seed=seed)
        # Reference catches evaluation failures, not every programming/graph error.
        model = build_seed_model(config, seed, prepared=prepared)
        try:
            metrics = _evaluate_model(config, seed, model)
        except EngineError as exc:
            if exc.code not in {"SEED_EVALUATION_FAILED", "NO_SCORED_CLASSES"}:
                raise
            last_error = exc
            history.append({"seed":seed, "status":"failed", "code":exc.code, "message":str(exc)})
            continue
        history.append({"seed":seed, "status":"completed", "metrics":metrics})
        if best is None or metrics["minimum_producer_percent"] > best["minimum_producer_percent"]:
            best, best_model = metrics, model
        if stop_when_target_reached and metrics["target_reached"]:
            break
    if best is None:
        message = "No Random Forest seed completed successfully."
        if last_error:
            message += " " + str(last_error)
        raise EngineError("NO_SUCCESSFUL_SEED", "seed_search", message,
                          details={"history":history, "last_error":last_error.details if last_error else {}})
    _emit(on_event, "preparing_result")
    return {"best_metrics":best, "history":history, "model":best_model,
            "config":config, "asset_report":prepared.asset_report, "coverage":prepared.coverage}


def libya_boundary() -> ee.FeatureCollection:
    """Public Libya boundary used only for portable notebook diagnostics."""
    return ee.FeatureCollection("FAO/GAUL/2015/level0").filter(
        ee.Filter.eq("ADM0_NAME", "Libya")
    )


def start_drive_export(
    classification: ee.Image,
    config: LandCoverConfig,
    description: str | None = None,
    folder: str = "LandCover_Exports",
) -> ee.batch.Task:
    config = normalized_config(config)
    roi = ee.FeatureCollection(config.aoi_asset)
    name = description or f"libya_landcover_{config.target_year}"
    task = ee.batch.Export.image.toDrive(
        image=ee.Image(classification).rename("classification").toUint8(),
        description=name,
        folder=folder,
        fileNamePrefix=name,
        region=roi.geometry(),
        scale=config.scale_m,
        maxPixels=1e13,
        fileFormat="GeoTIFF",
    )
    task.start()
    return task


def public_input_smoke_test(year: int = 2024) -> Dict[str, Any]:
    """Small public-data check suitable for Colab before private assets are used."""
    boundary = libya_boundary()
    start = ee.Date.fromYMD(int(year), 1, 1)
    collection = (
        ee.ImageCollection(EMBEDDING_COLLECTION)
        .filterDate(start, start.advance(1, "year"))
        .filterBounds(boundary)
    )
    image = collection.mosaic()
    return {
        "year": int(year),
        "image_count": collection.size().getInfo(),
        "band_count": image.bandNames().size().getInfo(),
        "first_bands": image.bandNames().slice(0, 5).getInfo(),
    }


def configuration_summary(config: LandCoverConfig) -> str:
    validate_config(config)
    return (
        f"Years: {list(config.years)} | target={config.target_year} | "
        f"fallback={config.fallback_year} | RF trees={config.trees} | "
        f"train fraction={config.train_fraction:.2f} | scale={config.scale_m:g} m"
    )


def asset_diagnostics(config: LandCoverConfig) -> ee.Dictionary:
    """Return lightweight diagnostics for the configured personal EE assets."""
    validate_config(config)
    roi, points = load_assets(config)
    return ee.Dictionary({
        "aoi_features": roi.size(),
        "training_points": points.size(),
        "classes": points.aggregate_array(config.class_field).distinct().sort(),
        "years": list(config.years),
        "target_year": config.target_year,
        "fallback_year": config.fallback_year,
    })
