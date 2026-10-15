# WP05: persistent jobs and retained-map GeoTIFF exports

WP04 retains a completed result and serialized Earth Engine image graphs. WP05
adds job history and an explicit path from one retained map to a Drive GeoTIFF
export. It does not alter `gee/automated_land_cover_app.js`,
`python/landcover_engine.py`, `python/assistant_adapter.py`, or WP02 contracts.
No model method or accuracy assessment is changed.

## Scope and completion status

- Installable package 0.5.0: SQLite job records/events, mapping queue/worker,
  checked WP04 ZIP import, independent export lifecycle and CLI/Python functions.
- Offline software verification covers persistence, crash recovery, duplicate
  requests, lost submission responses, cancellation races and actual EE-client
  export serialization. It does not contact the Earth Engine service.
- The owner's completed Tripoli ZIP was imported locally and all six retained
  graph checksums passed. No remote export was submitted by that local check. The subsequent owner-run export
  reached Earth Engine, then failed the pixel-count limit; see the correction below.
- Live acceptance is **pending**: authenticate, submit the final-map export,
  observe a terminal result and inspect an actual downloaded GeoTIFF. This is not
  a claim that a GeoTIFF has already been generated.

This release supports one trusted owner on Linux/Colab, local SQLite and `flock`.
Run workers in separate processes; it is not a multi-tenant/threaded web server.
There is no chatbot UI, hosted worker, public download endpoint or Drive file proxy.
The CLI and Python functions are the future assistant's tool boundary.

## Import and export the completed Tripoli run

The [unexecuted Colab notebook](../python/04_wp05_tripoli_export.ipynb) installs a
pinned WP05 source commit, requests normal Google authentication, and accepts the
existing WP04 ZIP. It selects `final_map` by default; annual maps can be selected
explicitly. The project remains `practical-proxy-441422-n6`.

Equivalent commands after installing the package and authenticating Earth Engine:

```bash
libya-landcover jobs --store ./job-store import-bundle ./wp04-tripoli.zip
libya-landcover jobs --store ./job-store list
libya-landcover jobs --store ./job-store show MAPPING_JOB_UUID
libya-landcover jobs --store ./job-store export-create MAPPING_JOB_UUID ARTIFACT_UUID \
  --spec examples/wp04-tripoli/export-spec.json --request-id EXPORT_REQUEST_UUID
libya-landcover jobs --store ./job-store export-submit EXPORT_JOB_UUID
libya-landcover jobs --store ./job-store export-poll EXPORT_JOB_UUID
libya-landcover jobs --store ./job-store events EXPORT_JOB_UUID
```

Replace uppercase placeholders with returned IDs, not file paths. Artifact IDs
are in `job-store/jobs/MAPPING_JOB_UUID/bundle/result.json`. Import and
`export-create` are local operations: only `export-submit` starts remote work.
`show` and `list` read the ledger; `export-poll` refreshes remote state.
No private asset contents, credentials, run archives or rasters belong in GitHub.

The export spec uses EPSG:32633 and `[10,0,0,0,-10,0]`, the explicit grid recorded
for the Tripoli probes. The first release requires an explicit north-up 10 m UTM
grid. It encodes classes 1–12 as UInt8 with 0 as NoData, clips the export region to
the requested AOI geometry, requests Cloud Optimized GeoTIFF and allows 100 million
pixels by default. The explicit Tripoli example overrides this with 5 billion
pixels after the first live task reported 4,696,963,298 pixels. `file_dimensions=4096` can produce multiple TIFF files within
one export. No resampling, classifier or temporal-rule change is introduced.

The selected graph is restored; the seed search is not repeated. Earth Engine can
still recompute the retained selected classifier graph to produce pixels. A graph
is not a snapshot of external asset contents; those assets must remain accessible
and unchanged for repeatable computation.

## Job identities and recovery

Mapping and export jobs have separate IDs and states. An export failure does not
turn a completed mapping job into a failed mapping job.

| Work | States and behavior |
| --- | --- |
| New mapping | `queued` → `running` → `completed` or `failed` |
| Worker crash | Next worker checks the retained bundle; a verified completed bundle recovers to `completed`, otherwise `interrupted`. No automatic model rerun. |
| Imported mapping | `importing` → `completed`; re-importing the same ZIP resumes an interrupted import or returns the same job. |
| Export | `queued` → `submitting` → `submitted` / `running` → `completed` / `failed` |
| Lost submission response | `submission_unknown`; poll reconciles by the exact request-specific description. Explicit resubmission reuses the saved payload and request ID. |
| Export cancellation | `cancelling` until the server confirms `cancelled`; a racing success may still become `completed`. |

SQLite stores inputs, revisions and event snapshots atomically. Compare-and-swap
revisions and process locks prevent concurrent claims. Request IDs are idempotency
keys: same key and inputs return the existing local job; changed inputs raise a
conflict. Import validates request/status/result linkage, reference provenance,
the complete graph index and hashes. It reads only expected JSON/graph files and
rejects archive path traversal, symlinks, duplicates and oversized archives.
These checks verify bundle consistency, not the truth of caller-supplied provenance.

Keep the same external `EXPORT_REQUEST_UUID` for retries. It is also the Earth
Engine `requestId`, description suffix and Drive-folder suffix. The notebook
derives it deterministically from project, source run, artifact, graph checksum
and normalized export spec. Re-importing the same ZIP into a fresh local store
therefore preserves the remote request identity, despite different local job IDs.
Use the same Google account and project. After a lost store, a duplicate submission
can return an uncertain outcome; poll the same job to reconcile it. Never invent
a new UUID to resolve an uncertain outcome. If the operation is no longer visible,
inspect Earth Engine Tasks and Drive before deciding on a new attempt.

