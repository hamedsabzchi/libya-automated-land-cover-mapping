# WP05B: one bounded tile delivery experiment

## Continuity: what remains fixed and open

The immutable reference is `gee/automated_land_cover_app.js`, SHA256
`1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4`.
Neither this file, the Python model/adapter, nor WP02 contracts change here.
No accuracy assessment, training scope, seed rule, classifier or temporal method
is revised. WP04's recorded Tripoli observation comparison remains as documented;
its other live cases remain open.

The supplied WP04 run selected seed 4444 and retained six graphs. It used engine
commit `bf9cf6c8bbd03d083c2d9bccae722d7036923afc`. WP05 imports that completed
mapping; it does not run seed search again. The source project and assets remain:

- `practical-proxy-441422-n6`
- `projects/practical-proxy-441422-n6/assets/Libya/Tripoli`
- `projects/practical-proxy-441422-n6/assets/Libya/TD3-attept1-tripoli`

The first Drive attempt failed because the service reported 4,696,963,298 pixels
against a 100-million cap. A subsequent owner input used 500 million; the corrected
full-area attempt used 5 billion. Increasing the cap removed the reported size
guard but did not establish delivery performance. At the owner's 2026-10-16
08:11:30 UTC observation, the corrected operation was RUNNING on attempt 2,
progress 0.5675714311015245; its current attempt started at 02:31:22 UTC.
The cause of the preceding server retry was not included. This is a historical
observation, not a live status assertion or evidence of model failure.

The existing full-area operation is preserved. The new notebook only reads it;
it never cancels or resubmits it. WP05's final raster acceptance remains pending.
This pilot is a separate job and a separate delivery acceptance step.

## What the pilot changes

Package 0.5.1 accepts an optional `pixel_window` in export specs:

```json
{"column": 39488, "row": -360513, "width": 1024, "height": 1024}
```

These are integer pixel offsets/dimensions relative to the supplied global affine
transform, not longitude/latitude. The above offsets are illustrative; the notebook
derives its actual window from the authorized AOI. Each dimension must be 1–1024.
The existing export spec continues to require north-up 10 m UTM coordinates.
For Tripoli it retains EPSG:32633 and `[10,0,0,0,-10,0]`.

The default window has 1,048,576 pixels, a 10.24 km square. It exports the **same
retained selected image graph**, clipped to the original AOI before NoData filling,
within this smaller rectangle. Source class values are not changed. Outside-AOI
or masked pixels are 0; mapped classes remain 1–12 in UInt8 GeoTIFF. The rectangle
is snapped to existing pixel edges. CRS/origin/resolution remain aligned with the
parent grid, even though the resulting TIFF's top-left coordinate is local to its
window. The pilot uses a 1.1-million maxPixels cap and 1024-pixel file dimensions.

Geometry-only preflight reads the projected AOI centroid and verifies positive
intersection area. It does not evaluate the entire raster or search seeds. For a
disjoint region where the centroid tile misses the AOI, the notebook fails before
submission and accepts an explicit `[longitude, latitude]` centre. Positive overlap
does not guarantee valid classified pixels; an all-NoData TIFF is inconclusive.
This is not a representative sample for accuracy assessment.

The original `fileDimensions=4096` split output files inside one large operation.
The pilot instead limits the operation's region. Smaller regions may still repeat
expensive upstream classifier/training/aggregation graphs. There is no promised
speedup, automatic widening or full-area tiling scheduler in this stage.

## Execute the prepared notebook

[Open the pilot in Colab](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/feat/wp05-tile-pilot/python/05_wp05_tripoli_tile_pilot.ipynb)

Use a fresh runtime and execute cells 1–7 in order:

1. Install the pinned 0.5.1 service commit printed by the notebook.
2. Authenticate with the same Google account and initialize the supplied project.
3. Upload one existing WP05 backup ZIP (including the `...-26.zip` backup), a
   completed WP04 ZIP, or a previously downloaded pilot ZIP.
4. Read the original operation, derive or recover the exact bounded plan, and
   inspect the local pilot job. No task starts in this cell.
5. Explicitly submit **one** pilot. This never starts a full grid or cancels the
   original task. A queued remote task can share project resources with the old
   task, so its queue time is not a clean benchmark of per-tile computation.
