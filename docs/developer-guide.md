# Developer guide

[Project home](../README.md) · [Documentation index](README.md) · [Package directory](../libya_landcover/README.md)

Most users only need the [complete Colab](../python/Libya_Land_Cover_Assistant.ipynb). This guide is for developers working with the source on `main`.

## How the components fit together

The notebook opens the map interface and English assistant in `libya_landcover`. Validated requests go through `contracts` into the job layer. The worker uses `python/assistant_adapter.py` and `python/landcover_engine.py` to build the Earth Engine computation. Map display and TIFF export consume the saved map graphs. Accuracy answers read saved result metadata.

The original reference is [gee/automated_land_cover_app.js](../gee/automated_land_cover_app.js). The separate root [Streamlit prototype](../app.py) has its own entry point and requirements; it is not the complete Colab UI.

## Install from main

Use Python 3.10 or newer; CI uses Python 3.12. In a new environment:

```sh
git clone https://github.com/hamedsabzchi/libya-automated-land-cover-mapping.git
cd libya-automated-land-cover-mapping
git checkout main
python -m venv .venv
# Activate .venv using the command for your operating system.
python -m pip install ".[map]"
libya-landcover --version
libya-landcover --help
```

| Dependency source | Use |
| --- | --- |
| [pyproject.toml](../pyproject.toml), base package (`pip install .`) | Engine runner and command-line tools |
| `.[map]` | Widget/map interface and offline interface tests |
| `.[map-chat]` | Map interface plus local language-model dependencies; the complete Colab installs this automatically |
| [python/requirements.txt](../python/requirements.txt) | Earlier standalone notebook environment |
| [requirements.txt](../requirements.txt) at the repository root | Separate Streamlit prototype |
| [tests/requirements.txt](../tests/requirements.txt) | Pinned Earth Engine client for offline graph tests |

Use the package extras for the current assistant. The root Streamlit requirements are not its installation instructions. Loading local chat weights is separate from installing the dependencies. No paid inference service is required by the current Colab.

## Requests and execution

The [contract examples](../contracts/examples/README.md) are synthetic fixtures. They illustrate format, not real assets or model results. This command validates an example locally without starting mapping:

```sh
libya-landcover validate contracts/examples/request.json
```

For live execution, configure an authorized Earth Engine project, AOI and training assets. Public source access does not provide those permissions. See [request contracts](assistant-contracts.md), [runner commands](wp04-execution.md) and [job/export commands](wp05-jobs-exports.md); use your current checkout rather than the historical branches in earlier notes.

## Preserve working behavior

- Keep the original GEE reference intact. Record any explicitly requested Python input-range extension separately from changes to classification logic.
- Keep notebook paths and older compatible entries available; external links and saved workflows may use them.
- Keep the complete notebook and its `08_wp08_map_workspace.ipynb` compatible entry synchronized. Their embedded starter comes from `python/start_assistant.py`.
- Notebook service commits are intentionally pinned. A documentation-only update does not require changing the working notebook's service pin.
- Preserve saved job IDs, result provenance and export records. A saved graph bundle or ZIP is not a raster download.
- Treat chat as a request/review interface. Do not let a conversation silently start a new map or export.

The currently supported Python target and fallback years are 2017–2025; the unchanged GEE reference retains its 2017–2024 ceiling. The existing coverage preflight and temporal fallback rules still apply.

## Verification

See the [test guide](../tests/README.md). Offline software checks cover contracts, engine behavior, graph serialization, UI flows, saved work and downloads. They do not by themselves establish live browser rendering, Earth Engine access, map quality or whole-region export success.
