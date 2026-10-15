# WP02 — Assistant/engine contracts v1.0

Status: executable contracts and offline examples; **not yet wired to the engine**.
Prepared: 2026-10-15. Depends on WP01 and its
[immutable reference specification](gee-reference-spec.md) and
[Python parity checklist](python-parity-checklist.md).

The GEE reference and existing Python engine are unchanged. This package defines
the boundary a later Python port, run manager and chatbot will share. It neither
executes nor modifies the model. The model's existing calculations and selection
rules remain authoritative.

## Deliverables and execution

- `contracts/models.py`: validated `RunRequest`, `RunStatus`, `RunResult`, state
  transition validation, cross-payload identity checks and class-table projection.
- `contracts/__main__.py`: command-line validation.
- `contracts/examples/`: clearly synthetic JSON fixtures.
- `tests/test_contracts.py`: offline contract tests.
- `.github/workflows/contract-tests.yml`: dedicated dependency-free CI.

Python 3.10+; standard library only. Run from repository root:

```sh
python -m contracts request contracts/examples/request.json
python -m contracts status contracts/examples/status-running.json contracts/examples/status-completed.json contracts/examples/status-failed.json
python -m contracts result contracts/examples/result.json
python -m contracts exchange contracts/examples/request.json contracts/examples/status-completed.json contracts/examples/result.json
python -m unittest discover -s tests -p 'test_contracts.py' -v
```

Payload validators accept dictionaries or JSON strings via `from_dict`/`from_json`;
`to_dict` returns a copy and `to_json` emits strict JSON. Unknown fields, duplicate
JSON keys, NaN/Infinity, booleans used as numbers and unsupported versions are
rejected. Validation failures raise `ContractError`. No `ee` import, authentication,
network request, background task or model run occurs.

## 1. RunRequest

| Field | Type | Required / default | Reference meaning |
| --- | --- | --- | --- |
| `schema_version` | string | `1.0` | Wire version |
| `mode` | string | `gee_reference_v1` | Current fixed GEE reference behavior |
| `request_id` | canonical UUID string | Required | Client submission/idempotency identity |
| `aoi_asset` | canonical EE asset path | Required | No author-specific fallback |
| `training_asset` | canonical EE asset path | Required | All valid national training features |
| `class_field` | nonempty trimmed string | `lc_code` | Training label property |
| `target_year` | integer 2017–2024 | `2024` | Priority year |
| `year_count` | integer 1–20 | `5` | Descending annual window |
| `fallback_year` | integer 2017–2024 | `2023` | Target-year fallback |
| `train_fraction` | number 0.01–0.99 | `0.7` | Existing split control |
| `trees` | integer 1–5000 | `500` | Existing RF tree count |

`to_dict()` resolves every optional default. `engine_config()` supplies the above
model fields and the reference hidden settings: threshold 60%, excluded class 8,
bag fraction 0.95, the ordered 14 seeds, scale 10 m and tileScale 16. It is a mapping
for WP03, **not** an invocation of the existing `LandCoverConfig`. These hidden
settings are not free-form chatbot arguments. Unknown overrides such as `scale_m`
or `seeds` in a public request are rejected, not silently ignored. Names align
with the existing Python configuration to make integration explicit.

The client should collect missing assets rather than guessing an asset ID. The
request represents a fully specified user intention; partial conversational state
is kept outside it. Download prefix, grid size, page/resume settings and display
language also remain outside the model request. Later output tools get separate
contracts; a download change must not retrain the model.

### Typed boundary versus the GEE textbox parser

This is an explicitly narrower typed assistant boundary, not a redefinition of
GEE behavior. Integers must be JSON integers; numeric strings, fractional years,
booleans and automatic rounding are not accepted. Fractions are normalized to
float. Canonical `projects/.../assets/...` (including legacy) and `users/...` paths
are accepted. The conversational/UI adapter must apply WP01 R02 normalization to
pasted URLs/quoted paths **before** constructing the request; this package does
not implement that normalizer. Asset existence, permissions, geometry/schema,
class availability and image coverage remain engine preflight checks in WP03.

Like the GEE parser, the contract allows `year_count` up to 20 even when the derived
window extends before 2017. Such a request is structurally valid; the reference
availability preflight decides its executable outcome. The existing Python early
window rejection is recorded in WP01 C02 and remains WP03 work. The contract does
not widen the fixed target/fallback year bounds based on today's data catalog.

### Identity, fingerprint and idempotency

