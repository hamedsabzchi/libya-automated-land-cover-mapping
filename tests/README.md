# Software checks

[Project home](../README.md) · [Developer guide](../docs/developer-guide.md)

These checks verify software behavior, serialization and interface flows. They do not replace live Colab/Earth Engine checks or assess scientific classification quality.

## Run the offline checks

From the repository root in an activated Python environment:

```sh
python -m pip install ".[map]" pytest
python -m unittest discover -s tests -p 'test_*.py' -v
python -m pytest -q tests/test_repository_structure.py
```

Node.js is also required for JavaScript reference and timer checks. CI uses Python 3.12 and Node.js 22 for engine/package checks. The map extra installs widgets and map dependencies; a language-model download or paid API key is not required for these tests.

## What is checked

| Area | Representative checks |
| --- | --- |
| Repository files and original reference | `test_repository_structure.py`, `test_contracts.py` |
| Engine control flow and offline Earth Engine graphs | `test_engine.py`, `test_ee_graphs.py`, `reference_client.cjs` |
| Runner, bundles, persistent jobs and sample exports | `test_runner.py`, `test_jobs.py`, `test_pilot.py` |
| Assistant requests and local chat parsing | `test_assistant.py`, `test_local_chat.py` |
| Saved accuracy and interpretation | `test_accuracy.py`, `test_accuracy_explanation.py`, `test_accuracy_upgrade.py` |
| Map display, downloads, viewport diagnostics and Colab callbacks | `test_map_workspace.py`, `test_display_diagnostics.py`, `test_colab_updates.py`, `test_widget_display.py` |
| Startup, upgrades, year controls and saved work | `test_complete_colab.py`, `test_startup_upgrade.py`, `test_notebook_logging.py`, `test_one_notebook.py`, `test_year_controls.py`, `test_workspace.py` |

## GitHub Actions

| Workflow | Scope |
| --- | --- |
| [Static tests](../.github/workflows/static-tests.yml) | Repository structure, notebook JSON and syntax |
| [Contract tests](../.github/workflows/contract-tests.yml) | Data contracts and examples |
| [Engine tests](../.github/workflows/engine-tests.yml) | Full offline suite with Earth Engine and map dependencies |
| [Package tests](../.github/workflows/package-tests.yml) | Wheel installation, installed commands and full offline suite |

Synthetic metrics and model graphs in fixtures are software-test data, not reported land-cover results. See the [recorded execution evidence](../docs/README.md#recorded-evidence) for the separately documented live cases.