A terminal failed/cancelled job is not automatically restarted. A deliberate new
attempt requires a new request UUID. Network errors while polling preserve the
previous state; they do not mean the remote computation failed. Cancellation is
explicit with `export-cancel EXPORT_JOB_UUID`. `cancel-mapping` supports only
queued jobs; this version does not forcibly stop an active mapping worker.

## Queue new mapping work

```bash
libya-landcover jobs --store ./job-store enqueue ./request.json \
  --project practical-proxy-441422-n6 --engine-commit ACTUAL_40_CHARACTER_SOURCE_COMMIT
libya-landcover jobs --store ./job-store work-one
```

Use the WP02 request schema and the actual installed engine source commit. The
caller supplies that commit; the service validates its format and consistency,
not a cryptographic attestation of the Python installation. `work-one` handles
one queued request in the calling process, using the existing WP04 runner. Invoke
it from a separate process for background work. Poll `show` for the latest saved
engine status. Repeating `work-one` is an explicit scheduler decision.

CLI exit codes: 0 for a successful command (including queued/running work), 1 for
failed/interrupted work, 2 for invalid input or command errors, 4 for an uncertain
submission. A zero exit code alone never proves a completed export; inspect `state`.

Python tool entry points are `JobStore`, `enqueue_mapping`, `work_one`,
`import_bundle`, `mapping_status`, `enqueue_export`, `submit_export`, `poll_export`
and `cancel_export`. A future chatbot should call these defined functions and
present recorded state; it must not generate arbitrary executable model code.

## Files, persistence and download

Keep the complete job-store directory on a persistent local disk. It contains
`jobs.sqlite3`, retained bundles and each persisted export request. Process restarts
preserve these files; deletion of a Colab runtime does not. `JobStore.snapshot()`
backs up only SQLite: copy `jobs/` too while local workers/submission calls are
stopped. The notebook downloads a scoped backup plus an export manifest; these
contain asset references and graphs, not account credentials. Restore a trusted
backup into a fresh local directory, preserving `jobs.sqlite3` and `jobs/` together.
Do not use mounted storage without reliable SQLite/locking semantics as the active
store; download backups separately.

After `completed`, `destination_uris` contains only Drive/Docs destinations
returned by the service. A destination may be a folder, not a direct file-download
URL. Open it in the authenticated account and download the `.tif` file(s). If no
URI is returned, find the exact recorded `drive_folder` name in your Google Drive.
This release does not make rasters public or download them automatically.

## Live acceptance handoff

1. Run the notebook in a fresh runtime; upload the completed WP04 Tripoli ZIP.
2. Review the selected final map, project and export grid; execute the submit cell.
3. Repeat the poll cell until terminal. Download the manifest/backup even if the
   export fails, preserving its operation ID and state for diagnosis.
4. On success, download all TIFF parts from Drive. Share the manifest and a TIFF
   for software-level inspection of CRS, 10 m transform, band/type, NoData and
   class encoding. This step does not reassess model accuracy.

The notebook's default run creates one final-map task. Additional annual exports
are separate explicit requests. Do not call WP05 live acceptance complete until
the actual output has been received and inspected.

## API references

- [Drive export options](https://developers.google.com/earth-engine/apidocs/export-image-todrive)
- [Image export requestId and operation response](https://developers.google.com/earth-engine/reference/rest/v1/projects.image/export)
- [Operation polling](https://developers.google.com/earth-engine/reference/rest/v1/projects.operations/get)

The adapter pins `earthengine-api==1.7.48`, uses public export/operation APIs and
persists the serialized request before submission. No private `Task._request_id`
attribute is used.

## Tripoli live export: pixel-limit failure and correction (2026-10-15)

The owner supplied a WP05 backup showing the imported mapping remained completed,
while its export advanced through submitted/running to failed. Bundle/graph and
export-payload hashes, SQLite integrity and the manifest/event correspondence
passed inspection. The archive contains no TIFF pixels.

The original handoff retained only remote code 3. A separate owner-authenticated
operation read supplied the cause: 4,696,963,298 requested pixels exceeded the
configured 100,000,000 maximum. This is a reported export-size guard failure;
it is not an accuracy finding or evidence that the model must change.

The Tripoli spec and notebook now explicitly set `max_pixels=5000000000`.
The general library default stays at 100 million. The AOI, CRS, 10 m affine grid,
selected graph, class encoding and 4096-pixel file dimensions are unchanged.
The pixel count is the server's reported export count, not an independently
measured AOI area. Splitting files with `file_dimensions` does not lower the
whole export's pixel count. Raising this cap clears the reported guard only;
it does not guarantee the subsequent computation will complete.

For the already-open original notebook, replace only `max_pixels` in cell 4 with
`5000000000`, rerun cells 4 and 5, poll with cell 6 and download a new backup with
cell 7. Cell 4 hashes the changed spec into a new deterministic request UUID,
so this is an explicit corrected attempt after a confirmed terminal failure.
Do not reuse the failed request UUID with changed inputs, edit stored records,
or resubmit the unchanged failed job. The old failed record remains available.

The updated notebook additionally retrieves the server error for failed tasks
and saves it in the private handoff under `remote_diagnostic`; a failed diagnostic
lookup does not prevent the backup download. This does not alter generic ledger
error handling or the immutable model code. The notebook still installs the same
pinned service commit: the existing service already supports the higher cap.

Live acceptance remains open until a corrected attempt completes and actual TIFF
files have been inspected. No retry was submitted from this development environment.
