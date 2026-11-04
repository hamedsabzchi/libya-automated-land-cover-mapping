"""Bounded observations of implementation behavior, not model quality tests."""

from copy import deepcopy
import math

from contracts import RunRequest
from contracts.models import GEE_SHA256

CONFIG_INPUTS = ("aoi_asset", "training_asset", "class_field", "target_year", "year_count",
                 "fallback_year", "train_fraction", "trees")
REQUIRED_OBSERVATIONS = ("config", "selection", "metrics", "splits", "raster_probes")


def years(request):
    value = request.to_dict()
    return range(value["target_year"], value["target_year"] - value["year_count"], -1)


def validate_probes(spec):
    if not isinstance(spec, dict) or set(spec) != {"crs", "transform", "points"}:
        raise ValueError("Probes require crs, transform and points")
    if not isinstance(spec["crs"], str) or not spec["crs"].strip():
        raise ValueError("Probes need an explicit CRS")
    transform = spec["transform"]
    if (not isinstance(transform, list) or len(transform) != 6 or
            any(type(x) not in (int, float) or not math.isfinite(x) for x in transform)):
        raise ValueError("Probes need six finite affine transform values")
    if transform[0] * transform[4] - transform[1] * transform[3] == 0:
        raise ValueError("Probe transform must be invertible")
    if not isinstance(spec["points"], list) or not 1 <= len(spec["points"]) <= 1000:
        raise ValueError("Provide 1..1000 explicit probe points")
    ids = set()
    for point in spec["points"]:
        if not isinstance(point, dict) or set(point) != {"id", "lon", "lat"}:
            raise ValueError("Each probe requires id, lon and lat")
        if not isinstance(point["id"], str) or not point["id"] or point["id"] in ids:
            raise ValueError("Probe IDs must be nonempty and unique")
        ids.add(point["id"])
        for key, limit in (("lon", 180), ("lat", 90)):
            if type(point[key]) not in (int, float) or not math.isfinite(point[key]) or abs(point[key]) > limit:
                raise ValueError("Probe coordinates must be WGS84 longitude/latitude")
    return deepcopy(spec)


def capture(execution, request, probes=None):
    import ee
    result, model = execution.result.to_dict(), execution.model
    record = {"schema_version": "wp04.1", "source": "python", "gee_sha256": GEE_SHA256,
              "config": request.engine_config(), "selection": result["selection"],
              "metrics": result["metrics"], "splits": None, "raster_probes": None}
    record["splits"] = ee.Dictionary({
        "normalized": model["points"].aggregate_array("system:index").sort(),
        "train": model["train"].aggregate_array("system:index").sort(),
        "validation": model["validation_points"].aggregate_array("system:index").sort(),
    }).getInfo()
    if probes is not None:
        spec = validate_probes(probes)
        points = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([p["lon"], p["lat"]]),
                                                  {"probe_id": p["id"]}) for p in spec["points"]])
        images = [("final", model["final_map"])]
        images += [("y" + str(year), model["yearly"][year]) for year in years(request)]
        bands = []
        for name, image in images:
            image = ee.Image(image)
            bands += [image.unmask(-9999, False).rename(name),
                      image.mask().unmask(0, False).rename(name + "_mask")]
        features = ee.Image.cat(bands).reduceRegions(
            collection=points, reducer=ee.Reducer.first(), crs=spec["crs"],
            crsTransform=spec["transform"], tileScale=16).getInfo()["features"]
        record["raster_probes"] = {"spec": spec, "values": sorted(
            [f["properties"] for f in features], key=lambda v: v["probe_id"])}
    return record


