# Libya Automated Land-Cover Mapping

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22798666.svg)](https://doi.org/10.5281/zenodo.22798666)

A reproducible Google Earth Engine and Python workflow for guided automated land-cover mapping in Libya, developed around a Fezzan case study while accepting user-supplied AOI and training assets. The project combines annual Google Satellite Embedding features with SRTM terrain predictors, class-stratified hold-out validation, per-year Random Forest models, multi-seed model selection, and explicit multi-year temporal decision rules.

## Project status

This repository is an **independent personal technical portfolio and research-development project by Hamed Sabzchi Dehkharghani**. It is not published on behalf of any employer, organization, or institution. No institutional affiliation, sponsorship, approval, endorsement, or official status is claimed or implied.

The repository contains the complete reference Google Earth Engine JavaScript application, a Python Earth Engine implementation of the same modeling core, an interactive Colab notebook, citation metadata, credential-free static tests, and GitHub Actions continuous integration.

## Main data inputs

- **Annual satellite representation:** `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`
- **Terrain:** `USGS/SRTMGL1_003` elevation, plus slope and aspect derived with Earth Engine
- **AOI:** a user-supplied Earth Engine `FeatureCollection`
- **Training data:** a user-supplied point `FeatureCollection` with integer land-cover labels

For portability, the public GEE application intentionally starts with blank AOI and training-asset fields. Users paste accessible Earth Engine asset IDs at run time. The Python configuration retains author-specific example asset IDs as convenience defaults; those assets are **external dependencies and are not bundled with this repository**, so other users must provide equivalent replacements.

## Dataset availability and attribution

The public Earth Engine catalog currently lists `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` as a global **10 m**, **64-dimensional** annual embedding collection covering **2017 through 2024**. The dataset is licensed under **CC BY 4.0** and requires the attribution: **“The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind.”**

The terrain predictor `USGS/SRTMGL1_003` is the SRTM V3 elevation product at approximately **30 m**. Because the workflow combines 10 m embeddings with 30 m terrain predictors, the terrain variables do not contain native 10 m spatial detail even when classification/output scale is set to 10 m.

### References

- Brown, C. F., Kazmierski, M. R., Pasquarella, V. J., et al. (2025). *AlphaEarth Foundations: An embedding field model for accurate and efficient global mapping from sparse label data*. arXiv. DOI: `10.48550/arXiv.2507.22291`.
- Farr, T. G., Rosen, P. A., Caro, E., et al. (2007). *The Shuttle Radar Topography Mission*. *Reviews of Geophysics*, 45(2), RG2004. DOI: `10.1029/2005RG000183`.

## Land-cover classes

| Code | Class |
|---:|---|
| 1 | Forest |
| 2 | Shrubland |
| 3 | Grassland |
| 4 | Cultivated rainfed |
| 5 | Cultivated irrigated |
| 6 | Orchards |
| 7 | Bare soil/sand |
| 8 | Rocks |
| 9 | Built up |
| 10 | Artificial water |
| 11 | Seasonal water |
| 12 | Sebkha |

## Reference workflow

The default priority year is **2024**, with five annual maps (`2024, 2023, 2022, 2021, 2020`) and **2023** used to fill masked pixels in the priority-year embedding. The code validates year selections against the current public Satellite Embedding period of **2017–2024**.

All valid labeled training points are retained, including points outside the mapping AOI. Mapping, display, and output are clipped to the AOI. For each candidate random seed, points are split independently within each class using a default **70% training / 30% validation** split. A separate Random Forest is trained for every selected year using all Satellite Embedding axes plus elevation, slope, and aspect. Defaults are **500 trees**, **0.95 bag fraction**, and **10 m** processing/output scale.

The final temporal map is not a simple majority map. It starts with the per-pixel modal class, then applies explicit priority rules for classes **4 (cultivated rainfed)** and **5 (cultivated irrigated)**. The priority-year class is retained when it is 4 or 5; repeated occurrences of class 4 or class 5 across the annual stack also trigger cultivated-class rules, with the priority year resolving pixels where both occur repeatedly.

## Seed selection and accuracy reporting

The JavaScript application evaluates a fixed sequence of candidate seeds. For each valid seed it derives:

- overall accuracy;
- Cohen's kappa;
- producer accuracy by class;
- a 12 × 12 confusion matrix in the Earth Engine model object.

The selection score is the **minimum producer accuracy across included classes**. Class **8 (Rocks)** is excluded from the default 60% minimum-producer-accuracy stopping rule, while remaining a mapped class. The best candidate seen so far is retained, and evaluation can stop when the target is reached.

## Output

The final active JavaScript path retains the selected native classifier-backed map and generates direct GeoTIFF browser-download links. It supports fixed-10 m row/column grids, paged link generation, automatic skipping of empty/outside-AOI cells, and dynamic map symbols. The earlier tree-text materialization path is inactive. The Python engine retains the selected candidate objects and provides an optional Google Drive export helper; browser-download/UI mechanics are separate from the model port. The output class domain is **1–12**.

## Repository structure

```text
libya-automated-land-cover-mapping/
├── README.md
├── CITATION.cff
├── .gitignore
├── gee/
│   └── automated_land_cover_app.js
├── python/
│   ├── 01_test_gee_connection.py
│   ├── 02_landcover_colab.ipynb
│   ├── landcover_engine.py
│   └── requirements.txt
├── tests/
│   └── test_repository_structure.py
└── .github/
    └── workflows/
        └── static-tests.yml
```

## Python ↔ GEE synchronization

WP03 ports the final active GEE **modeling core** documented in [WP01](docs/gee-reference-spec.md): input normalization/preflight, separate national/AOI predictors, per-class sorted splits, terrain masks, existing temporal and selection rules, failed-candidate continuation and retained selected graphs. `python/assistant_adapter.py` connects this engine to the [WP02 contracts](docs/assistant-contracts.md) in `contracts/` and emits linked status/result objects with session-local map references.

See [Python engine integration](docs/python-engine-integration.md) for usage, compatibility notes and checks. Offline software tests include comparisons with extracted GEE client functions and serialization using the actual Earth Engine Python client. The [Tripoli live comparison](docs/wp04-tripoli-comparison.md) now matches all recorded observation groups; additional WP04 cases remain open. WP05 adds a separate job/export layer described below; the adapter itself does not implement jobs or change the GEE reference. WP06 adds a bounded conversational interface; direct-download services remain later work.

## Start here: map workspace (WP08)

[Open the map assistant in Colab](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/feat/wp08-map-workspace/python/08_wp08_map_workspace.ipynb).
Click **Start assistant** once. Follow **Connect → Prepare map → Explore & download** and the visible **Next step** instruction.
The normal workflow is in this one notebook; no previous ZIP or code edits are needed.

- Connect the Google account authorized for the configured Tripoli project/data.
- Choose a year, review it, and click **Create map**. Progress updates automatically.
- Explore the full study-area land-cover layer and its 12-class legend.
- Click a grid square, choose **Download selected tile**, review it, and click
  **Create tile download**. Open the resulting Google Drive link for the TIFF.
- **Ask the assistant** is optional English help for colours, next steps, status,
  preparing another year, and downloading the tile selected on the map.

Version 0.8.5 keeps the reference GEE, Python modeling engine and adapter unchanged.
Display requests use the retained final-map graph over the actual AOI; downloads
use selected 1024 × 1024 windows on the existing 10 m grid. Display tiles load on
demand: an accepted map request does not prove every location has rendered.
This is not a completed whole-region TIFF delivery or an automatic full-grid export.

No paid chat API, external app server or Colab Pro subscription is required by the
notebook. Free Colab resources are limited; Earth Engine access and project quotas
still apply. The local chat model can misunderstand requests; buttons remain
available if chat cannot load. **Save work for later** downloads a recovery ZIP,
not the TIFF. See [WP08 usage, boundaries and acceptance](docs/wp08-map-workspace.md).

The [WP07 notebook](python/07_wp07_free_english_assistant.ipynb) and
[WP07 notes](docs/wp07-free-colab-chat.md) remain available for the earlier sample-only interface.

## Earlier API-based conversational assistant (WP06)

Version 0.6 adds a private Colab/Jupyter chat interface over the existing mapping,
job and pilot-export services. Review a request before confirming execution, ask
for recorded status/results, or import an existing pilot ZIP without rerunning the
model. Free Persian/English text uses an optional OpenAI API key; a clearly labeled
guided-command mode works without one. Replies use actual records, and distinguish
saved model graphs, a successful pilot window, and full-region delivery.

Start with the [WP06 notebook](python/06_wp06_landcover_assistant.ipynb) and
[usage, execution boundaries and limitations](docs/wp06-conversational-assistant.md).
The reference GEE code and Python modeling engine remain unchanged. This MVP does
not yet compute class-area/change analyses or deliver a complete tiled region.

## Installable assistant runner (WP04)

The Python engine now has an installable command-line runner, local result/graph
bundles, and a separate diagnostic harness for comparing actual Python and GEE
observations. See [WP04 installation and execution](docs/wp04-execution.md).
The GEE reference and WP03 engine are unchanged. The supplied Tripoli Python/GEE
records match for their settings, selected result, split IDs and 26 raster probes;
this does not prove full-raster equality. Saved graphs are not GeoTIFF exports.

## Persistent jobs and GeoTIFF exports (WP05)

Version 0.5 adds a local job ledger, a mapping worker, and separate Earth Engine
Drive export jobs. A completed WP04 bundle can be imported and its selected maps
exported without repeating seed search. Export submission, polling, cancellation
and recovery are explicit operations suitable for a later chatbot tool layer.
The GEE reference, Python modeling engine and adapter are unchanged.

See [WP05 commands, recovery and acceptance](docs/wp05-jobs-exports.md) and
[Tripoli export notebook](python/04_wp05_tripoli_export.ipynb).
This is a single-owner Python/CLI service foundation; it does not deploy a chatbot
or HTTP server. Automated checks are offline. A successful authenticated Tripoli
export and inspection of the downloaded GeoTIFF remain live acceptance steps.

### Bounded tile pilot (WP05B)

The owner-run full-area export reached a second server attempt after more than
ten hours. Version 0.5.1 adds one independently tracked, at-most 1024 × 1024 pixel
pilot export on the same 10 m grid, plus progress/attempt metadata and portable
recovery from WP05/pilot backups. It preserves the original operation and selected
model. See [pilot instructions and continuity record](docs/wp05-tile-pilot.md)
and [the pilot notebook](python/05_wp05_tripoli_tile_pilot.ipynb).
The [first live pilot TIFF passed delivery inspection](docs/wp05-pilot-live-inspection.md)
in attempt 1 after 3 minutes 42 seconds. This establishes one aligned, nonempty
tile export; it does not establish full-grid coverage or whole-AOI performance.
No full tiling campaign has been launched.

## Google Colab

Open the notebook at:

`https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/02_landcover_colab.ipynb`

The notebook first performs a **public-data smoke test** over Libya using the 2024 Satellite Embedding collection, so Earth Engine initialization and public input availability can be checked without the personal AOI/training assets. Separate cells then test the default personal assets and optionally run one full candidate model.

## Scientific interpretation and limitations

This workflow is a supervised land-cover classification system, not a universally transferable land-cover product. Results depend on the supplied training points, label quality, spatial coverage, class balance, predictor availability, selected years, and model settings.

The reported accuracy is an **internal stratified random hold-out assessment from the same training asset, not independent external validation**. Spatially nearby training and validation points can make random-split accuracy optimistic. Publication-quality assessment should use independent probability-based validation samples or an appropriately designed spatial cross-validation strategy.

The training scope deliberately includes valid points outside the mapping AOI. This can improve sample support, but may also introduce geographic domain shift. The temporal post-processing deliberately favors cultivated classes 4 and 5 under documented conditions, so the final map should be interpreted as a supervised classification plus explicit temporal rules rather than a neutral modal composite.

## Reproducibility

The public repository reproduces the computational logic. The GEE app accepts user-supplied AOI/training asset IDs, while the Python configuration includes author-specific example defaults; the underlying AOI/training assets remain external dependencies. Full reproduction therefore requires accessible equivalent assets. Public dataset identifiers and scientific references are retained for data provenance and do not imply authorship, sponsorship, or endorsement by their providers.

## Author

Hamed Sabzchi Dehkharghani

## Independent personal-project notice

This repository is an independent personal technical portfolio and research-development project by Hamed Sabzchi Dehkharghani. It is not published on behalf of any employer, organization, or institution. No institutional affiliation, sponsorship, approval, endorsement, or official status is claimed or implied.

## Citation

Software citation metadata are provided in `CITATION.cff`.

**Zenodo DOI for v1.0.3:** `10.5281/zenodo.22798666`

## Licensing note

No open-source license is asserted by this repository at this stage. The repository is publicly viewable for technical portfolio, reproducibility, and citation purposes; no broader reuse permission is granted by an explicit software license here.