`request_id` is a client-generated UUID reused when retrying the same submission.
`run_id` is a server-generated UUID for a mapping run; `result_id` identifies its
selected result. The service stores a request_id → fingerprint/run_id association
**within the authenticated owner scope**. Same ID and fingerprint returns the
existing run; same ID and different fingerprint is an idempotency conflict. A new
request_id permits an intentional new run with the same settings. The fingerprint
alone is not a cross-user cache key or authorization mechanism.

`fingerprint()` computes SHA-256 over UTF-8 JSON with sorted keys, compact separators,
and these fields: schema version, mode, fixed GEE commit/hash and the fully resolved
engine_config. It excludes request_id and download/UI state. Equivalent implicit
and explicit defaults therefore match. This is an algorithm defined by this Python
implementation, not a general claim of RFC canonical JSON. The fingerprint records
configuration identity; it does not freeze mutable EE asset contents. Record dataset
versions/snapshots separately when that capability is added.

## 2. RunStatus

All fields are required: `schema_version`, `run_id`, `request_id`,
`request_fingerprint`, `revision`, `state`, `phase`, `created_at`, `updated_at`,
`progress`, `error`, `result_id`. Timestamps are UTC RFC3339 ending in Z; update
time cannot precede creation. Revision is a nonnegative integer incremented for
each persisted update. Revision ordering, not guessed percent completion, handles
delayed polling responses. Clients discard older snapshots.

| State | Allowed phase | Meaning |
| --- | --- | --- |
| `queued` | `queued` | Accepted for background execution |
| `running` | `asset_preflight`, `coverage_preflight`, `seed_search`, `preparing_result` | Engine work or final result assembly |
| `exporting` | `preparing_outputs` | Optional initial output preparation required by the service before completing this run |
| `completed` | `completed` | Selected result and stable map artifact references are available |
| `failed` | `failed` | Run ended without a deliverable result; typed terminal error provided |

Allowed transitions: queued → running/failed; running → running/exporting/completed/
failed; exporting → exporting/completed/failed. Terminal states have no outgoing
transition. A user-requested retry after terminal failure creates a new request/run.
Within running, phase order cannot move backwards; seed index cannot decrease.
`validate_transition` checks consecutive persisted snapshots, requiring revision+1,
unchanged identity/creation time and nondecreasing update time. Polling clients may
skip intermediate snapshots and should not apply this adjacency validator to them.

`progress` is null except during seed_search. There it contains 1-based `seed_index`,
`seed_count=14`, and `current_seed` matching the pinned ordered seeds. It does not
claim a percentage or ETA: early stopping and skipped seeds make those misleading.
`result_id` is populated only for completed state. `error` is populated only for
failed state. A failed seed followed by another attempt is not a failed run.

Mapping cancellation is not exposed in v1. Download paging/pause/retry is a distinct
later output-job lifecycle (WP01 R19). A subsequent optional GeoTIFF export must
not move an already completed mapping run backwards to exporting or failed.

### Errors

Terminal `error` fields: `code`, `phase` (the stage that failed), safe human-readable
`message`, and boolean `retryable`. A failed status uses phase=failed while
error.phase retains the original stage. `retryable` is advice, not an instruction
to automatically restart expensive work. Credentials, tokens and raw internal
stack traces do not belong in this payload.

| Code | Reference/service condition |
| --- | --- |
| `INVALID_REQUEST` | Contract/input validation; normally returned before run creation |
| `ASSET_ACCESS_OR_SCHEMA` | Reference asset/schema query failed; do not invent a more specific cause |
| `EMPTY_AOI`, `EMPTY_TRAINING` | Reference preflight branches |
| `INVALID_CLASSES`, `INSUFFICIENT_CLASSES`, `INSUFFICIENT_CLASS_SAMPLES` | Reference usable class/count branches |
| `COVERAGE_QUERY_FAILED`, `COVERAGE_UNAVAILABLE` | Reference coverage query/availability branches |
| `SEED_EVALUATION_FAILED`, `NO_SCORED_CLASSES` | Candidate events; normally recorded and followed by next seed, not emitted as terminal run errors |
| `NO_SUCCESSFUL_SEED` | Seed exhaustion with no best candidate |
| `OUTPUT_PREPARATION_FAILED` | Required initial output preparation failed |
| `INTERNAL_ERROR` | Adapter/runtime error outside the specifically handled reference branches |

Error translation, persistence, access control and idempotency enforcement are
service responsibilities in later work packages; these validators do not implement
a service or replace the reference error/continuation behavior.

