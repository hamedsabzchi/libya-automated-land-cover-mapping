"""Explicit commands; no login, jobs or exports on import or validation."""

import argparse
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import re
import sys

from contracts.models import GEE_SHA256
from python.assistant_adapter import request_from_inputs, run_request
from . import __version__
from .bundle import GraphArtifactStore, write_json
from .evidence import capture, compare, validate_probes


def read_json(path):
    def reject(value):
        raise ValueError("Nonfinite JSON value: " + value)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject, object_pairs_hook=unique)


def emit(value):
    print(json.dumps(value, allow_nan=False, ensure_ascii=False))


def initialize(project):
    import ee
    ee.Initialize(project=project)


def source_hashes():
    from python import landcover_engine, assistant_adapter
    from contracts import models
    return {module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (landcover_engine, assistant_adapter, models)}


def parser():
    root = argparse.ArgumentParser(description="Libya land-cover reference engine and execution evidence")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Resolve request offline; no EE calls")
    validate.add_argument("request")
    doctor = commands.add_parser("doctor", help="Check an already authenticated EE session")
    doctor.add_argument("--project", required=True)
    run = commands.add_parser("run", help="Run the reference engine synchronously; save graphs and results")
    run.add_argument("request")
    run.add_argument("--project", required=True)
    run.add_argument("--engine-commit", required=True, help="Actual installed source commit, asserted by the caller")
    run.add_argument("--output", required=True, help="New local directory; existing paths are refused")
    run.add_argument("--capture-evidence", action="store_true", help="Evaluate selected split IDs after the model run")
    run.add_argument("--probes", help="Explicit raster probe JSON; implies --capture-evidence")
    reference = commands.add_parser("prepare-reference", help="Build a diagnostic session from byte-identical GEE plus a separate observer")
    reference.add_argument("--reference", required=True, help="Path to unchanged gee/automated_land_cover_app.js")
    reference.add_argument("--output", required=True, help="New .js session file, outside the reference path")
    reference.add_argument("--probes")
    diff = commands.add_parser("compare", help="Compare actual Python and GEE observation JSON offline")
    diff.add_argument("python_evidence")
    diff.add_argument("gee_evidence")
    return root


def execute(args):
    if args.command == "validate":
        request = request_from_inputs(read_json(args.request))
        emit({"request": request.to_dict(), "fingerprint": request.fingerprint(), "engine_config": request.engine_config()})
        return 0
    if args.command == "compare":
        report = compare(read_json(args.python_evidence), read_json(args.gee_evidence))
        emit(report)
        return {"observations_match": 0, "different": 1, "incomplete": 4}[report["status"]]
    if args.command == "prepare-reference":
        reference = Path(args.reference).read_bytes()
        if hashlib.sha256(reference).hexdigest() != GEE_SHA256:
            raise ValueError("GEE reference checksum differs; no session was created")
        probes = validate_probes(read_json(args.probes)) if args.probes else None
        observer = files("libya_landcover").joinpath("gee_observer.js").read_text(encoding="utf-8")
        addition = "\n// Separate WP04 observation harness; original bytes above are unchanged.\n"
        addition += "var WP04_PROBES = " + json.dumps(probes, allow_nan=False) + ";\n" + observer
        with Path(args.output).open("xb") as stream:
            stream.write(reference + addition.encode("utf-8"))
        emit({"session": args.output, "reference_sha256": GEE_SHA256, "reference_bytes": len(reference),
              "live_execution_performed": False})
        return 0
    if args.command == "doctor":
        try:
            initialize(args.project)
        except Exception as exc:
            emit({"initialized": False, "project": args.project, "error_type": type(exc).__name__,
                  "next_action": "Authenticate with earthengine authenticate in your environment; verify the authorized project and retry."})
            return 3
        emit({"initialized": True, "project": args.project, "asset_access_verified": False})
        return 0

    # Validate all local inputs before any initialization or paid remote work.
    request = request_from_inputs(read_json(args.request))
    if not re.fullmatch(r"[0-9a-f]{40}", args.engine_commit) or args.engine_commit == "0" * 40:
        raise ValueError("Supply the actual nonzero 40-character source commit")
    probes = validate_probes(read_json(args.probes)) if args.probes else None
    directory = Path(args.output)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {"schema_version": "wp04.1", "bundle_state": "initializing", "package_version": __version__,
                "project": args.project, "engine_commit": args.engine_commit,
                "commit_provenance": "caller_asserted", "source_sha256": source_hashes(),
                "gee_sha256": GEE_SHA256, "representation": "serialized_graphs_not_geotiffs",
                "evidence_state": "pending" if args.capture_evidence or probes else "not_requested"}
    write_json(directory / "request.json", request.to_dict())
    write_json(directory / "manifest.json", manifest)
    try:
        try:
            initialize(args.project)
        except Exception as exc:
            manifest.update(bundle_state="initialization_failed", error_type=type(exc).__name__)
            write_json(directory / "manifest.json", manifest)
            emit({"bundle": str(directory), "bundle_state": "initialization_failed",
                  "next_action": "Run doctor with the authorized EE project after authentication."})
            return 3
        manifest["bundle_state"] = "running"
        write_json(directory / "manifest.json", manifest)
        with (directory / "status.jsonl").open("x", encoding="utf-8") as log:
            def on_status(status):
                log.write(json.dumps(status.to_dict(), allow_nan=False) + "\n")
                log.flush()
                emit(status.to_dict())
            execution = run_request(request, engine_commit=args.engine_commit,
                                    artifact_store=GraphArtifactStore(directory), on_status=on_status)
        write_json(directory / "status.json", execution.status.to_dict())
        if execution.result is None:
            manifest["bundle_state"] = "engine_failed"
            write_json(directory / "manifest.json", manifest)
            return 1
        write_json(directory / "result.json", execution.result.to_dict())
        write_json(directory / "class-table.json", execution.result.class_table())
        manifest["bundle_state"] = "completed"
        if args.capture_evidence or probes:
            try:
                observation = capture(execution, request, probes)
                write_json(directory / "python-evidence.json", observation)
                manifest["evidence_state"] = "captured" if probes else "partial_without_raster_probes"
            except Exception as exc:
                manifest.update(evidence_state="failed", evidence_error_type=type(exc).__name__)
                write_json(directory / "manifest.json", manifest)
                emit({"bundle": str(directory), "bundle_state": "completed", "evidence_state": "failed"})
                return 4
        write_json(directory / "manifest.json", manifest)
        emit({"bundle": str(directory), "bundle_state": manifest["bundle_state"], "evidence_state": manifest["evidence_state"]})
        return 0
    except Exception as exc:
        manifest.update(bundle_state="runner_failed", error_type=type(exc).__name__)
        write_json(directory / "manifest.json", manifest)
        raise


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return execute(args)
    except Exception as exc:
        # Do not print raw remote exceptions, credential paths or HTTP payloads.
        print(json.dumps({"error": type(exc).__name__, "message": "Command failed; check inputs, output paths and the saved run manifest."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
