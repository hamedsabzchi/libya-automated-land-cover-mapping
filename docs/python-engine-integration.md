# WP03 — Python reference engine and assistant integration

Implemented against the unchanged GEE reference from [WP01](gee-reference-spec.md).
The reference file remains byte-identical, SHA-256:
`1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4`.

WP03 delivers the Python port and synchronous contract adapter. It does not change
GEE, its method, existing metrics or selection rule. It does not yet claim live
Earth Engine execution parity; that is the bounded WP04 integration check.

## What is now implemented

| WP01 rows | Implementation |
| --- | --- |
| C01–C03 | Fixed 10 m typed configuration, explicit assistant asset inputs, pasted asset normalization, configured integer bounds; early annual-window years go to coverage preflight as in GEE |
| C05–C08 | Single asset/schema report; ordered reference error branches; histogram lookup/null filtering; full national points; separate annual coverage queries for training and AOI with target fallback logic |
| C10–C12 | Full normalized training bounds and independent AOI bounds; per-band terrain unmask(0); represented-class sorted `_flex_random` split, floor/clamp counts and list slices |
| C14–C18 | Annual AOI classifiers and AOI temporal final map separate from national validation map; existing temporal operations retained; sampled count returned; reference row/exclusion/finite-value scoring |
| C19–C22 | JS-compatible evaluated numeric-array conversion; sequential seed failure continuation; strict first-on-tie choice and threshold stopping; selected model retained without rebuilding |
| C23–C24, C28 | Synchronous RunRequest → engine configuration → RunStatus snapshots → linked RunResult; model objects internal and artifacts registered in a caller-supplied store |

Already matching constants, RF parameters, national training scope and temporal
operations (C04/C07/C09/C13/C15/C16/C20) are retained. Rounding/coercion is the WP02
typed request boundary, not an attempt to accept every malformed GEE textbox input.
Browser widgets and direct-download queue/grid work (C25–C27) remain later stages.

## Entry points and return values

`python/landcover_engine.py` stays importable as the standalone module downloaded
by the existing Colab notebook. Pure helpers can also be imported without EE
installed. Execution requires an installed, caller-initialized Earth Engine client.

- `normalize_asset_id`: same supported pasted path/URL normalization as the final
  GEE helper; `normalized_config` resolves paths and trims the class field.
- `prepare_inputs(config, on_event=None)`: one asset/schema request and one coverage
  request; returns `PreparedInputs` with separate predictor dictionaries. Each seed
  shares these inputs, never a shared fitted classifier.
- `build_seed_model(config, seed, prepared=None)`: builds the candidate graph and
  its validation objects. When no prepared inputs are supplied, preflight runs first.
- `evaluate_seed(config, seed)`: builds and evaluates one candidate, returning its
  existing metrics and score. It raises a typed failure if no classes are scored.
- `search_seeds(config, ..., on_event=None)`: sequential reference selection;
  returns `best_metrics`, retained `model`, `history`, normalized `config`,
  `asset_report` and `coverage`.

History entries have `{seed, status:"completed", metrics}` or
`{seed, status:"failed", code, message}`. Internal histories may contain nonfinite
raw EE numbers and are not wire payloads. The result adapter performs explicit
finite/null conversion before contract validation. `sampled_validation_count`
is the count after sampling the validation map, not the number of split features.

The old union `processing_geometry` path is removed. `metrics_dictionary` now
returns the reference selection payload and sampled count; the earlier extra
`user` array is replaced at the assistant boundary by the exact existing GEE
display formula in `RunResult.class_table()`. Overall/kappa/producer/confusion
calculations are unchanged. The single-candidate Colab calls remain supported.

Only reference-handled candidate evaluation errors or no-scored-class outcomes
advance to the next seed. Programming/graph-construction errors propagate to the
adapter instead of silently disappearing. Exhaustion with no selected candidate
raises `NO_SUCCESSFUL_SEED` and retains internal diagnostic history.

## Using the adapter from a checked-out repository

Install the existing runtime requirements, initialize EE with your authorized
project/account, and use the actual commit of the checked-out engine. Authentication
is caller-owned; importing the adapter never initiates login or reads credentials.

