"""CLI for the single-owner ledger and independently managed EE exports."""

from .bundle import canonical_uuid
from .job_store import JobStore
from .jobs import enqueue_mapping, import_bundle, mapping_status, work_one
from .exports import enqueue_export, submit_export, poll_export, cancel_export


def add_parser(commands):
    root = commands.add_parser("jobs", help="Persist mapping work and independent GeoTIFF exports")
    root.add_argument("--store", required=True, help="Persistent local directory for SQLite and graphs")
    sub = root.add_subparsers(dest="job_command", required=True)
    enqueue = sub.add_parser("enqueue", help="Queue a mapping request; does not call EE")
    enqueue.add_argument("request")
    enqueue.add_argument("--project", required=True)
    enqueue.add_argument("--engine-commit", required=True)
    adopt = sub.add_parser("import-bundle", help="Adopt a completed WP04 ZIP without running seed search")
    adopt.add_argument("archive")
    sub.add_parser("work-one", help="Run one queued mapping job in this process")
    sub.add_parser("list", help="List recorded jobs without querying EE")
    for name in ("show", "events", "cancel-mapping", "export-submit", "export-poll", "export-cancel"):
        command = sub.add_parser(name)
        command.add_argument("job_id")
    export = sub.add_parser("export-create", help="Queue an export of one selected map; no remote task yet")
    export.add_argument("mapping_job_id")
    export.add_argument("artifact_id")
    export.add_argument("--spec", required=True)
    export.add_argument("--request-id", required=True, help="UUID reused for the same logical export request")


def execute(args):
    from .cli import emit, read_json, request_from_inputs
    store = JobStore(args.store)
    command = args.job_command
    if command == "enqueue":
        result = enqueue_mapping(store, request_from_inputs(read_json(args.request)),
                                 project=args.project, engine_commit=args.engine_commit)
    elif command == "import-bundle":
        result = import_bundle(store, args.archive)
    elif command == "work-one":
        result = work_one(store)
    elif command == "list":
        result = store.list()
    elif command == "show":
        result = mapping_status(store, args.job_id)
    elif command == "events":
        result = store.events(args.job_id)
    elif command == "cancel-mapping":
        result = store.get(args.job_id)
        if result["kind"] != "mapping" or result["state"] != "queued":
            raise ValueError("Only queued mapping jobs can be cancelled locally")
        result = store.update(result, state="cancelled")
    elif command == "export-create":
        result = enqueue_export(store, args.mapping_job_id, args.artifact_id,
                                read_json(args.spec), request_id=canonical_uuid(args.request_id))
    else:
        result = {"export-submit": submit_export, "export-poll": poll_export,
                  "export-cancel": cancel_export}[command](store, args.job_id)
    emit(result)
    if isinstance(result, dict):
        if result.get("state") in {"failed", "interrupted"}:
            return 1
        if result.get("state") == "submission_unknown":
            return 4
    return 0
