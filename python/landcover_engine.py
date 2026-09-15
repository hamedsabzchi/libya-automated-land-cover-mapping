"""Core Earth Engine logic for the Libya automated land-cover mapping project.

The module mirrors the modeling core of the reference JavaScript application:
annual Google Satellite Embedding predictors + SRTM terrain, class-stratified
hold-out splitting, per-year Random Forests, and the documented temporal rules.

This is an independent personal technical portfolio project by
Hamed Sabzchi Dehkharghani.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

import ee

EMBEDDING_COLLECTION = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"
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


def validate_config(config: LandCoverConfig) -> None:
    if not config.aoi_asset.strip():
        raise ValueError("AOI asset is empty.")
    if not config.training_asset.strip():
        raise ValueError("Training asset is empty.")
    if not config.class_field.strip():
        raise ValueError("Class field is empty.")
    if not EMBEDDING_FIRST_YEAR <= config.target_year <= EMBEDDING_LAST_YEAR:
        raise ValueError(f"target_year must be within {EMBEDDING_FIRST_YEAR}-{EMBEDDING_LAST_YEAR}.")
    if not EMBEDDING_FIRST_YEAR <= config.fallback_year <= EMBEDDING_LAST_YEAR:
        raise ValueError(f"fallback_year must be within {EMBEDDING_FIRST_YEAR}-{EMBEDDING_LAST_YEAR}.")
    if not 1 <= config.year_count <= 20:
        raise ValueError("year_count must be between 1 and 20.")
    if config.years[-1] < EMBEDDING_FIRST_YEAR:
        raise ValueError(
            "The selected annual window extends before available Satellite "
            f"Embedding coverage ({EMBEDDING_FIRST_YEAR})."
        )
    if not 0.01 <= config.train_fraction <= 0.99:
        raise ValueError("train_fraction must be between 0.01 and 0.99.")
    if not 1 <= config.trees <= 5000:
        raise ValueError("trees must be between 1 and 5000.")
    if not 0.01 <= config.bag_fraction <= 1.0:
        raise ValueError("bag_fraction must be between 0.01 and 1.0.")
    if not 0 <= config.target_accuracy_percent <= 100:
        raise ValueError("target_accuracy_percent must be between 0 and 100.")
    if config.scale_m <= 0:
        raise ValueError("scale_m must be positive.")
    if not 1 <= config.tile_scale <= 64:
        raise ValueError("tile_scale must be between 1 and 64.")
    if not config.seeds:
        raise ValueError("At least one random seed is required.")


def libya_boundary() -> ee.FeatureCollection:
    """Public Libya boundary used only for portable notebook diagnostics."""
    return ee.FeatureCollection("FAO/GAUL/2015/level0").filter(
        ee.Filter.eq("ADM0_NAME", "Libya")
    )


def get_embedding(year: int, geometry: ee.Geometry | None = None) -> ee.Image:
    """Return the annual 64-D Satellite Embedding mosaic for one year."""
    if not EMBEDDING_FIRST_YEAR <= int(year) <= EMBEDDING_LAST_YEAR:
        raise ValueError(f"Embedding year must be within {EMBEDDING_FIRST_YEAR}-{EMBEDDING_LAST_YEAR}.")
    start = ee.Date.fromYMD(int(year), 1, 1)
    collection = ee.ImageCollection(EMBEDDING_COLLECTION).filterDate(
        start, start.advance(1, "year")
    )
    if geometry is not None:
        collection = collection.filterBounds(geometry)
    return collection.mosaic()


def terrain_image() -> ee.Image:
    dem = ee.Image(SRTM_IMAGE)
    return ee.Image.cat(
        [dem.select("elevation"), ee.Terrain.slope(dem), ee.Terrain.aspect(dem)]
    ).rename(["elevation", "slope", "aspect"])


def load_assets(config: LandCoverConfig) -> Tuple[ee.FeatureCollection, ee.FeatureCollection]:
    """Load AOI and normalize valid integer class labels in the training points."""
    validate_config(config)
    roi = ee.FeatureCollection(config.aoi_asset)
    raw = ee.FeatureCollection(config.training_asset)

    def normalize(feature: ee.Feature) -> ee.Feature:
        feature = ee.Feature(feature)
        return feature.set(
            config.class_field,
            ee.Number.parse(ee.String(feature.get(config.class_field))),
        )

    points = raw.map(normalize).filter(
        ee.Filter.inList(config.class_field, list(CLASS_VALUES))
    )
    return roi, ee.FeatureCollection(points)


def processing_geometry(roi: ee.FeatureCollection, points: ee.FeatureCollection) -> ee.Geometry:
    training_bounds = points.geometry().bounds(1)
    roi_bounds = roi.geometry().bounds(1)
    return training_bounds.union(roi_bounds, 1)


def build_embeddings(config: LandCoverConfig, geometry: ee.Geometry) -> Dict[int, ee.Image]:
    validate_config(config)
    result: Dict[int, ee.Image] = {}
    for year in config.years:
        image = get_embedding(year, geometry)
        if year == config.target_year:
            image = image.unmask(get_embedding(config.fallback_year, geometry))
        result[year] = image
    return result


def stratified_split(
    points: ee.FeatureCollection, config: LandCoverConfig, seed: int
) -> Tuple[ee.FeatureCollection, ee.FeatureCollection]:
    train = ee.FeatureCollection([])
    validation = ee.FeatureCollection([])
    for class_value in CLASS_VALUES:
        class_points = points.filter(
            ee.Filter.eq(config.class_field, class_value)
        ).randomColumn("random", int(seed))
        train = train.merge(
            class_points.filter(ee.Filter.lt("random", config.train_fraction))
        )
        validation = validation.merge(
            class_points.filter(ee.Filter.gte("random", config.train_fraction))
        )
    return train, validation


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


def build_seed_model(config: LandCoverConfig, seed: int) -> Dict[str, Any]:
    """Build one candidate seed model and its server-side validation objects."""
    validate_config(config)
    roi, points = load_assets(config)
    geometry = processing_geometry(roi, points)
    terrain = terrain_image()
    embeddings = build_embeddings(config, geometry)
    train, validation_points = stratified_split(points, config, int(seed))

    yearly_national: Dict[int, ee.Image] = {}
    yearly_aoi: Dict[int, ee.Image] = {}
    classifiers: Dict[int, ee.Classifier] = {}

    for year in config.years:
        predictor = ee.Image.cat([embeddings[year], terrain])
        band_names = predictor.bandNames()
        samples = predictor.sampleRegions(
            collection=train,
            properties=[config.class_field],
            scale=config.scale_m,
            tileScale=config.tile_scale,
            geometries=False,
        ).filter(ee.Filter.notNull(band_names))
        classifier = ee.Classifier.smileRandomForest(
            numberOfTrees=config.trees,
            bagFraction=config.bag_fraction,
            seed=int(seed),
        ).train(
            features=samples,
            classProperty=config.class_field,
            inputProperties=band_names,
        )
        classified = predictor.classify(classifier).rename(f"c{year}")
        classifiers[year] = classifier
        yearly_national[year] = classified
        yearly_aoi[year] = classified.clipToCollection(roi)

    validation_map = temporal_decision(yearly_national, config)
    final_map = validation_map.clipToCollection(roi)
    sampled_validation = validation_map.sampleRegions(
        collection=validation_points,
        properties=[config.class_field],
        scale=config.scale_m,
        tileScale=config.tile_scale,
        geometries=False,
    )
    error_matrix = sampled_validation.errorMatrix(
        config.class_field, "classification", list(CLASS_VALUES)
    )

    return {
        "seed": int(seed),
        "roi": roi,
        "points": points,
        "train": train,
        "validation_points": validation_points,
        "embeddings": embeddings,
        "terrain": terrain,
        "classifiers": classifiers,
        "yearly": yearly_aoi,
        "validation_map": validation_map,
        "final_map": final_map,
        "error_matrix": error_matrix,
    }


def metrics_dictionary(model: Dict[str, Any]) -> ee.Dictionary:
    matrix = ee.ConfusionMatrix(model["error_matrix"])
    return ee.Dictionary(
        {
            "overall": matrix.accuracy(),
            "kappa": matrix.kappa(),
            "producer": matrix.producersAccuracy(),
            "user": matrix.consumersAccuracy(),
            "confusion": matrix.array(),
        }
    )


def _flatten_vector(value: Any) -> list[float]:
    while isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list):
        raise ValueError("Expected an accuracy vector from Earth Engine.")
    return [float(v) for v in value]


def evaluate_seed(config: LandCoverConfig, seed: int) -> Dict[str, Any]:
    model = build_seed_model(config, seed)
    metrics = metrics_dictionary(model).getInfo()
    producer = _flatten_vector(metrics["producer"])
    included = [
        p * 100.0
        for code, p in zip(CLASS_VALUES, producer)
        if code != config.excluded_class_from_threshold
    ]
    minimum_producer = min(included) if included else float("nan")
    metrics["producer"] = producer
    metrics["minimum_producer_percent"] = minimum_producer
    metrics["target_reached"] = minimum_producer >= config.target_accuracy_percent
    metrics["seed"] = int(seed)
    return metrics


def search_seeds(
    config: LandCoverConfig,
    seeds: Iterable[int] | None = None,
    stop_when_target_reached: bool = True,
) -> Dict[str, Any]:
    """Evaluate candidate seeds using the JavaScript model-selection criterion."""
    validate_config(config)
    candidates = tuple(seeds) if seeds is not None else config.seeds
    if not candidates:
        raise ValueError("No candidate seeds were provided.")

    best: Dict[str, Any] | None = None
    history: list[Dict[str, Any]] = []
    for seed in candidates:
        metrics = evaluate_seed(config, int(seed))
        history.append(metrics)
        if best is None or metrics["minimum_producer_percent"] > best["minimum_producer_percent"]:
            best = metrics
        if stop_when_target_reached and metrics["target_reached"]:
            break

    assert best is not None
    selected_model = build_seed_model(config, int(best["seed"]))
    return {"best_metrics": best, "history": history, "model": selected_model}


def start_drive_export(
    classification: ee.Image,
    config: LandCoverConfig,
    description: str | None = None,
    folder: str = "LandCover_Exports",
) -> ee.batch.Task:
    validate_config(config)
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
