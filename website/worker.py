"""Single-request Earth Engine process. No EE state shared between visitors."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import sys

from website.service import EE_SCOPE, json_safe, validate_project


def safe_error(exc):
    """Classify errors without returning tokens or raw HTTP request URLs."""
    text = (str(exc) + " " + str(getattr(exc, "details", ""))).lower()
    if any(s in text for s in ("429", "quota", "restricted mode", "resource_exhausted")):
        return {"code": "QUOTA_LIMIT", "message": "Your Earth Engine project has reached a quota or request limit. Wait or review that project's quota. Repeated mapping will not fix it."}
    if any(s in text for s in ("401", "invalid_grant", "expired", "unauthenticated")) or type(exc).__name__ == "RefreshError":
        return {"code": "AUTH_EXPIRED", "message": "Google authorization has expired or was declined. Download any saved report, then sign out and sign in again."}
    if any(s in text for s in ("403", "permission", "not authorized", "not registered", "access denied", "not found", "404", "insufficient authentication")):
        return {"code": "ACCESS_DENIED", "message": "This Google account cannot access the selected project or assets. Check Earth Engine registration, API enablement, project permissions, asset sharing and consent to the Earth Engine scope."}
    code = getattr(exc, "code", "")
    messages = {
        "COVERAGE_UNAVAILABLE": "Embedding data is unavailable for one or more requested years or locations. Check the target year, fallback year and annual window.",
        "NO_SUCCESSFUL_SEED": "The engine could not complete a candidate model. Check the training data, annual coverage and project quota.",
        "NO_SCORED_CLASSES": "The engine returned no usable validation samples. Check the selected training data and class field.",
    }
    if code in messages:
        return {"code": code, "message": messages[code]}
    return {"code": "EE_REQUEST_FAILED", "message": "Earth Engine could not complete this request. Check project access, input assets and available quota. Your previous result is retained."}


def execute(payload):
    import ee
    from google.oauth2.credentials import Credentials
    from python.landcover_engine import CLASS_PALETTE, LandCoverConfig, normalized_config, search_seeds

    action = payload["action"]
    if action not in {"connect", "map", "display"}:
        raise ValueError("Unknown action")
    token = payload["access_token"]
    if not isinstance(token, str) or not token:
        raise ValueError("Missing access token")
    request = payload["request"]
    project = validate_project(request["project"])
    config = normalized_config(LandCoverConfig(**request["config"]))
    # No ambient credentials, shared credential files, or service-account fallback.
    ee.Initialize(credentials=Credentials(token=token, scopes=[EE_SCOPE]), project=project)
    ee.data.setDeadline(120000)

    if action == "connect":
        for asset in (config.aoi_asset, config.training_asset):
            info = ee.data.getAsset(asset)
            if info.get("type") not in {"TABLE", "FEATURE_COLLECTION"}:
                raise ValueError("Boundary and training assets must be feature collections.")
        return {"project": project, "connected": True}

    if action == "map":
        selected = search_seeds(config)
        model = selected["model"]
        # Save selected graphs and existing metrics BEFORE requesting display tiles.
        # No second training, new accuracy computation or rectangle substitution.
        return json_safe({
            "request": request, "created_at": datetime.now(timezone.utc).isoformat(),
            "metrics": selected["best_metrics"], "history": selected["history"],
            "image": model["final_map"].serialize(),
            "geometry": model["roi"].geometry().serialize(),
        })

    result = payload["result"]
    image = ee.Image(ee.deserializer.fromJSON(result["image"]))
    geometry = ee.Geometry(ee.deserializer.fromJSON(result["geometry"]))
    # bounds() converts GeometryCollections before coordinates() is requested.
    ring = geometry.bounds(1, "EPSG:4326").coordinates().getInfo()[0]
    xs, ys = zip(*[(point[0], point[1]) for point in ring])
    map_id = image.getMapId({"min": 1, "max": 12, "palette": list(CLASS_PALETTE)})
    return {"tile_url": map_id["tile_fetcher"].url_format,
            "bounds": [[min(ys), min(xs)], [max(ys), max(xs)]]}


def main():
    try:
        payload = json.load(sys.stdin)
        with redirect_stdout(io.StringIO()):
            result = execute(payload)
        reply = {"ok": True, "result": result}
    except Exception as exc:
        reply = {"ok": False, "error": safe_error(exc)}
    json.dump(reply, sys.stdout, allow_nan=False)


if __name__ == "__main__":
    main()
