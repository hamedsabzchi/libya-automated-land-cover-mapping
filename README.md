# Libya Automated Land-Cover Mapping

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22770165.svg)](https://doi.org/10.5281/zenodo.22770165)

A reproducible Google Earth Engine workflow for guided automated land-cover mapping in Libya, with the default area of interest set to Fezzan. The project combines annual Google Satellite Embedding features with SRTM terrain predictors, class-stratified hold-out validation, per-year Random Forest models, multi-seed model selection, and explicit multi-year temporal decision rules.

## Project status

This repository is an **independent personal technical portfolio and research-development project by Hamed Sabzchi Dehkharghani**. It is not published on behalf of any employer, organization, or institution. No institutional affiliation, sponsorship, approval, endorsement, or official status is claimed or implied.

The repository contains a streamlined reference Google Earth Engine JavaScript application, a Python Earth Engine implementation of the same modeling core, an interactive Colab notebook, citation metadata, credential-free static tests, and GitHub Actions continuous integration.

## Main data inputs

- **Annual satellite representation:** `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`
- **Terrain:** `USGS/SRTMGL1_003` elevation, plus slope and aspect derived with Earth Engine
- **AOI:** a user-supplied Earth Engine `FeatureCollection`
- **Training data:** a user-supplied point `FeatureCollection` with integer land-cover labels

The default AOI and training collections are personal Earth Engine assets. They are **external dependencies and are not bundled with this repository**. Users without access must provide replacement assets with the expected geometry and class field.

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

The JavaScript application displays the selected map and creates a single-band UInt8 GeoTIFF export task to Google Drive in `LandCover_Exports`. The Python engine includes a matching Drive-export helper. The output class domain is **1–12**.

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

## Google Colab

Open the notebook at:

`https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/02_landcover_colab.ipynb`

The notebook first performs a **public-data smoke test** over Libya using the 2024 Satellite Embedding collection, so Earth Engine initialization and public input availability can be checked without the personal AOI/training assets. Separate cells then test the default personal assets and optionally run one full candidate model.

## Scientific interpretation and limitations

This workflow is a supervised land-cover classification system, not a universally transferable land-cover product. Results depend on the supplied training points, label quality, spatial coverage, class balance, predictor availability, selected years, and model settings.

The reported accuracy is an **internal stratified random hold-out assessment from the same training asset, not independent external validation**. Spatially nearby training and validation points can make random-split accuracy optimistic. Publication-quality assessment should use independent probability-based validation samples or an appropriately designed spatial cross-validation strategy.

The training scope deliberately includes valid points outside the mapping AOI. This can improve sample support, but may also introduce geographic domain shift. The temporal post-processing deliberately favors cultivated classes 4 and 5 under documented conditions, so the final map should be interpreted as a supervised classification plus explicit temporal rules rather than a neutral modal composite.

## Reproducibility

The public repository reproduces the computational logic, but the default personal Earth Engine AOI and training assets are external dependencies. Full reproduction therefore requires access to those assets or equivalent replacements. Public dataset identifiers and scientific references are retained for data provenance and do not imply authorship, sponsorship, or endorsement by their providers.

## Author

Hamed Sabzchi Dehkharghani

## Independent personal-project notice

This repository is an independent personal technical portfolio and research-development project by Hamed Sabzchi Dehkharghani. It is not published on behalf of any employer, organization, or institution. No institutional affiliation, sponsorship, approval, endorsement, or official status is claimed or implied.

## Citation

Zenodo DOI: **10.5281/zenodo.22770165**

Software citation metadata are also provided in `CITATION.cff`.

## Licensing note

No open-source license is asserted by this repository at this stage. The repository is publicly viewable for technical portfolio, reproducibility, and citation purposes; no broader reuse permission is granted by an explicit software license here.