```python
import subprocess
import ee
from uuid import uuid4
from python.assistant_adapter import request_from_inputs, run_request

# Authenticate separately as appropriate for your environment, then initialize.
ee.Initialize(project="YOUR_AUTHORIZED_EE_PROJECT")
engine_commit = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], text=True
).strip()

request = request_from_inputs({
    "request_id": str(uuid4()),
    "aoi_asset": "projects/YOUR_PROJECT/assets/YOUR_AOI",
    "training_asset": "projects/YOUR_PROJECT/assets/YOUR_TRAINING",
    "class_field": "lc_code",
    "target_year": 2024,
})

execution = run_request(
    request,
    engine_commit=engine_commit,
    on_status=lambda snapshot: print(snapshot.to_json()),
)
if execution.result is not None:
    result_json = execution.result.to_json()
    table = execution.result.class_table()
    record = execution.result.to_dict()
    final_record = record["outputs"][0]
    final_image = execution.artifact_store.get(
        record["run_id"], final_record["artifact_id"]
    )
else:
    failure = execution.status.to_dict()["error"]
```

Use a clean committed checkout for truthful engine provenance. The adapter validates
the commit shape and rejects the all-zero example sentinel; it cannot independently
prove that supplied metadata matches deployed files. It defaults engine_version to
the module's `0.3.0`, which is an adapter implementation version, not a new GitHub
release. Do not execute the example until the placeholder paths/project are replaced.

The standalone notebook still downloads `main` unless its ENGINE_URL is changed;
an unmerged WP03 branch is exercised from its checkout, not by assuming main already
contains it. Existing personal asset defaults are retained only for legacy notebook
convenience. The assistant always requires explicit AOI/training inputs and never
uses those author defaults silently.

## Status and artifact boundaries

`run_request` returns `Execution(status, result, artifact_store, model, history,
diagnostic_exception)`. Only status/result are wire contracts. Live EE handles,
candidate history and the exception are process-local diagnostics, not chatbot JSON.
Unexpected failures produce a generic INTERNAL_ERROR; backend details stay internal.
An observer failure raises `StatusDeliveryError` without automatic model retry.

Status snapshots are emitted in order: queued, asset_preflight, coverage_preflight,
seed_search (once per attempted seed), preparing_result, then completed or failed.
Every transition and request/result linkage is checked against WP02. No invented
completion percentage is emitted. Contract validation occurs before artifact storage;
storage failure cannot publish a completed result.

`MemoryArtifactStore` is an explicit session-local implementation. It keeps the
actual selected final/annual image objects under run-scoped artifact UUIDs. A future
store can implement atomic `save_many(run_id, entries)`; access control, persistence,
restart recovery and downloadable URLs are WP05–WP07 responsibilities. The memory
store is not a durable database, a public resolver or a cross-user authorization layer.
`artifact://` refers to registered objects; it is not a downloadable GeoTIFF URL.

No background worker, web API, cancellation, idempotency database, export polling
or chat UI is introduced in WP03. Model execution remains synchronous in the caller
process. Calling the adapter is not the same as deploying an assistant.

## Verification completed for WP03

Commands from repository root:

```sh
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
node --check gee/automated_land_cover_app.js
```

The 49 unittest cases cover 23 WP02 contract checks, 22 engine/adapter checks, and
4 actual EE-client graph checks. The 9 existing repository structural checks are
also run separately. Tests compare asset normalization, histogram conversion and
scoring against pure client snippets extracted directly from the unchanged GEE
file. The oracle does not run GEE UI or server computations.

Real-client tests use Earth Engine Python `1.7.48` and its bundled official static
algorithm fixtures. API evaluations are replaced with controlled fixture responses,
and socket connection attempts are blocked. Full candidate/metric graphs serialize
successfully, including sorted split, RF, temporal combination and clip operations.
They confirm client API compatibility and graph construction, not server output.
CI installs this test client explicitly, so these tests cannot silently skip there.

## WP04 handoff: remaining execution observations

Run an agreed small AOI and accessible training asset with the same inputs/seed in
the fixed GEE reference and Python. Record normalized/split feature IDs, sampled
counts, returned array shapes, selected candidate and raster/mask output. In
particular, observe target-year fallback with missing/partially masked inputs and
the exact `clip(roi)` behavior on the same multi-feature ROI. WP03 preserves the
reference clip call instead of silently substituting a different operation.

The O01–O05 observations in WP01 remain live-run work. O06 and C25–C27 remain
output-service work. These are implementation-equivalence checks, not a review or
redesign of the user's model. GEE stays unchanged; any port discrepancy is resolved
on the Python/adapter side.

This PR is stacked on WP02. Merge predecessors in order and retarget to main
before merging; no automatic merge or live EE job is part of this delivery.
