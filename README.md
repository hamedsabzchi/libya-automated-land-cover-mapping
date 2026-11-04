# Libya Automated Land-Cover Mapping

Create and explore land-cover maps, download selected areas as GeoTIFFs, and ask an English assistant about your results. The project includes a Google Colab workspace, a Python mapping engine, and the original Google Earth Engine (GEE) reference application.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/Libya_Land_Cover_Assistant.ipynb)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22798666.svg)](https://doi.org/10.5281/zenodo.22798666)

## Start here — use the assistant

**[Open the complete Libya Land-Cover Assistant](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/Libya_Land_Cover_Assistant.ipynb)**

Everything opens in this one notebook. No code edits, separate update cells, paid chat API or external app server are required.

1. Click **Start assistant**, then **Connect Google** with an account authorized for the configured Earth Engine project and data.
2. Choose **Target year** and **Fallback year** (2017–2025), then click **Create map** once.
3. Explore the map and legend. Select a blue grid square and click **Create tile download** once. Its progress and Google Drive link appear automatically in **Downloads**.
4. Use **Save work for later** before leaving. Next time, restore that ZIP under **Continue saved work**.

The default workspace is **Tripoli, Libya**. Public GitHub access does not grant access to the configured Earth Engine assets. A new user needs access arranged by the project owner. Free Colab resources and Earth Engine quotas still apply; keep the notebook connected while working.

**[User guide](docs/user-guide.md)** · **[Choose a component](#choose-the-right-component)** · **[All documentation](docs/README.md)** · **[Developer guide](docs/developer-guide.md)**

## What the current assistant does

| Feature | What you receive |
| --- | --- |
| Study-area map | Interactive land-cover layer, boundary and 12-class legend; colours load as you explore |
| Selected-area download | A selected 1024 × 1024 tile at 10 m resolution, exported as TIFF to Google Drive |
| English assistant | Help with colours, progress, selected downloads and preparing another year |
| Model accuracy | Saved validation tables, confusion matrix and explanations; no new Earth Engine calculation to read them |
| Save and resume | One ZIP with saved maps, download records and recovery information; raster pixels remain in Drive |

The assistant currently does **not** calculate class areas or change statistics, or automatically download the entire study area. A completed map-preparation job does not mean every display tile has rendered. An unfinished Python mapping process cannot be restored after Colab deletes its runtime.

## Choose the right component

| Your goal | Start with | Role |
| --- | --- | --- |
| Use the map and assistant | [Complete Colab](python/Libya_Land_Cover_Assistant.ipynb) | Recommended user entry point, version 0.12.1 |
| Understand the workflow | [User guide](docs/user-guide.md) | Buttons, chat, downloads and saved work |
| Work directly with the original GEE app | [GEE directory](gee/README.md) | Original JavaScript reference; unchanged |
| Develop or integrate the assistant | [Python package](libya_landcover/README.md) | Interface, chat, jobs, exports and reports |
| Inspect the mapping implementation | [Python directory](python/README.md) | Engine, adapter and notebook inventory |
| Understand request/result formats | [Contracts](contracts/README.md) | Validated requests, statuses and results |
| Inspect examples and recorded evidence | [Examples](examples/README.md) | Configurations and links to execution records |
| Run software checks | [Tests](tests/README.md) | Offline verification and CI |
| Find earlier development versions | [Notebook directory](python/README.md#earlier-notebooks) and [development history](docs/development-history.md) | Retained for reference; not additional setup steps |
| Use or deploy the separate website | [Website guide](docs/website.md), [app.py](app.py) and [requirements.txt](requirements.txt) | Google sign-in, each visitor's Earth Engine project, map and accuracy report |

The separate Streamlit website uses each visitor's Google authorization, Cloud project and accessible assets. Its owner must configure Google OAuth for the deployed address first; see the [website setup guide](docs/website.md). It calls the existing reference engine, but is not the complete Colab assistant: chat, TIFF tile export and saved-work ZIP recovery remain in Colab. Website tests are offline; live Google sign-in and rendering still require deployment verification.

## Repository guide

| Location | Contents |
| --- | --- |
| [python/](python/README.md) | Complete Colab, compatible notebook entry, mapping engine, adapter and earlier notebooks |
| [libya_landcover/](libya_landcover/README.md) | Installable assistant application and command-line tools |
| [website/](website/README.md) | Separate Streamlit interface and per-user Earth Engine workers |
| [gee/](gee/README.md) | Original Earth Engine reference code |
| [contracts/](contracts/README.md) | Data contracts and synthetic examples |
| [docs/](docs/README.md) | User/developer guides, model reference, technical notes and development records |
| [examples/](examples/README.md) | Tripoli case configuration and export specification |
| [tests/](tests/README.md) and [.github/workflows/](.github/workflows/) | Software checks and GitHub Actions |
| [pyproject.toml](pyproject.toml) | Assistant package version and dependencies |
| [CITATION.cff](CITATION.cff) | Software citation metadata |

Existing source files and notebooks keep their paths so previous links and saved workflows remain usable.

## Model and interpretation

The workflow uses annual Google Satellite Embeddings and SRTM terrain predictors with Random Forest classification and temporal decision rules. The original GEE reference accepts 2017–2024; the Python assistant extends input selection through 2025 while retaining the coverage and fallback checks.

Accuracy reports describe an **internal stratified random hold-out assessment, not independent external validation**. They are saved model results, not a separate accuracy assessment of the selected download tile.

The full [model and data reference](docs/model-reference.md) preserves the class list, modeling settings, seed-selection logic, scientific references, interpretation limitations and reproducibility details.

Attribution: **“The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind.”**

## Author, citation and use

**Hamed Sabzchi Dehkharghani**

This is an **independent personal technical portfolio and research-development project**. It is not published on behalf of any employer, organization or institution; no institutional affiliation, sponsorship, approval or endorsement is claimed.

See [CITATION.cff](CITATION.cff) for citation metadata. The recorded Zenodo DOI for **v1.0.3** is [10.5281/zenodo.22798666](https://doi.org/10.5281/zenodo.22798666); that citation version is distinct from the assistant package version.

**No open-source license is asserted by this repository.** Public visibility does not itself grant broader reuse permission. The existing [licensing notice](docs/model-reference.md#licensing-note) is retained.