6. Poll and save progress, attempt count, timestamps, stages and raw server errors.
   Polling is observational and does not accelerate execution. A progress reset
   across attempts is not linear time remaining. Network errors do not prove a
   remote failure.
7. Download the private pilot ZIP immediately after submission, before closing
   Colab, and after the final status. Download the actual TIFF from the returned
   Drive destination on success; the ZIP contains graphs/evidence, not raster pixels.

`save_diagnostic` retains raw server responses in private files so failure messages
are not discarded. Generic public-facing job errors stay concise. A diagnostic
lookup failure is captured by type and does not prevent a local handoff download.
The regular job ledger now also retains whitelisted progress/attempt/stage metadata.
EECU usage is compute usage, not wall-clock time or a monetary bill.

## Recovery after Colab reset

The notebook must initialize imports, authentication and its local state again.
Run cells **1–4**, upload the most recent `wp05-pilot-...zip` in cell 3, then run
cell **6**. Skip submission cell 5 for an already recorded operation. Recovery
verifies its project and exact request-specific description before attaching it.
The original full-area operation remains independent.

Pilot identities are UUID5 values derived from project, source run, artifact,
graph hash and the normalized exact window/spec. Re-importing into another local
store changes local job IDs, not the remote request identity. Unknown submissions
retain uncertainty and reconcile using that same identity before explicit retries.
Terminal failed/cancelled jobs are not automatically restarted. A changed tile is
a different deliberate experiment, not a retry of the old tile.

Archive adoption checks graph hashes, bundle consistency, safe paths, entry counts
and uncompressed size. It imports whitelisted JSON/graphs without executing uploaded
code or opening the uploaded SQLite database. Pilot recovery preserves previous
event histories and raw diagnostic snapshots as audit files. The original WP05
manifest is retained when supplied. Keep the source WP05 ZIP too: this is not a
general restore of every job in that source database.

Recreating a pilot from only the old WP05 ZIP recomputes the geometric plan; use
the newer pilot handoff to preserve the exact window even if external AOI assets
later change. Checksums protect serialized graph consistency, not the immutability
of referenced remote assets.

## Python/CLI integration

The existing `jobs export-create ... --spec ...` accepts `pixel_window`; submission,
polling and cancellation remain separate commands. For archive adoption/planning:

```python
from libya_landcover.job_store import JobStore
from libya_landcover.pilot import adopt_archive, plan_pilot, create_pilot

store = JobStore("./pilot-store")
adopted = adopt_archive(store, "./wp05-backup.zip")
mapping_id = adopted["mapping"]["job_id"]
plan = plan_pilot(store, mapping_id)  # authenticated geometry reads only
# Obtain artifact_id from the checked mapping result, then:
# job = create_pilot(store, mapping_id, artifact_id, plan)  # no submission
```

`recover_pilot`, `save_diagnostic`, and `save_handoff` provide the notebook recovery
and evidence boundaries. `recover_export` reattaches one verified known operation
without submitting it. No HTTP server or chatbot UI is deployed by this work.

## Completion criteria and next decision

Offline checks cover bound/alignment validation, actual EE-client region/request
serialization, geometry-only preflight, same-identity recovery, metadata retention,
failure diagnostics, hostile archives and portable history. They are not evidence
of live raster delivery. No authenticated pilot is submitted from the development
environment.

Live acceptance requires a terminal operation record and the downloaded TIFF:
one band, UInt8, EPSG:32633, 10 m transform on the same lattice, expected window
extent/dimensions, NoData=0 and nonempty valid class values. Inspect available
runtime/attempt evidence too. This is software output validation, not a new model
accuracy test. No bulk campaign is authorized by merely completing this notebook.

If the pilot works acceptably, the next implementation can plan a complete aligned
grid, avoid empty cells, persist a per-tile manifest and resume individual failed
tiles. If it repeats the costly failure, inspect the retained graph's delivery
computation before choosing another export strategy; do not blindly multiply tasks.

## References

- [Export region, grid, pixel cap and file dimensions](https://developers.google.com/earth-engine/apidocs/export-image-todrive)
- [Projected rectangle geometry](https://developers.google.com/earth-engine/apidocs/ee-geometry-rectangle)
- [Batch task lifecycle and retries](https://developers.google.com/earth-engine/guides/processing_environments)
