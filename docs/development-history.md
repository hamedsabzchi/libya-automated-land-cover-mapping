# Development history and earlier workflows

[Project home](../README.md) · [Documentation index](README.md) · [Notebook directory](../python/README.md)

These records describe earlier work packages (WP = work package). Their version numbers, branch-installation advice and acceptance status belong to those stages. They are not a sequence of steps for a new user. The complete assistant is now on `main`.

For current use, start with the [complete Colab assistant](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/Libya_Land_Cover_Assistant.ipynb). For installation from `main`, see the [developer guide](developer-guide.md). All earlier notebooks and evidence files remain in their original locations.

## Python ↔ GEE synchronization

WP03 ports the final active GEE **modeling core** documented in [WP01](gee-reference-spec.md): input normalization/preflight, separate national/AOI predictors, per-class sorted splits, terrain masks, existing temporal and selection rules, failed-candidate continuation and retained selected graphs. `python/assistant_adapter.py` connects this engine to the [WP02 contracts](assistant-contracts.md) in `contracts/` and emits linked status/result objects with session-local map references.

See [Python engine integration](python-engine-integration.md) for usage, compatibility notes and checks. Offline software tests include comparisons with extracted GEE client functions and serialization using the actual Earth Engine Python client. The [Tripoli live comparison](wp04-tripoli-comparison.md) now matches all recorded observation groups; additional WP04 cases remain open. WP05 adds a separate job/export layer described below; the adapter itself does not implement jobs or change the GEE reference. WP06 adds a bounded conversational interface; direct-download services remain later work.

## Earlier API-based conversational assistant (WP06)

Version 0.6 adds a private Colab/Jupyter chat interface over the existing mapping,
job and pilot-export services. Review a request before confirming execution, ask
for recorded status/results, or import an existing pilot ZIP without rerunning the
model. Free Persian/English text uses an optional OpenAI API key; a clearly labeled
guided-command mode works without one. Replies use actual records, and distinguish
saved model graphs, a successful pilot window, and full-region delivery.

Start with the [WP06 notebook](../python/06_wp06_landcover_assistant.ipynb) and
[usage, execution boundaries and limitations](wp06-conversational-assistant.md).
The reference GEE code and Python modeling engine remain unchanged. This MVP does
not yet compute class-area/change analyses or deliver a complete tiled region.

## Installable assistant runner (WP04)

The Python engine now has an installable command-line runner, local result/graph
bundles, and a separate diagnostic harness for comparing actual Python and GEE
observations. See [WP04 installation and execution](wp04-execution.md).
The GEE reference and WP03 engine are unchanged. The supplied Tripoli Python/GEE
records match for their settings, selected result, split IDs and 26 raster probes;
this does not prove full-raster equality. Saved graphs are not GeoTIFF exports.

## Persistent jobs and GeoTIFF exports (WP05)

Version 0.5 adds a local job ledger, a mapping worker, and separate Earth Engine
Drive export jobs. A completed WP04 bundle can be imported and its selected maps
exported without repeating seed search. Export submission, polling, cancellation
and recovery are explicit operations suitable for a later chatbot tool layer.
The GEE reference, Python modeling engine and adapter are unchanged.

See [WP05 commands, recovery and acceptance](wp05-jobs-exports.md) and
[Tripoli export notebook](../python/04_wp05_tripoli_export.ipynb).
This is a single-owner Python/CLI service foundation; it does not deploy a chatbot
or HTTP server. Automated checks are offline. A successful authenticated Tripoli
export and inspection of the downloaded GeoTIFF remain live acceptance steps.

### Bounded tile pilot (WP05B)

The owner-run full-area export reached a second server attempt after more than
ten hours. Version 0.5.1 adds one independently tracked, at-most 1024 × 1024 pixel
pilot export on the same 10 m grid, plus progress/attempt metadata and portable
recovery from WP05/pilot backups. It preserves the original operation and selected
model. See [pilot instructions and continuity record](wp05-tile-pilot.md)
and [the pilot notebook](../python/05_wp05_tripoli_tile_pilot.ipynb).
The [first live pilot TIFF passed delivery inspection](wp05-pilot-live-inspection.md)
in attempt 1 after 3 minutes 42 seconds. This establishes one aligned, nonempty
tile export; it does not establish full-grid coverage or whole-AOI performance.
No full tiling campaign has been launched.

## Google Colab

Open the notebook at:

`https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/02_landcover_colab.ipynb`

The notebook first performs a **public-data smoke test** over Libya using the 2024 Satellite Embedding collection, so Earth Engine initialization and public input availability can be checked without the personal AOI/training assets. Separate cells then test the default personal assets and optionally run one full candidate model.

