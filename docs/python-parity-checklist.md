# WP01 — Python parity checklist

Prepared: 2026-10-15. Baseline commit:
`4c92894ec292ffa549275948d8d43f6cb8f89a8b`.

The GEE implementation is fixed and authoritative. All implementation changes
identified here are for Python or the future assistant adapter; none authorize
changes to GEE or changes to its modeling/assessment methods.

See [GEE reference specification](gee-reference-spec.md) for requirements R01–R20,
hashes, effective call paths and runtime observations O01–O06.

## Evidence and status meanings

- **Code match:** the specified local behavior is present in source; not a claim
  of complete runtime equivalence or identical end-to-end maps.
- **Needs alignment:** a concrete implementation difference is visible.
- **Not implemented:** the corresponding behavior is absent.
- **Runtime check:** source alone does not establish the behavior's equivalence.

**J** line references point to the pinned
[GEE source](https://github.com/hamedsabzchi/libya-automated-land-cover-mapping/blob/4c92894ec292ffa549275948d8d43f6cb8f89a8b/gee/automated_land_cover_app.js).
**P** line references point to the pinned
[Python source](https://github.com/hamedsabzchi/libya-automated-land-cover-mapping/blob/4c92894ec292ffa549275948d8d43f6cb8f89a8b/python/landcover_engine.py).

## Traceability matrix

| ID / reference | Python location | Status | Required work or retained behavior |
| --- | --- | --- | --- |
| C01 / R01 defaults | `LandCoverConfig`, P48–67 | Needs alignment | Keep matching year/window/fallback/RF/seed defaults. Public assistant must request assets as GEE does, rather than silently using author-specific P29–30 defaults. Force effective model scale to 10 as J1446–1455 does. |
| C02 / R01 parser | `validate_config`, P70–101; `get_embedding`, P111–121 | Needs alignment | Document numeric coercion/rounding and year-window handling. Python rejects pre-2017 windows locally; GEE builds the requested years then runs availability checks. Python does not enforce the reference excluded-class bound. Specify the typed adapter boundary in WP02 while retaining model rules. |
| C03 / R02 asset input | `load_assets`, P131–147 | Not implemented | Add the reference asset-path normalization before FeatureCollection construction; support both project and users paths and the supported pasted URL form. |
| C04 / R03 classes | constants P33–45 | Code match | Ordered codes/names/palette and default ordered seeds match (palette differs only by `#` notation). Preserve ordering. |
| C05 / R04 preflight | `asset_diagnostics`, P385–396; `load_assets` | Needs alignment | Existing diagnostics do not implement AOI area, raw histogram, usable total, represented-class minimum or per-class minimum checks and error branches. Add a preflight before seeds with the reference branch order. |
| C06 / R05 labels | `load_assets`, P137–146 | Needs alignment | Replace direct Number.parse of each property with the reference histogram lookup/null-filter/domain-filter behavior. Retain all usable national features and feature identities. |
| C07 / R05 national scope | `load_assets`, P131–147 | Code match | Python does not spatially filter training to the mapping AOI. Retain this behavior while changing normalization. |
| C08 / R06 coverage | `build_embeddings`, P156–164; public smoke helper P358–373 | Not implemented | Add per-year collection-count preflight separately for full training and AOI, including reference target/fallback acceptance logic. Public smoke helper is not this preflight. |
| C09 / R07 annual retrieval | `get_embedding`, `build_embeddings`, P111–121, P156–164 | Code match | Collection ID, annual dates, filterBounds/mosaic and target-only unmask chain match for supplied geometry and supported years; geometry separation is C10 and boundary handling C02. Runtime fallback observation remains O03. |
| C10 / R07 footprints | `processing_geometry`, P150–153; `build_seed_model`, P208–243 | Needs alignment | Replace union geometry with separate full-normalized-training bounds and AOI bounds; build national and AOI predictor images independently for each year. |
| C11 / R08 terrain | `terrain_image`, P124–128 | Needs alignment | Apply unmask(0) separately to all three terrain images, in the same order as J3766–3771. Retain names and predictor concatenation order. |
| C12 / R09 split | `stratified_split`, P167–182 | Needs alignment | Replace threshold random split with sorted represented classes, `_flex_random`, sort, floor/clamp counts and list slicing/flattening exactly as J3518–3543. Preserve feature IDs; observe split IDs in O01. |
| C13 / R10 RF operations | `build_seed_model`, P218–236 | Code match | sampleRegions options, non-null predictor filtering and explicit RF parameters match conditional on corrected upstream inputs and fixed scale. Preserve remaining RF defaults. |
| C14 / R10–R11 AOI outputs | `build_seed_model`, P237–243 | Needs alignment | Classify AOI predictors separately and apply temporal decision to the AOI annual dictionary. Current final_map is clipped from the national validation map. Align construction; observe clipping/masks in O04. |
| C15 / R11 temporal operations | `temporal_decision`, P185–202 | Code match | Ordered mode and four where replacements, counts, priority band and output name match. Preserve order, including priority restoration when both counts >=2. |
| C16 / R12 sampling/matrix | `build_seed_model`, P244–253; `metrics_dictionary`, P271–281 | Code match | National validation sampling, class order, overall/kappa/producer/confusion calls match conditional on upstream alignment. Retain current model calculations. |
| C17 / R12 metric payload | `metrics_dictionary`, P271–281 | Needs alignment | Expose sampled validation count evaluated in the reference. Distinguish this count from the pre-sampling validation features. Python additionally computes consumersAccuracy; retain reference displayed user-value formula/zero-column behavior in result adapter. |
| C18 / R12 score | `evaluate_seed`, P292–306 | Needs alignment | Apply confusion-row count >0, exclusion and finite-value filtering; reject a candidate with no scored classes. Current code only excludes the configured class before taking min. Preserve threshold and minimum-score rule. |
| C19 / R12 shape conversion | `_flatten_vector`, P284–289 | Runtime check | Capture real evaluated payload shapes and compare conversion with J3834–3851. Do not declare a runtime bug based only on hypothetical array shape. Add compatible normalization only as evidenced/required for parity. |
| C20 / R13 order/ties/stop | `search_seeds`, P309–332 | Code match | Default ordered sequential traversal, strict greater-than replacement and threshold early stop match for successful comparable candidates. The assistant's reference mode must keep stop_when_target_reached=True. |
| C21 / R13 failed candidates | `search_seeds`, P322–330 | Needs alignment | Continue on candidate metric-evaluation failures and no-scored-class outcomes; retain last error; return best on exhaustion or a controlled no-result failure. Current exception aborts the loop. |
| C22 / R13 selected objects | `search_seeds`, P331; `build_seed_model` return P255–268 | Needs alignment | Return the selected candidate's already-built objects rather than rebuilding the selected seed after search. Keep map/yearly/classifiers bound to its metrics. No tree-text materialization is required. |
| C23 / R14 lifecycle | engine call functions; no run manager | Not implemented | Define run phases/errors in WP02 and persist/track in WP05. Represent stale-result protection and settings identity outside the pure model. Do not advertise mapping cancellation as an existing GEE feature. |
| C24 / R15 result data | `build_seed_model`, `metrics_dictionary`, `search_seeds` | Needs alignment | Assemble one result carrying selected seed/score, configuration, annual/final maps, class order, raw metrics, confusion matrix and class table. Keep EE objects internal and serializable metadata separate in WP02. |
| C25 / R15 map display | Colab notebook, code cells | Needs alignment | Existing notebook shows a selected final layer; the assistant UI later needs annual layers, fixed legend, results and download affordances. GEE widget code itself is UI-only. |
| C26 / R16–R18 direct export | `start_drive_export`, P335–355 | Not implemented | Drive export is a different delivery path. Later output work needs reference UTM/aligned grid, exact dimensions, one candidate file/cell, class mask, zero fill, empty-cell checks, filename and ZIP URL behavior. Do not mark Drive helper as direct-download parity. |
| C27 / R19 download state | no counterpart | Not implemented | Later adapter must support 20-successful-link pages, retry/current-cell state, refresh and invalidation without retraining. Keep mapping and downloading status separate. |
| C28 / R20 assistant boundary | module returns live EE objects; no service | Not implemented | WP02 defines RunRequest/RunStatus/RunResult; WP05–WP08 add persistent execution, outputs, tools and conversation. This does not alter the model. |

## Concrete implementation order after WP01

Each item is future work, not code delivered by this documentation PR.

| Work package | Checklist rows | Deliverable / acceptance evidence |
| --- | --- | --- |
| WP02 — contracts | C01–C03, C17, C23–C24, C28 | Explicit reference-mode inputs, fixed 10 m behavior, phases/errors, result schema and EE-object boundary. Document hidden model settings and parsing differences; no arbitrary assistant changes to them. |
| WP03-A — inputs/preflight | C03, C05–C08 | Normalized asset paths; reference histogram/label logic; ordered asset/class and collection availability checks. Software fixtures cover valid/invalid labels and reference error branches. |
| WP03-B — graph parity | C10–C12, C14 | Separate training/AOI predictor graphs, terrain masks, reference split, AOI temporal output. Retain C04/C07/C09/C13/C15/C16 behaviors. |
| WP03-C — selection/results | C17–C22, C24 | Reference scoring, failed-candidate continuation, first-on-tie selection, threshold stopping and retained selected graph with associated metrics. |
| WP04 — execution comparison | C09/C12–C16/C19/C22; O01–O05 | Run the same assets/config/seed against fixed GEE reference; record input identities, split IDs/counts, shapes, selected seed and output/mask comparison. Resolve port differences in Python. This is not a reassessment of the model's scientific validity. |
| WP05–WP08 — assistant | C23–C28; O06 | Persistent run tracking, output service and analysis metadata, tool API, chat/map UI. Preserve R16–R19 when exposing the reference direct-download capability. |

## Result payload mapping for WP02

Names below are proposed adapter mappings, not a finalized JSON schema or new
model behavior. The contract work must settle serialization and storage details.

| GEE object / field | Python source today | Adapter consideration |
| --- | --- | --- |
| `cfg`, `roi` | `LandCoverConfig`, model `roi` | Store resolved inputs and baseline code identity; keep geometry/EE handles internal |
| `best.seed`, `best.score` | `best_metrics.seed`, `minimum_producer_percent` | Associate with one selected run and the exact candidate objects |
| `best.map`, `best.yearly`, `best.classifiers` | model `final_map`, `yearly`, `classifiers` | Internal EE objects; expose map/output references, not object string representations |
| `best.overall`, `kappa`, `prod`, `conf` | `overall`, `kappa`, `producer`, `confusion` | Store numeric arrays in fixed class order; percentages/rounding are presentation rules |
| sampled `validationCount` | not currently returned in metrics | Store separately from model `validation_points` collection count |
| class table J458–489 | not assembled | Include code/name, producer/user percentage, row sample count, included/excluded state |
| asynchronous progress/errors | exceptions / synchronous returns | Define stable phases and errors without reinterpreting seed selection |

## WP01 verification and limitations

- Both local source blob hashes match the GitHub tree at the recorded commit.
- Reference GEE SHA-256 and Python SHA-256 are recorded in the companion document.
- Effective final event bindings, configuration/finish wrappers, selection flow,
  download planner and queue were traced by source inspection.
- Every R01–R20 behavior has a corresponding matrix row; C01–C28 have an explicit
  status and next action or preserved behavior.
- No model, Python implementation, existing test, or README changes are included.
- No live Earth Engine run, asset read, export, scientific assessment, or end-to-end
  equivalence claim is part of WP01. O01–O06 identify the follow-up observations.
- GitHub publication is complete when both documents are committed on
  `docs/wp01-gee-reference`, linked by a WP01 Issue and open PR, and the remote
  diff contains only these additions with unchanged source blobs. Merge remains
  a separate action.

If later work finds an undocumented reference behavior, add an evidence-linked
clarification to these documents and align Python. Do not edit the GEE reference
to make the port easier.
