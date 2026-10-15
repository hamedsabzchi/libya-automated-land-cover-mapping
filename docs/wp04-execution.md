# WP04 — Installable runner and controlled execution observations

**Delivery status:** package and diagnostic harness implemented. The owner has supplied
a completed Tripoli Python execution bundle and subsequent GEE console evidence.
The [Tripoli comparison](wp04-tripoli-comparison.md) found all recorded observation
groups equal. Other WP04 acceptance cases remain open; this probe comparison does
not establish full-raster or all-input equivalence.
No scientific accuracy assessment or change to the model is part of this work.

The owner has now supplied a concrete Tripoli case. The [prepared Colab notebook
and case configuration](../examples/wp04-tripoli/README.md) use those exact project
and asset identifiers. See the [first Python run review](wp04-tripoli-run-review.md)
for the initial inspection, and the comparison above for the completed Tripoli case. The notebook is committed
without executed outputs.

The GEE reference remains byte-identical to WP01, SHA-256
`1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4`.
The WP03 engine and adapter are also unchanged. Package version `0.4.0` identifies
the new runner; the underlying engine still reports implementation version `0.3.0`.

## 1. Install the branch and validate a request

This PR is stacked on WP03. Until the preceding PRs and this one are merged, install
the explicit branch, not `main`. Use a clean committed checkout for the source SHA.

```sh
git clone https://github.com/hamedsabzchi/libya-automated-land-cover-mapping.git
cd libya-automated-land-cover-mapping
git checkout feat/wp04-installable-runner
python -m venv .venv
. .venv/bin/activate
python -m pip install .
libya-landcover --version
```

The distribution is `libya-landcover-assistant`; the import and command are
`libya_landcover` and `libya-landcover`. Python 3.10 or newer is required; CI uses
3.12. The tested EE client is pinned at `1.7.48`. Existing `python` and `contracts`
imports remain supported. The notebook's separate geemap dependency is not required
by this command-line runner. Do not install the legacy notebook requirements over
the pinned runner environment when collecting reproducible observations.

Create `runs/input/request.json` locally with the actual authorized assets. For example:

```json
{
  "request_id": "11111111-1111-4111-8111-111111111111",
  "aoi_asset": "projects/YOUR_PROJECT/assets/YOUR_SMALL_AOI",
  "training_asset": "projects/YOUR_PROJECT/assets/YOUR_TRAINING",
  "class_field": "lc_code",
  "target_year": 2024,
  "year_count": 5,
  "fallback_year": 2023,
  "train_fraction": 0.7,
  "trees": 500
}
```

Replace the placeholder paths and use a new UUID for a new request. Neither this
example nor `contracts/examples/` is a completed live run. The default author AOI
and training paths in the legacy notebook are never selected silently by this CLI.

```sh
libya-landcover validate runs/input/request.json
```

Validation prints the resolved request, fingerprint and full engine settings. It
does not authenticate, initialize EE or query assets. The remaining reference-mode
settings are fixed by WP02: 10 m, 14 seeds, 60% threshold, excluded class 8, bag
fraction 0.95 and tileScale 16.

## 2. Initialize an authorized account and project

Run the normal client login on your own machine or Colab environment. Do not put
credentials, tokens, service-account keys or real run bundles into GitHub.

```sh
earthengine authenticate
libya-landcover doctor --project YOUR_AUTHORIZED_EE_PROJECT
```

`doctor` only checks initialization. It does not prove that both requested assets
are accessible; the unchanged engine preflight does that during `run`. It never
initiates login on its own. A failed doctor returns exit code 3. In the development
environment for this delivery, initialization failed because authentication was not
configured; no live computation or export was started.

## 3. Define bounded, identical raster observations

Create `runs/input/probes.json` with 1–1000 explicit locations inside and around
the agreed small AOI, including a boundary or known masked location where useful.
Use the same file for Python and the GEE diagnostic session. Coordinates are WGS84
longitude/latitude; `crs` and the six-element affine `transform` define the exact
pixel grid used for reading both outputs. Example structure only:

```json
{
  "crs": "EPSG:32633",
  "transform": [10, 0, 0, 0, -10, 0],
  "points": [{"id": "p1", "lon": 13.2, "lat": 32.8}]
}
```

These example coordinates are not an agreed AOI or a live observation. Choose the
CRS, grid origin and locations for your actual case. No random location, grid or
reprojection override is inserted into the model. The supplied grid is used only
by the separate observation request. Each final/annual map is read together with
its mask; masked values are represented as -9999 and their mask is recorded.

## 4. Run Python and save the selected output

```sh
libya-landcover run runs/input/request.json \
  --project YOUR_AUTHORIZED_EE_PROJECT \
  --engine-commit "$(git rev-parse HEAD)" \
  --output runs/case-01 \
  --probes runs/input/probes.json
```

`--output` must be a new directory. The runner refuses reuse; it does not silently
overwrite results or automatically retry the model. The engine executes its normal
preflight, seed search and selected-result preparation. After that, `--probes` adds
split-ID and bounded raster observation queries. `--capture-evidence` without
`--probes` records split IDs and numerical observations but leaves raster evidence
explicitly missing. With neither option, only the model run bundle is saved.

| File | Meaning |
| --- | --- |
| `request.json` | Resolved, validated request |
| `status.jsonl` | One validated status snapshot per line, flushed during execution |
| `status.json` | Last engine status after the synchronous adapter returns |
| `result.json` | WP02 result: selection, existing metrics, provenance and image references |
| `class-table.json` | Existing reference display calculations |
| `graphs/index.json` | Run-scoped artifact IDs, filenames, SHA-256 checksums and EE version |
| `graphs/<artifact_id>.json` | Selected final/annual serialized EE graphs |
| `python-evidence.json` | Optional live observations for comparison |
| `manifest.json` | Runner state, evidence state, project, source fingerprints and provenance declaration |

