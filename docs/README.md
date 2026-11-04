# Documentation directory

[Project home](../README.md) · [Open the complete assistant](https://colab.research.google.com/github/hamedsabzchi/libya-automated-land-cover-mapping/blob/main/python/Libya_Land_Cover_Assistant.ipynb)

## Start with your goal

| Goal | Guide |
| --- | --- |
| Use the map, chat and TIFF downloads | [User guide](user-guide.md) |
| Find a notebook or script | [Python directory](../python/README.md) |
| Install or extend the code | [Developer guide](developer-guide.md) |
| Understand data, classes and model behavior | [Model and data reference](model-reference.md) |
| Understand how the project developed | [Development history](development-history.md) |
| Diagnose the current assistant or inspect releases | [Map workspace technical notes](wp08-map-workspace.md) |

## Technical references

| Topic | Document |
| --- | --- |
| Original GEE behavior | [GEE reference specification](gee-reference-spec.md) |
| Python request, status and result formats | [Assistant contracts](assistant-contracts.md) |
| Python engine and adapter | [Engine integration](python-engine-integration.md) |
| Reference-port tracking | [Parity checklist](python-parity-checklist.md) |
| CLI, result bundles and execution diagnostics | [Runner notes — WP04](wp04-execution.md) |
| Job ledger and Drive exports | [Jobs and exports — WP05](wp05-jobs-exports.md) |
| Bounded sample exports and recovery | [Tile pilot — WP05B](wp05-tile-pilot.md) |
| Earlier API-based chat | [Conversational assistant — WP06](wp06-conversational-assistant.md) |
| Earlier free local English chat | [Free Colab chat — WP07](wp07-free-colab-chat.md) |
| Current map workspace and release changes | [Map workspace — WP08](wp08-map-workspace.md) |

WP means **work package**. Earlier documents preserve the instructions, versions and acceptance status at that stage. In particular, old branch-installation instructions are historical: current installation starts from `main` as described in the [developer guide](developer-guide.md).

## Recorded evidence

| Record | Readable report | Structured data |
| --- | --- | --- |
| Tripoli Python/GEE observations | [Comparison](wp04-tripoli-comparison.md) | [JSON](wp04-tripoli-comparison.json) |
| Initial Tripoli Python execution review | [Run review](wp04-tripoli-run-review.md) | Referenced artifacts in the report |
| First bounded TIFF inspection | [Pilot inspection](wp05-pilot-live-inspection.md) | [JSON](wp05-pilot-live-inspection.json) |
| Earlier local-model smoke check | [WP07 context](wp07-free-colab-chat.md) | [JSON](wp07-local-model-smoke.json) |

These records have defined cases and scopes. A successful sample export or a set of matching probes does not establish whole-region delivery or accuracy for every map. Synthetic contract examples are separately identified in [contracts/examples](../contracts/examples/README.md).
