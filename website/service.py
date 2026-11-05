"""Session-local website adapter. EE calls run in isolated child processes.

Tokens travel over stdin, never in command-line arguments, files or reports.
No credentials, maps or results are placed in shared Streamlit caches.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import subprocess
import sys

from python.landcover_engine import CLASS_NAMES, CLASS_VALUES, LandCoverConfig, normalized_config

ROOT = Path(__file__).resolve().parents[1]
EE_SCOPE = "https://www.googleapis.com/auth/earthengine"
GOOGLE_METADATA = "https://accounts.google.com/.well-known/openid-configuration"
# This public website must never spend the owner's existing EE compute quota.
# Asset paths from this project remain usable when explicitly shared for reading.
PROTECTED_COMPUTE_PROJECTS = frozenset({"practical-proxy-441422-n6"})


class WebsiteError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def auth_configuration_error(auth):
    """Check deployment settings without returning secret values."""
    required = ("client_id", "client_secret", "cookie_secret", "redirect_uri")
    if any(not auth.get(key) or str(auth[key]).startswith("REPLACE_") for key in required):
        return "The website owner must configure Google sign-in in the hosting secrets."
    if auth.get("server_metadata_url") != GOOGLE_METADATA:
        return "Configure the Google OpenID discovery URL shown in the website setup guide."
    exposed = auth.get("expose_tokens", [])
    if isinstance(exposed, str):
        exposed = [exposed]
    if "access" not in exposed:
        return 'The owner must set expose_tokens = ["access"] for Earth Engine access.'
    scopes = str(auth.get("client_kwargs", {}).get("scope", "")).split()
    if not {"openid", EE_SCOPE}.issubset(scopes):
        return "The owner must enable the OpenID and Earth Engine scopes in Google sign-in."
    from urllib.parse import urlparse
    url = urlparse(auth["redirect_uri"])
    if not url.hostname or (url.scheme != "https" and not (url.scheme == "http" and url.hostname == "localhost")) or not url.path.endswith("/oauth2callback"):
        return "The Google callback must be the HTTPS website address followed by /oauth2callback."
    return None


def validate_project(project):
    project = str(project).strip()
    # IDs only: a numeric alias must not bypass the protected-project check.
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
        raise ValueError("Enter your own Google Cloud project ID (6–30 characters), not a project number or URL.")
    if project in PROTECTED_COMPUTE_PROJECTS:
        raise ValueError("The website owner's project cannot be used for computation here. Enter your own Earth Engine-enabled project ID.")
    return project


def make_request(project, aoi_asset, training_asset, target_year, fallback_year,
                 year_count=5, class_field="lc_code"):
    config = normalized_config(LandCoverConfig(
        aoi_asset=aoi_asset, training_asset=training_asset,
        target_year=int(target_year), fallback_year=int(fallback_year),
        year_count=int(year_count), class_field=class_field,
    ))
    return {"project": validate_project(project), "config": asdict(config)}


def request_key(request):
    return json.dumps(request, sort_keys=True, separators=(",", ":"))


def run_operation(action, access_token, request, *, result=None, timeout=None):
    if action not in {"connect", "map", "display"}:
        raise ValueError("Unknown website action")
    try:
        validate_project(request.get("project", ""))
    except ValueError as exc:
        raise WebsiteError("COMPUTE_PROJECT_NOT_ALLOWED", str(exc)) from None
    if not isinstance(access_token, str) or not access_token:
        raise WebsiteError("AUTH_REQUIRED", "Sign in with Google again to connect Earth Engine.")
    payload = {"action": action, "access_token": access_token, "request": request}
    if result is not None:
        payload["result"] = {key: result[key] for key in ("image", "geometry")}
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "website.worker"], cwd=ROOT,
            input=json.dumps(payload), text=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False,
            timeout=timeout if timeout is not None else (2700 if action == "map" else 180),
        )
    except subprocess.TimeoutExpired:
        raise WebsiteError("TIMEOUT", "Earth Engine did not finish within this website's time limit. "
                           "Your previous result is retained. Check your project's quota before retrying.") from None
    except OSError:
        raise WebsiteError("WORKER_START_FAILED", "The website could not start its processing worker. Contact the website owner.") from None
    try:
        reply = json.loads(completed.stdout)
        if not isinstance(reply, dict) or "ok" not in reply:
            raise ValueError()
    except (ValueError, TypeError):
        raise WebsiteError("WORKER_FAILED", "The website worker stopped without a valid result. Your previous result is retained.") from None
    if completed.returncode or not reply["ok"]:
        error = reply.get("error", {})
        raise WebsiteError(error.get("code", "WORKER_FAILED"),
                           error.get("message", "The website could not complete this request."))
    return reply["result"]


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    return value


def accuracy_rows(metrics):
    """Read saved metrics; derive user accuracy from matrix column totals."""
    matrix = metrics["confusion"]
    if len(matrix) != 12 or any(len(row) != 12 for row in matrix):
        raise ValueError("Saved confusion matrix must contain the 12 reference classes.")
    producer = metrics.get("producer", [])
    if producer and isinstance(producer[0], list):
        producer = [item for row in producer for item in row]
    rows = []
    for i, (code, name) in enumerate(zip(CLASS_VALUES, CLASS_NAMES)):
        total_predicted = sum(row[i] for row in matrix)
        p = producer[i] if i < len(producer) else None
        rows.append({"Code": code, "Class": name,
                     "Producer accuracy (%)": None if p is None else p * 100,
                     "User accuracy (%)": matrix[i][i] / total_predicted * 100 if total_predicted else None,
                     "Reference samples": sum(matrix[i])})
    return rows


def report_bytes(result):
    # Explicit allowlist: no credentials, display URLs, serialized graphs or auth state.
    return json.dumps(json_safe({key: result[key] for key in (
        "request", "created_at", "metrics", "history",
    )}), indent=2, allow_nan=False).encode("utf-8")


def bind_identity(state, subject):
    """Never carry a previous account's map/settings into another identity."""
    if state.get("website_subject") != subject:
        state.clear()
        state["website_subject"] = subject


def accept_result(state, result):
    # Called only after success: failed new work must not erase the previous map.
    state["website_result"] = result
    state.pop("website_display", None)
    state.pop("website_display_error", None)
