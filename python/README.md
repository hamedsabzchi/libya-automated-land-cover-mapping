# Python notebooks and engine

[Project home](../README.md) · [User guide](../docs/user-guide.md) · [Developer guide](../docs/developer-guide.md)

## Recommended notebook

**[Open Libya Land-Cover Assistant in Colab](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/Libya_Land_Cover_Assistant.ipynb)**

| File | Purpose |
| --- | --- |
| [Libya_Land_Cover_Assistant.ipynb](Libya_Land_Cover_Assistant.ipynb) | Complete current workspace: map, legend, selected TIFF downloads, English chat, accuracy reports and saved work |
| [08_wp08_map_workspace.ipynb](08_wp08_map_workspace.ipynb) | Compatible entry containing the same current notebook; retained for existing links |

Use either current entry, not both. No earlier notebook or update helper is required.

## Earlier notebooks

The numbers below identify development stages, **not setup steps**. These files are retained for reproducibility and technical investigation.

| File | Development purpose |
| --- | --- |
| [02_landcover_colab.ipynb](02_landcover_colab.ipynb) | Earlier engine notebook and public-data smoke test |
| [03_wp04_tripoli_execution.ipynb](03_wp04_tripoli_execution.ipynb) | Tripoli execution bundle and Python/GEE observation workflow |
| [04_wp05_tripoli_export.ipynb](04_wp05_tripoli_export.ipynb) | Job-ledger and Drive-export workflow |
| [05_wp05_tripoli_tile_pilot.ipynb](05_wp05_tripoli_tile_pilot.ipynb) | Bounded sample TIFF, diagnostics and recovery |
| [06_wp06_landcover_assistant.ipynb](06_wp06_landcover_assistant.ipynb) | Earlier guided/API-based conversation interface; may use a paid API |
| [07_wp07_free_english_assistant.ipynb](07_wp07_free_english_assistant.ipynb) | Earlier local English chat with sample-only delivery |

See [development history](../docs/development-history.md) for the corresponding work packages and evidence.

## Source and support scripts

| File | Role |
| --- | --- |
| [landcover_engine.py](landcover_engine.py) | Python Earth Engine modeling core |
| [assistant_adapter.py](assistant_adapter.py) | Converts validated requests into engine configuration and linked results |
| [start_assistant.py](start_assistant.py) | Startup source embedded in the complete notebook; receives the notebook's pinned service commit |
| [01_test_gee_connection.py](01_test_gee_connection.py) | Earlier standalone Earth Engine connection check |
| [requirements.txt](requirements.txt) | Dependencies for the earlier standalone workflow |
| [__init__.py](__init__.py) | Package marker supporting engine/adapter imports |

## Compatibility helpers — maintainer use

| File | Original role |
| --- | --- |
| [update_workspace.py](update_workspace.py) | Update an existing workspace while preserving saved work |
| [update_accuracy.py](update_accuracy.py) | Compatibility entry for earlier assistant updates |
| [repair_map_display.py](repair_map_display.py) | Restore an existing map display |

These helper files remain available for older links. The complete notebook includes the updates; ordinary users do not need to copy or run helper cells.
