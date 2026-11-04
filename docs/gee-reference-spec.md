# WP01 — GEE reference behavior specification

Status: source inspection complete; runtime observations explicitly deferred below.
Prepared: 2026-10-15. Scope: the existing GEE application is the authoritative model.
This document describes its behavior for a Python port. It does not propose changes
to the GEE source, model methodology, selection rules, or accuracy assessment.

## 1. Immutable baseline and evidence

| Item | Recorded value |
| --- | --- |
| Repository | `hamedsabzchi/libya-automated-land-cover-mapping` |
| Reference branch at inspection | `main` |
| Reference commit | `4c92894ec292ffa549275948d8d43f6cb8f89a8b` |
| GEE path | `gee/automated_land_cover_app.js` |
| GEE Git blob SHA-1 | `d60a7ad47c1a5c4648f4d69cbd39841c744e0110` |
| GEE byte length | `146773` |
| GEE SHA-256 | `1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4` |
| Python comparison path | `python/landcover_engine.py` |
| Python Git blob SHA-1 | `fff24a79da5e0eac8493841e3961001c6fab8d60` |
| Python SHA-256 | `4e33aeb314215ed2a8cdb522299b9ce7f0839e6bf9b3c7464cd302fb30775ffb` |

The local files' computed Git blob hashes match the pinned GitHub tree. SHA-256 is
computed on the exact file bytes, including line endings. The reference SHA is a
baseline identifier, not a request to update the reference when Python changes.

