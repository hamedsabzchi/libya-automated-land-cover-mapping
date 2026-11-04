"""One bounded delivery experiment, with portable recovery and private diagnostics.

No classifier/search modification, full-area scheduler, or automatic task start.
"""

import json
import math
from pathlib import Path
import stat
import tempfile
from uuid import NAMESPACE_URL, uuid5
import zipfile

from .bundle import write_json
from .exports import export_spec, window_bounds, enqueue_export, recover_export
from .job_store import encoded, now
from .jobs import MAX_BUNDLE_BYTES, validate_bundle, bundle_digest, import_bundle, checked_mapping_bundle


def adopt_archive(store, archive):
    """Read a WP04 ZIP, WP05 backup or pilot handoff without restoring uploaded SQL.

    Only a validated completed mapping bundle is imported. Old operations remain
    remote and untouched; context records are returned as references, not commands.
    """
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)) or len(names) > 500 or sum(i.file_size for i in members) > MAX_BUNDLE_BYTES:
            raise ValueError("Duplicate/excessive entries or oversized archive")
        for item in members:
            path = Path(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Unsafe archive member")
        context = None
        previous = None
        if "run/result.json" in names:
            checked = validate_bundle(lambda name: source.read("run/" + name))
            if "pilot-context.json" in names:
                context = json.loads(source.read("pilot-context.json"))
                if context.get("schema_version") != "wp05-pilot.1":
                    raise ValueError("Unsupported pilot context")
                if context.get("bundle_digest") != bundle_digest(checked):
                    raise ValueError("Pilot context belongs to another mapping bundle")
                context["recovery_history"] = {
                    "events": json.loads(source.read("pilot-events.json")),
                    "previous": json.loads(source.read("pilot/recovered-history.json"))
                    if "pilot/recovered-history.json" in names else None,
                }
                context["recovery_diagnostics"] = {
                    name.split("/")[-1]: json.loads(source.read(name)) for name in names
                    if name.startswith("pilot/diagnostic-") and name.endswith(".json")
                }
                if "pilot/recovered-diagnostics.json" in names:
                    context["recovery_diagnostics"].update(json.loads(source.read("pilot/recovered-diagnostics.json")))
                if "pilot/source-manifest.json" in names:
                    context["source_manifest"] = json.loads(source.read("pilot/source-manifest.json"))
        elif "export-manifest.json" in names:
            previous = json.loads(source.read("export-manifest.json"))
            from .bundle import canonical_uuid
            mapping = previous["mapping"]
            identifier = canonical_uuid(mapping["job_id"])
            checked = validate_bundle(lambda name: source.read("jobs/" + identifier + "/bundle/" + name))
            if (mapping.get("state") != "completed" or
                    mapping.get("run_id") != checked["result"].to_dict()["run_id"] or
                    mapping.get("inputs", {}).get("bundle_digest") != bundle_digest(checked)):
                raise ValueError("WP05 mapping manifest does not match its bundle")
        else:
            raise ValueError("Upload a completed WP04 ZIP, WP05 backup, or pilot handoff")
        # All expected graph files are verified before any persistent mapping job
        # is created. No extractall, pickle, uploaded code or uploaded DB execution.
        with tempfile.TemporaryDirectory() as temporary:
            normalized = Path(temporary) / "mapping.zip"
            with zipfile.ZipFile(normalized, "w", zipfile.ZIP_DEFLATED) as target:
                for name, data in checked["files"].items():
                    target.writestr("run/" + name, data)
            mapping = import_bundle(store, normalized)
    return {"mapping": mapping, "context": context, "previous_manifest": previous}


def centered_spec(center_xy, *, side=1024, crs="EPSG:32633", transform=None):
    """Snap the window to existing pixel edges; never shift the parent grid."""
    if type(side) is not int or not 1 <= side <= 1024:
        raise ValueError("Pilot side must be an integer from 1 to 1024")
    if (not isinstance(center_xy, (list, tuple)) or len(center_xy) != 2 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in center_xy)):
        raise ValueError("Expected a finite projected centre")
    transform = [10, 0, 0, 0, -10, 0] if transform is None else transform
    base = export_spec({"crs": crs, "transform": transform})
    x, y = center_xy
    return export_spec({**base, "folder_prefix": "LibyaLandCover_Pilot", "file_dimensions": 1024,
        "max_pixels": 1100000, "pixel_window": {
            "column": math.floor((x - transform[2]) / 10) - side // 2,
            "row": math.floor((transform[5] - y) / 10) - side // 2,
            "width": side, "height": side}})


def plan_pilot(store, mapping_job_id, *, side=1024, center_wgs84=None):
    """Geometry-only preflight. No raster evaluation, seed search or export.

    Centroid selection is a delivery smoke test, not a representative accuracy
    sample. A user-specified lon/lat centre can be used for a disjoint AOI.
    """
    import ee
    mapping = store.get(mapping_job_id)
    checked = checked_mapping_bundle(store, mapping)
    if mapping["state"] != "completed":
        raise ValueError("Pilot requires a completed mapping")
    ee.Initialize(project=checked["manifest"]["project"])
    aoi = ee.FeatureCollection(checked["request"].to_dict()["aoi_asset"]).geometry()
    projection = ee.Projection("EPSG:32633")
    if center_wgs84 is None:
        centre = aoi.centroid(maxError=1, proj=projection)
    else:
        if (not isinstance(center_wgs84, (tuple, list)) or len(center_wgs84) != 2 or
                any(type(x) not in (float, int) or not math.isfinite(x) for x in center_wgs84) or
                not -180 <= center_wgs84[0] <= 180 or not -90 <= center_wgs84[1] <= 90):
            raise ValueError("Expected centre [longitude, latitude]")
        centre = ee.Geometry.Point(center_wgs84).transform(projection, 1)
    center_xy = centre.coordinates().getInfo()
    spec = centered_spec(center_xy, side=side)
    rectangle = ee.Geometry.Rectangle(window_bounds(spec), proj=spec["crs"], geodesic=False)
    overlap = rectangle.intersection(aoi, maxError=1, proj=projection).area(maxError=1, proj=projection).getInfo()
    if type(overlap) not in (float, int) or not math.isfinite(overlap) or overlap <= 0:
        raise ValueError("Pilot does not overlap AOI; choose center_wgs84 inside the actual region")
    return {"spec": spec, "center_xy": center_xy, "bounds_xy": window_bounds(spec),
            "aoi_overlap_m2": overlap, "pixel_count": side * side,
            "selection": "aoi_centroid" if center_wgs84 is None else "explicit_center",
            "valid_raster_pixels_verified": False}