## 3. RunResult

All fields are required: `schema_version`, `result_id`, `run_id`, `request_id`,
`request_fingerprint`, `created_at`, fully resolved `request`, `provenance`,
`selection`, `metrics`, `outputs`.

- `provenance`: exact `gee_reference_commit` and `gee_sha256`, actual deployed
  `engine_commit` (40 lowercase hex characters) and `engine_version`. The example
  engine identity is a labelled fixture; a real worker must fill its actual build.
- `selection`: selected integer `seed`, `minimum_producer_percent` (0–100),
  `target_reached`, `stop_reason` (`target_reached` or `seeds_exhausted`). Threshold
  consistency is checked against the existing 60% setting. There is no alternative
  model-scoring rule in this package.
- `metrics`: raw `overall` fraction, `kappa`, 12-element `producer` fractions in
  class order, 12×12 nonnegative-integer `confusion`, and `sampled_validation_count`.
  The count must equal the matrix total for the fixed 1–12 domain. Do not substitute
  the pre-sampling validation-feature count for sampled_validation_count.
- `outputs`: one final_map at target year, followed by one annual_map for every
  descending requested year. Each has a unique UUID `artifact_id`, `kind`, `year`
  and `reference=artifact://<artifact_id>`. These are stable opaque service records,
  not an EE object dump or a promise of a public URL. The future artifact resolver
  must authorize access and supply current display/download URLs. Map references
  do not imply that every GeoTIFF has already been exported.

Nonfinite EE metric values must be normalized by the future adapter to JSON null;
raw overall/kappa/producer permit null. The adapter should record normalization in
its logs. Selection score must be finite for a successful selected result. The
contract checks structure/consistency, not model accuracy. It does not recompute or
replace the RF, temporal rules, metrics or selected seed.

`RunResult.class_table()` exposes the fixed class order/names/palette, producer
percentage, the GEE displayed user percentage (`diagonal/column sum *100`, zero
for empty column), row sample count and Included/Excluded flag (class 8 excluded).
For null producer, the displayed percentage is zero to follow GEE's falsy fallback;
raw metrics retain null so the chatbot can distinguish unavailable from measured
zero. Formatting/rounding stays in the UI. The class table is derived rather than
duplicated in JSON, avoiding two conflicting values. No class-area values are
invented; those require output analysis in WP06.

The final downloadable classification has band name `classification`, classes
1–12, UInt8 delivery, 10 m grid and filled zero outside/missing pixels according
to WP01 R16–R18. Actual CRS, transform, dimensions, filename and links belong in
the later artifact/export manifest, not an assumed fixed CRS in this model result.
Live `ee.Image`, `ee.Classifier`, FeatureCollection objects and credentials remain
inside the engine/service boundary.

`validate_exchange(request, status, result)` checks request/run/result linkage,
fingerprint and result timestamp within the completed run interval. This is the
boundary the chatbot must use to avoid answering from a different run. A completed
status can be checked alone before fetching its result separately.

## 4. Minimal integration handoff

```python
from contracts import RunRequest, RunStatus, RunResult, validate_exchange

request = RunRequest.from_json(request_text)
resolved_inputs = request.engine_config()  # Pass to the WP03 adapter, not a run here.
fingerprint = request.fingerprint()
# Later: worker executes the fixed model; service constructs status/result payloads.
status = RunStatus.from_json(status_text)
result = RunResult.from_json(result_text)
validate_exchange(request, status, result)
class_table = result.class_table()
```

WP02 covers WP01 C01–C03's typed boundary (path normalization remains WP03), C17,
C23–C24 and C28 contracts. WP03 must resolve existing Python differences before
wiring `engine_config()` to a real run. WP05 supplies run storage, revisions,
idempotency and artifact records; WP07 supplies tools; WP08 supplies chat/UI.

Breaking wire changes require a new schema version and matching validators. v1.0
rejects unknown keys deliberately; new optional product features need a documented
version change instead of silently appearing in old payloads.

## 5. Acceptance and branch dependency

WP02 is complete when the examples validate, negative/identity/transition tests
pass, the remote diff contains only contract/docs/test/workflow additions, and the
GEE and existing engine hashes remain identical to WP01. No live EE run is needed
for this contract milestone. PR is stacked on the WP01 branch while PR #2 is open;
merge WP01 first, then retarget WP02 to main before merging. No automatic merge is
part of this work package.