All **J** source citations below refer to this pinned
[GEE file](https://github.com/hamedsabzchi/libya-automated-land-cover-mapping/blob/4c92894ec292ffa549275948d8d43f6cb8f89a8b/gee/automated_land_cover_app.js).
For example, J3518–3543 means lines 3518–3543 of that file. **P** citations in the
[companion checklist](python-parity-checklist.md) refer to the Python file at the
same commit. Runtime equivalence has not been asserted or tested in WP01.

## 2. Effective entry points and retained overrides

Follow assignments and final event bindings, not the first function with a
familiar name. The final RUN binding is `flexibleRunCompleteAssets` (J3893–3895).

| Stage | Effective implementation and source |
| --- | --- |
| Parse inputs | `normalizeVisibleAssetBoxes`; final `readConfig` wrapper J3000–3037 → fixed-scale wrapper J1445–1455 → original parser J188–217 |
| Preflight and orchestration | `flexibleRunCompleteAssets`, J3625–3891 |
| Labels | `flexibleBuildClassLookup` and `flexibleNormalizeTraining`, J3486–3514 |
| Split | `flexibleStratified`, J3518–3543 |
| Annual predictors | `flexibleEmbeddingCollection` / `flexibleEmbeddingImage`, J3469–3484; terrain J3766–3771 |
| Train and classify | `flexibleMakeMap`, J3565–3614 |
| Temporal result | `flexibleTemporalDecision`, J3545–3563 |
| Select candidate | local `attempt`, J3779–3888 |
| Deliver selected objects | assigned `materializeBestModel`, J1828–1839; retains native classifier-backed images and calls `finish` |
| Complete/display | final `finish` J3081–3086 → wrapper J2052–2056 → wrapper J1785–1797 → original J559–590 |
| Download entry | `simple10Click`, J1751–1768, bound at J3897–3902 |
| Download queue | `simple10Next = valid10Next`, J2942–2943; implementation J2811–2940 |
| Grid plan | wrapper J3387–3398 → implementation J2611–2643 → captured original extent planner J1554–1583 |
| Completion grid adjustment | final `flexibleAdjustGridForAoi`, J3418–3467 |
| Button state | `simple10Sync = finalDirectSync`, J2581–2604 |

The original `run`, `stratified`, `makeMap`, and later `runWithUserAssets` are not
the final RUN path. The original decision-tree text materialization (J352–399)
is replaced by J1828–1839. The earlier Drive export button callback is replaced
by the final direct-download binding. Preserve these files as-is; Python must
implement the effective path, not copy obsolete branches or descriptive text.

The finish wrapper still calls `cache10Prepare` conditionally. That helper returns
immediately with the shipped `LC10_CACHE.prepareInCodeEditor = false` and blank
asset ID (J1819–1826, J1904–1905). Owner-enabled cache export is not part of the
default reference execution. The later finish wrapper calls the **final** grid
adjustment by name, so the old small-AOI-only adjustment is superseded.

## 3. Inputs and parsing — R01–R03

**R01 — Configuration.** Defaults below describe the final initialized interface,
not just the first widget declarations (J105–140, J188–217, J1445–1457,
J2573–2578, J3378–3382).

| Input | Effective default | Parser / behavior |
| --- | --- | --- |
| AOI asset | empty | User-supplied FeatureCollection asset; normalized as R02 |
| Training asset | empty | User-supplied FeatureCollection asset; normalized as R02 |
| Class field | `lc_code` | Trimmed string; schema checked through preflight |
| Target year | `2024` | Finite numeric value in 2017–2024; original parser does not explicitly round this field |
| Annual count | `5` | Numeric 1–20, then `Math.round`; years descend from target |
| Fallback year | `2023` | Numeric 2017–2024, then `Math.round` |
| Training fraction | `0.7` | Numeric 0.01–0.99 |
| Trees | `500` | Numeric 1–5000, then `Math.round` |
| Threshold | `60` percent | Hidden widget; numeric 0–100 |
| Excluded class | `8` | Hidden widget; numeric -999–999, then `Math.round` |
| Bag fraction | `0.95` | Hidden widget; numeric 0.01–1 |
| Seeds | `42,123,256,389,512,645,778,891,999,1111,2222,3333,4444,5555` | Hidden widget; ordered comma-separated values converted with JS `Number`, nonfinite values filtered; no explicit integer rounding |
| Processing scale | `10` m | Wrapper forces 10; disabled widget |
| tileScale | `16` | Hidden widget; numeric 1–64, then `Math.round` |
| Download prefix | `landcover_automated` | Trim, replace characters outside `[A-Za-z0-9_-]` with underscores |
| Download rows / columns | `1 / 1` before AOI adjustment | Separate download validation; model parser temporarily substitutes 1 / 1 and restores text |

**R02 — Asset paths.** Trim surrounding whitespace and quotes/backticks, remove
the supported Code Editor `?asset=` URL prefix, attempt URI decoding, extract a
`projects/.../assets/...` or `users/...` path (including the legacy project form),
strip trailing whitespace/commas/semicolons, then validate the path form.
Do not restrict assets to the author's project or to Fezzan (J3000–3037).

**R03 — Classes.** Ordered codes are 1–12: Forest, Shrubland, Grassland,
Cultivated rainfed, Cultivated irrigated, Orchards, Bare soil/sand, Rocks,
Built up, Artificial water, Seasonal water, Sebkha. Palette order is
`002200,185e0a,74a56a,fffb00,FF8C00,43BE0A,bb6d3a,553a17,808080,00008B,15c0df,8B4513`
(J31–45). Exclusion from threshold scoring does not remove a class from training,
the output domain, or the displayed class table.

## 4. Preflight and data preparation — R04–R08

**R04 — Asset checks.** Evaluate AOI feature count and area, raw training feature
count and the class-field histogram before running seeds (J3662–3716). Reject
read/schema failures, AOI count <1 or area <=0, empty training, usable class total
<4 or no represented classes, fewer than two represented classes, or any
represented class with fewer than two usable features. Preserve the branch order
and useful error context. These are reference application checks.

**R05 — Label normalization.** On the histogram keys, apply
`Number(String(key).trim())`; retain finite integers present in the class domain.
Build a lookup keyed by the original histogram key, combine counts for equivalent
numeric classes, and count valid features. Filter null class properties, convert
each remaining property's string through the lookup (unknown → -999999), then
retain codes 1–12 (J3486–3514). Keep all usable training features nationally;
do not filter them to the AOI. The full normalized collection supplies the
training geometry (J3718–3720).

**R06 — Availability preflight.** For each selected year, count embedding images
intersecting the full training geometry and AOI geometry separately. Also query
fallback if not already in the annual list. For the target year each region needs
either target or fallback count >0; for other years each region needs that year's
count >0. A query error or missing required counts aborts before seeds
(J3722–3764). Counts are collection availability checks; do not describe them as
pixel-level completeness checks.

**R07 — Annual embedding images.** Collection is
`GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`, filtered from January 1 to the next January 1
and by the supplied geometry, then mosaicked. For target year only, apply
`primary.unmask(fallbackMosaic)` with the same arguments/default footprint
semantics as the reference (J3469–3484). Training/validation predictors use
`points.geometry().bounds(1)` for the **full normalized** points; AOI predictors
use `roi.geometry().bounds(1)` independently (J3565–3578). Do not replace these
with a union geometry or the current seed's training subset bounds.

**R08 — Terrain.** Use `USGS/SRTMGL1_003`. Individually apply `unmask(0)` to elevation,
`ee.Terrain.slope(dem)`, and `ee.Terrain.aspect(dem)`, then concatenate and rename
to `elevation`, `slope`, `aspect` in this order (J3766–3771). Concatenate embedding
bands before these three terrain bands. Use resulting training predictor band
names for sampling and classifier input properties.

## 5. Model execution — R09–R13

**R09 — Split.** Enumerate represented classes in sorted order. For each class,
use `randomColumn('_flex_random', seed)` then sort on that field. With class count
`N`, use `max(1, min(floor(N * trainFraction), N - 1))` training features. Slice the
ordered list into training then validation; flatten per-class collections
(J3518–3543). Preserve feature identities, ordering and random-column semantics
when porting. This count guarantee is before predictor sampling.

**R10 — Annual training and prediction.** For each descending year, sample national
predictors at training features with the class property, scale 10, configured
tileScale, and `geometries:false`. Filter samples with null predictor bands. Train
`smileRandomForest(numberOfTrees=trees, bagFraction=bag, seed=seed)` with the class
field and all predictor band names; leave all other RF options at the reference
library defaults. Store each classifier. Classify national predictors to `cYEAR`
for validation, and separately classify AOI predictors to `cYEAR` and clip to ROI
for annual output (J3565–3606).

**R11 — Temporal rules.** Apply the following ordered image operations separately
to annual AOI predictions and annual national predictions (J3545–3563,
J3608–3613):

1. Stack descending years as `yYEAR`; priority is the target-year band.
2. Start with `ee.Reducer.mode()` over the stack.
3. Where priority is 4 or 5, replace with priority.
4. Where class 5 occurs at least twice, replace with 5.
5. Where class 4 occurs at least twice, replace with 4.
6. Where both counts are at least two, replace with priority (without restricting
   priority to 4 or 5 in this last operation).
7. Rename `classification`; clip the final AOI result to ROI. Keep the national
   validation result unclipped to the mapping AOI.

Do not reorder replacements, change mask propagation, or introduce a new tie rule.

**R12 — Existing metrics and score.** Sample the national temporal map at the
validation features with the same scale/tileScale and `geometries:false`. Call
`errorMatrix(classField, 'classification', classValues)` with explicit 1–12 order.
Evaluate `accuracy()`, `kappa()`, `producersAccuracy()`, `array()`, and sampled
validation count (J3806–3823). Preserve the reference array normalization
(J3834–3839). Starting score is 100 and targetReached is true. For each class:
skip confusion rows whose sum is <=0, the configured excluded class, and
nonfinite converted producer values. Otherwise use producer *100, reduce the
minimum score, and mark targetReached false if below the configured threshold.
No scored classes makes this seed unusable (J3841–3862). This documents existing
computation, without evaluating or changing its scientific meaning.

**R13 — Seed search and selection.** Process seeds sequentially in configured order.
On the asynchronous metric-evaluation error or empty result, retain a readable
last error and advance. Also advance for no scored classes. Replace best only
when no best exists or the new score is **strictly greater**; ties keep the earlier
candidate. Stop when the current usable seed reaches threshold, delivering the
stored best; otherwise continue. On exhaustion deliver best if available, else
abort with the last error (J3779–3888). Store the selected candidate's already-built
map, yearly images and classifiers. The effective `materializeBestModel` performs
no tree-text conversion or second training pass (J1828–1839).

## 6. State, results and downloads — R14–R19

**R14 — Run lifecycle.** Ignore RUN while `APP.running` or cache preparation is
active. Handle configuration errors before entering running state. A new run
increments the run token and download generations, clears prior result objects,
map and panels, disables controls and resets downloads (J3625–3660).
Asynchronous preflight, coverage, and seed callbacks ignore stale run tokens.
`flexibleAbortRun` clears running state, restores RUN and disables downloads
(J3616–3623). The finish wrapper rejects a model whose settings key changed or
whose scale is not 10 (J1785–1797). The final RUN function has no catch-all around
every synchronous/server-graph construction call; do not claim universal recovery.
There is no explicit user-facing mapping-cancel button. Download pause is separate.

**R15 — Result objects and display.** Selected best contains `score`, `seed`, `map`,
`yearly`, `overall`, `kappa`, `prod`, `conf`, `val` (pre-sampling validation features)
and `classifiers` (J3864–3876). `finish` retains best, ROI and configuration in APP;
centers the map, adds hidden annual layers and visible final layer with the fixed
palette, legend and dynamic map symbols (J559–590 and finish wrappers).
`showResults` displays seed, overall *100 to two decimals and kappa to three;
per-class producer percentage, user percentage (`diagonal/columnTotal *100`, zero
if columnTotal=0), reference-row sample count, and Included/Excluded status based
on configured exclusion. It also shows charts and the ordered confusion matrix
(J444–557). Preserve raw numbers separately from UI formatting in a future adapter.
Class-area statistics and conversational explanations are future assistant features,
not existing GEE model outputs.

**R16 — Download settings and extent.** The final download action uses live selected
classification, not a required Drive task or prepared asset. Rows/columns must be
integers 1–1000 (J1423, J1529–1537). Defaults are initially 1/1 and are adjusted
after mapping using the actual AOI (J3400–3467). Choose UTM from AOI centroid;
longitude must be -180..180, latitude -80..84; zone is clamped 1..60, north uses
EPSG 32600+zone and south 32700+zone (J1538–1544). Get projected AOI bounds with
1 m tolerance. Snap bounds outward to 10 m edges with a 1 m guard; reject rows or
columns exceeding pixel dimensions (J1554–1583). Partition using integer floor
boundaries in row-major order (J1585–1593).

**R17 — Grid limits.** Final planner requires each cell side <=10000 pixels and
pixel count <=24*1024*1024; oversized manual layouts return suggested larger
rows/columns. Final automatic adjustment computes minimum safe rows/columns,
retains larger entered values subject to raster dimensions, and uses the
reference guarded loop (J2609–2643, J3387–3467). The grid has exactly rows*columns
candidate cells, **at most** one file per cell: empty cells are skipped. Hidden
subdivision is disabled (J2645–2672). Preserve these reference limits as code
constants, without inferring current service limits from them.

**R18 — Raster and URL.** Rename selected map `classification`, cast UInt8, mask
values outside 1–12 (J2805–2809). For each cell, intersect with AOI and check area
and valid mask pixel sum at scale 10 in grid CRS (`maxPixels` as above,
`bestEffort:false`, `tileScale:4`); skip area<=0 or validPixels<=0. Generate URL from
`classified.unmask(0,false)` with grid CRS, transform `[10,0,x0,0,-10,yTop]`, exact
width/height, `filePerBand:false`, format `ZIPPED_GEO_TIFF`. Names are cleaned
prefix (fallback `landcover`), target year, seed, grid shape, `R####_C####`, and
`10m` (J2864–2930). Zero is the filled outside/missing value; the call does not
set an explicit GeoTIFF nodata metadata option.

**R19 — Download lifecycle.** Pages contain 20 successful links, not 20 candidate
cells. Queue callbacks check the current token, map identity/settings and busy
state. Empty cells advance; check/download errors stop after two attempts, with
retry available for the current tile. The click handler can pause/continue link
generation, move to the next page, or regenerate links. Row/column/prefix changes
reset download state without retraining. Model-widget changes invalidate the map.
Final reset wrappers and final binding remain effective (J1430–1439,
J1751–1783, J2581–2604, J2811–2951, J3327–3360, J3897–3911).

## 7. Port boundary — R20

**R20 — Python and assistant boundary.** Python must preserve R01–R13 and expose
equivalent results from R15; run control from R14 becomes a service concern.
R16–R19 define the existing download behavior for later output-service work.
Do not require Python to recreate Earth Engine `ui` widgets, chart objects,
button labels, north arrow or scale-bar implementation. Their data and user-visible
capabilities can be represented by the assistant's own interface. A Python Drive
export helper is an additional delivery mechanism, not evidence of parity with
the GEE direct-download path. WP02 defines JSON contracts; WP03 changes Python;
WP04 checks executable parity; WP05–WP08 add persistence, outputs and chat tools.

## 8. Explicit runtime observations still needed

These are bounded follow-up checks, not open model-design decisions or reasons to
edit GEE. No Earth Engine assets were accessed and no RF jobs were run in WP01.

| ID | Observation for WP04 | Reference to preserve |
| --- | --- | --- |
| O01 | Capture normalized feature IDs, per-class ordered split IDs and sampled counts for the same inputs/seed | R05, R09, R10; preserve IDs and ordering during Python port |
| O02 | Capture returned metric array shapes and value coercions, selected seed, and output values/masks | R11–R13; compare implementations, not model quality |
| O03 | Observe a missing target-year collection with available fallback, and partial masked coverage | R06–R07; availability preflight and `mosaic().unmask(...)` are distinct operations |
| O04 | Compare clipping on the same multi-feature ROI, image grids and download transforms | R10–R11, R16–R18; Python currently uses `clipToCollection` |
| O05 | Exercise readable/unreadable assets, seed evaluation failure and delayed callbacks | R04, R13–R14; distinguish reference-handled cases from generic service error handling |
| O06 | Confirm non-empty tiles, retry/resume and paging using the fixed grid | R16–R19; delivery-stage check, not a prerequisite to documenting the model |

The source accepts some JS-coercible numeric inputs more broadly than Python type
annotations imply. WP02 must document any typed assistant input boundary explicitly;
it must not silently redefine the GEE model or pretend malformed-input behavior is
already identical. Source/parser details above remain the reference.

## 9. WP01 completion boundary

Deliverables are this specification and the linked Python checklist. Only those
two documentation files are added by WP01. GEE and Python code, tests, README,
and model settings remain unchanged. Publication verification checks the PR file
list and unchanged reference blobs/hashes. WP01 ends with an open PR; it does not
claim a merged release, a completed Python port, or runtime equivalence.