def pilot_request_id(checked, artifact_id, spec):
    spec = export_spec(spec)
    if "pixel_window" not in spec:
        raise ValueError("Pilot must have an explicit bounded pixel_window")
    index = json.loads(checked["files"]["graphs/index.json"])
    identity = {"project": checked["manifest"]["project"], "run_id": checked["result"].to_dict()["run_id"],
                "artifact_id": artifact_id, "graph_sha256": index["artifacts"][artifact_id]["sha256"], "spec": spec}
    return str(uuid5(NAMESPACE_URL, "libya-wp05-pilot:" + encoded(identity)))


def create_pilot(store, mapping_job_id, artifact_id, plan):
    checked = checked_mapping_bundle(store, store.get(mapping_job_id))
    request_id = pilot_request_id(checked, artifact_id, plan["spec"])
    return enqueue_export(store, mapping_job_id, artifact_id, plan["spec"], request_id=request_id)


def recover_pilot(store, mapping_job_id, context, *, backend=None):
    """Recreate identity from a checked handoff and reattach its remote operation."""
    checked = checked_mapping_bundle(store, store.get(mapping_job_id))
    if context.get("bundle_digest") != bundle_digest(checked):
        raise ValueError("Pilot recovery bundle differs")
    old = context["export"]
    if context["plan"]["spec"] != old["inputs"]["spec"]:
        raise ValueError("Pilot recovery spec differs")
    artifact_id = old["inputs"]["artifact_id"]
    request_id = pilot_request_id(checked, artifact_id, context["plan"]["spec"])
    if old["ee_request_id"] != request_id:
        raise ValueError("Pilot recovery identity differs")
    job = create_pilot(store, mapping_job_id, artifact_id, context["plan"])
    folder = store.folder(job["job_id"])
    folder.mkdir(parents=True, exist_ok=True)
    for key, filename in (("recovery_history", "recovered-history.json"),
                          ("recovery_diagnostics", "recovered-diagnostics.json"),
                          ("source_manifest", "source-manifest.json")):
        if key in context:
            write_json(folder / filename, context[key])
    if old.get("operation_name"):
        return recover_export(store, job["job_id"], old["operation_name"], backend=backend)
    # No known operation: retain uncertainty so submit reconciles before retrying
    # with the same identity. An explicitly cancelled/failed local job stays so.
    if job["state"] == "queued" and old["state"] != "queued":
        state = old["state"] if old["state"] in {"cancelled", "failed"} else "submission_unknown"
        job = store.update(job, state=state)
    return job


def save_diagnostic(store, job_id, *, backend=None):
    """Preserve raw operation evidence privately; never submit or cancel work."""
    from .exports import EarthEngineBackend
    job = store.get(job_id)
    folder = store.folder(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    record = {"observed_at": now(), "job_id": job_id, "operation_name": job.get("operation_name")}
    if job.get("operation_name"):
        try:
            client = backend if backend is not None else EarthEngineBackend(job["inputs"]["project"])
            record["operation"] = client.get(job["operation_name"])
        except Exception as exc:
            record["lookup_error_type"] = type(exc).__name__
    else:
        record["note"] = "No operation recorded; submission has not been confirmed"
    stamp = record["observed_at"].replace(":", "").replace(".", "")
    write_json(folder / ("diagnostic-" + stamp + ".json"), record)
    return record


def save_handoff(store, job_id, plan, destination, *, service_commit, original_operation=None):
    """Portable scoped ZIP, without credentials; no remote calls required.

    Contains a standard checked run/ bundle for reimport, exact pilot identity,
    accumulated local history and raw diagnostics. No uploaded DB is restored.
    """
    job = store.get(job_id)
    mapping = store.get(job["inputs"]["mapping_job_id"])
    checked = checked_mapping_bundle(store, mapping)
    if pilot_request_id(checked, job["inputs"]["artifact_id"], plan["spec"]) != job["ee_request_id"]:
        raise ValueError("Handoff plan does not match the pilot job")
    context = {"schema_version": "wp05-pilot.1", "created_at": now(), "service_commit": service_commit,
               "bundle_digest": bundle_digest(checked), "mapping": mapping, "export": job, "plan": plan,
               "original_operation": original_operation, "raster_included": False}
    folder = store.folder(job_id)
    destination = Path(destination)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in checked["files"].items():
            target.writestr("run/" + name, data)
        target.writestr("pilot-context.json", json.dumps(context, indent=2, allow_nan=False))
        target.writestr("pilot-events.json", json.dumps(store.events(job_id), indent=2, allow_nan=False))
        for pattern in ("diagnostic-*.json", "export-request.json", "recovered-history.json",
                        "recovered-diagnostics.json", "source-manifest.json", "original-operation.json"):
            for path in folder.glob(pattern):
                target.writestr("pilot/" + path.name, path.read_bytes())
    temporary.replace(destination)
    return context