The graphs are executable definitions, **not GeoTIFF files or cached pixel data**.
They still reference EE assets; restoring them requires the same client version and
an authorized initialized session. They do not freeze asset contents or guarantee
future reproducibility if upstream assets change. `completed` means the selected
metrics and graphs were produced; it does not mean every output pixel was exported.

The source commit is caller-asserted, as in WP03. The runner records SHA-256 of the
installed engine, adapter and contracts so the claim can be checked later; it does
not falsely label a user-provided SHA as independently verified. Use a freshly
installed wheel from the stated clean commit. The bundle is a local evidence folder,
not a multi-user artifact service, job queue, authorization system or resume engine.

To restore a saved image without rerunning seed search:

```python
import json
import ee
from libya_landcover.bundle import GraphArtifactStore

ee.Initialize(project="YOUR_AUTHORIZED_EE_PROJECT")
with open("runs/case-01/result.json", encoding="utf-8") as stream:
    result = json.load(stream)
final = result["outputs"][0]
image = GraphArtifactStore("runs/case-01").get(result["run_id"], final["artifact_id"])
```

No Drive/Cloud Storage export, task creation or public download happens in WP04.
Those are the next output-service work package.

## 5. Observe the unchanged GEE model

```sh
libya-landcover prepare-reference \
  --reference gee/automated_land_cover_app.js \
  --probes runs/input/probes.json \
  --output reference-session.js
```

This command first checks the pinned SHA-256, then creates a **separate local session
file** whose prefix is the exact original reference bytes. It appends the separately
versioned `libya_landcover/gee_observer.js`; it never writes to the reference file.
The observer adds one diagnostic button. It does not replace model functions, change
RUN handlers, alter settings or train another model. The generated session is ignored
by Git and is not a proposed replacement for the reference app.

Open this temporary session in the Earth Engine Code Editor with the authorized
account. Set the app's controls to the settings printed by `validate`, click the
original RUN button, and wait for completion. Then click **WP04: capture execution
observations** and copy the complete printed JSON string to
`runs/case-01/gee-evidence.json` (without console labels or surrounding string quotes).
Keep both runs close in time, with unchanged asset contents and the same EE access.

The observer reads `APP.best` and `APP.cfg`, existing selected metrics and retained
maps. For normalized/training IDs it calls the existing reference normalization/split
helpers with the selected seed; validation IDs come from the retained `best.val`.
No classifier is rebuilt. The sampled validation count is the sum of the already
returned reference confusion matrix; it is not a new evaluation method. The flattened
producer entries reflect the retained reference result, not the original raw response
shape. A changed/started run invalidates pending observation callbacks. Failed queries
do not emit complete evidence. Large training-ID lists may exceed client/console
limits; such a failure is incomplete evidence, never a successful comparison.

## 6. Compare observations and record the outstanding cases

```sh
libya-landcover compare \
  runs/case-01/python-evidence.json \
  runs/case-01/gee-evidence.json > runs/case-01/comparison.json
```

The comparison enforces the pinned reference and supported settings. It compares
actual configuration, selected seed/stop reason, existing metrics/counts, normalized
and split ID lists, and classes/masks at the explicit probe grid. IDs are compared
as sorted lists, preserving duplicates. Configuration, IDs, counts and raster values
are exact; floating numerical observations use absolute tolerance 1e-9, relative 0.

| Result / exit code | Meaning |
| --- | --- |
| `observations_match` / 0 | All recorded observation groups agree for this case |
| `different` / 1 | At least one observed field differs; report includes its path |
| `incomplete` / 4 | No observed mismatch, but one or more required groups are absent |
| Command error / 2 | Invalid input, unreadable files, existing destination or runner error |
| Initialization failure / 3 | EE initialization failed before model execution |

The `run` command also returns 1 for a recorded engine failure, and 4 if the model
completed but the requested diagnostic capture failed. Read the manifest and saved
status to distinguish these outcomes. A partial capture without requested probes
can return 0 from `run`; `compare` still reports missing raster evidence.

Matching explicit probes is not a proof of full-raster equality. The comparison
always reports `full_raster_parity_proven: false`. It cannot certify fabricated
observations, inspect immutable asset revisions, or recover unrecorded raw array
shapes. Never replace a missing GEE observation with the Python result.

Remaining live acceptance work, inherited from WP01 O01–O05:

- Ordinary agreed AOI: collect both records and resolve any port discrepancy in Python.
- Missing target-year / partially masked target input: observe fallback behavior with
  appropriate accessible inputs; do not manufacture training data or change GEE.
- Multi-feature AOI: observe the existing `clip(roi)` call and boundary/mask behavior.
- Failure cases: record real asset/coverage/seed failure handling where reproducible.
- Record raw server array shapes if needed to resolve a concrete mismatch; this
  companion captures retained normalized values, not the transient raw responses.

Keep this work package open until the agreed live cases and their limits are recorded.
The next assistant-service work can use this installable interface, but must not
assume that live equivalence has already been demonstrated.

## Verification delivered

- 65 offline unittest cases: existing 49 plus 16 runner/graph/evidence checks.
- Real EE-client graph serialization, artifact round-trip and explicit probe graph
  construction using the client's official offline fixtures; network disabled there.
- Wheel build, install and CLI exercise outside the source checkout.
- Generated reference session JavaScript syntax and byte-identical reference prefix.
- CI repeats installation, CLI and offline checks; it needs no EE credentials.

These checks establish package/orchestration behavior. They are not live model runs,
not accuracy tests and not evidence of Python/GEE server-output equality.