def _valid_record(record, source):
    if not isinstance(record, dict) or record.get("schema_version") != "wp04.1" or record.get("source") != source:
        raise ValueError("Expected wp04.1 evidence with source=" + source)
    if record.get("gee_sha256") != GEE_SHA256:
        raise ValueError("Evidence does not identify the pinned GEE reference")
    cfg = record.get("config")
    if not isinstance(cfg, dict):
        raise ValueError("Missing actual execution configuration")
    request = RunRequest({"request_id": "11111111-1111-4111-8111-111111111111",
                         **{key: cfg[key] for key in CONFIG_INPUTS}})
    if cfg != request.engine_config():
        raise ValueError("Evidence settings differ from the supported reference mode")
    selection, metrics = record.get("selection"), record.get("metrics")
    if selection is not None:
        if (not isinstance(selection, dict) or set(selection) != {
                "seed", "minimum_producer_percent", "target_reached", "stop_reason"} or
                type(selection["seed"]) is not int or selection["seed"] not in cfg["seeds"] or
                type(selection["target_reached"]) is not bool or
                selection["stop_reason"] != ("target_reached" if selection["target_reached"] else "seeds_exhausted")):
            raise ValueError("Invalid selected-seed evidence")
        score = selection["minimum_producer_percent"]
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100:
            raise ValueError("Invalid selected score")
    if metrics is not None:
        if not isinstance(metrics, dict) or set(metrics) != {"overall", "kappa", "producer", "confusion", "sampled_validation_count"}:
            raise ValueError("Incomplete metric observation")
        if not isinstance(metrics["producer"], list) or len(metrics["producer"]) != 12:
            raise ValueError("Expected twelve producer entries")
        for value in [metrics["overall"], metrics["kappa"], *metrics["producer"]]:
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError("Metric values must be finite or null")
        matrix = metrics["confusion"]
        if not isinstance(matrix, list) or len(matrix) != 12 or any(
                not isinstance(row, list) or len(row) != 12 or any(type(x) is not int or x < 0 for x in row) for row in matrix):
            raise ValueError("Expected integer 12 by 12 confusion counts")
        count = metrics["sampled_validation_count"]
        if type(count) is not int or count != sum(map(sum, matrix)):
            raise ValueError("Sample count does not match the recorded matrix")
    splits = record.get("splits")
    if splits is not None:
        if not isinstance(splits, dict) or set(splits) != {"normalized", "train", "validation"} or any(
                not isinstance(v, list) or not v or any(not isinstance(x, str) for x in v) for v in splits.values()):
            raise ValueError("Invalid split-ID observations")
    raster = record.get("raster_probes")
    if raster is not None:
        if not isinstance(raster, dict) or set(raster) != {"spec", "values"}:
            raise ValueError("Invalid raster probes")
        spec = validate_probes(raster["spec"])
        rows = raster["values"]
        names = ["final"] + ["y" + str(year) for year in years(request)]
        expected = {"probe_id", *names, *(name + "_mask" for name in names)}
        if not isinstance(rows, list) or len(rows) != len(spec["points"]):
            raise ValueError("Missing probe rows")
        for row in rows:
            if not isinstance(row, dict) or set(row) != expected:
                raise ValueError("Missing class/mask band in probe row")
            for name in names:
                if type(row[name]) is not int or row[name] not in [-9999, *range(1, 13)]:
                    raise ValueError("Invalid probe class")
                if type(row[name + "_mask"]) not in (int, float) or not 0 <= row[name + "_mask"] <= 1:
                    raise ValueError("Invalid probe mask")
        if sorted(row["probe_id"] for row in rows) != sorted(p["id"] for p in spec["points"]):
            raise ValueError("Probe IDs do not match the supplied locations")


def compare(python_record, gee_record):
    _valid_record(python_record, "python")
    _valid_record(gee_record, "gee")
    differences, missing = [], []

    def walk(left, right, path, tolerant=False):
        if type(left) in (int, float) and type(right) in (int, float):
            equal = math.isclose(left, right, rel_tol=0, abs_tol=1e-9) if tolerant else left == right
        elif isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
            for key in sorted(left):
                walk(left[key], right[key], path + "." + key, tolerant)
            return
        elif isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
            for index, (a, b) in enumerate(zip(left, right)):
                walk(a, b, path + "[" + str(index) + "]", tolerant)
            return
        else:
            equal = type(left) is type(right) and left == right
        if not equal:
            differences.append(path)

    for field in REQUIRED_OBSERVATIONS:
        if python_record.get(field) is None or gee_record.get(field) is None:
            missing.append(field)
        else:
            left, right = deepcopy(python_record[field]), deepcopy(gee_record[field])
            if field == "splits":
                left, right = ({k: sorted(v) for k, v in item.items()} for item in (left, right))
            if field == "raster_probes":
                for item in (left, right):
                    item["values"].sort(key=lambda v: v["probe_id"])
                    item["spec"]["points"].sort(key=lambda v: v["id"])
            walk(left, right, field, field in ("metrics", "selection"))
    return {"schema_version": "wp04.1", "status": "different" if differences else "incomplete" if missing else "observations_match",
            "differences": differences, "missing_observations": missing,
            "numeric_absolute_tolerance": 1e-9, "full_raster_parity_proven": False,
            "scope": "One input case and explicit raster probes only; not a scientific accuracy assessment."}
