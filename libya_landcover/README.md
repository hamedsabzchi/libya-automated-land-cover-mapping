# Assistant application package

[Project home](../README.md) · [Developer guide](../docs/developer-guide.md) · [Complete Colab](../python/Libya_Land_Cover_Assistant.ipynb)

This is the installable `libya_landcover` package behind the Colab assistant. Users open the notebook; developers use this directory to locate application behavior. Dependencies and the `libya-landcover` command are defined in [pyproject.toml](../pyproject.toml).

## Component map

| Responsibility | Source files |
| --- | --- |
| Assistant requests and mapping actions | [assistant.py](assistant.py), [map_assistant.py](map_assistant.py) |
| Main map workspace and shared chat controls | [map_ui.py](map_ui.py), [chat_ui.py](chat_ui.py), [year_controls.py](year_controls.py) |
| English intent parsing and local language model | [chat_language.py](chat_language.py), [local_language.py](local_language.py) |
| Saved accuracy reports, explanations and chat panel | [accuracy.py](accuracy.py), [accuracy_explanation.py](accuracy_explanation.py), [accuracy_chat.py](accuracy_chat.py) |
| Earth Engine map view, tile grid and viewport handling | [map_view.py](map_view.py), [notebook_map.py](notebook_map.py) |
| Widget rendering, automatic Colab updates and diagnostics | [widget_display.py](widget_display.py), [colab_updates.py](colab_updates.py), [display_diagnostics.py](display_diagnostics.py) |
| Persistent job records, workers and saved graph bundles | [job_store.py](job_store.py), [jobs.py](jobs.py), [bundle.py](bundle.py) |
| Export submission, progress and download cards | [exports.py](exports.py), [downloads.py](downloads.py), [pilot.py](pilot.py) |
| Saved-work ZIP creation and restoration | [workspace.py](workspace.py) |
| CLI entry points | [cli.py](cli.py), [job_cli.py](job_cli.py), [__main__.py](__main__.py) |
| Execution observations and reference diagnostics | [evidence.py](evidence.py), [gee_observer.js](gee_observer.js) |
| Public exports and package version | [__init__.py](__init__.py) |

The modeling core is separately located in [python/landcover_engine.py](../python/landcover_engine.py), reached through [assistant_adapter.py](../python/assistant_adapter.py). The [contracts](../contracts/README.md) define request, status and result formats.

The current Colab uses local English chat without a paid API. `chat_language.py` also retains an earlier optional API parser for compatibility. Saved accuracy answers use checked result metadata; they do not initiate a new Earth Engine accuracy calculation.
