# Request and result contracts

[Project home](../README.md) · [Developer guide](../docs/developer-guide.md)

These modules validate the data exchanged between the assistant and the Python mapping engine. They are developer components; ordinary Colab users do not need to edit them.

| Component | Purpose |
| --- | --- |
| [models.py](models.py) | Request, run-status and result validation, transitions and linked identifiers |
| [__init__.py](__init__.py) | Public `RunRequest`, `RunStatus`, `RunResult` and validation exports |
| [__main__.py](__main__.py) | Contract command-line entry |
| [examples/](examples/README.md) | Synthetic format examples, explicitly not model outputs |
| [Contract specification](../docs/assistant-contracts.md) | Fields, validation rules and execution boundaries |

The current request validation accepts target and fallback years from 2017 through 2025. The original specification records earlier development-stage limits; the current Python contract is authoritative for accepted inputs.

Example asset paths, IDs and accuracy values are fixtures. They must not be presented as real Libya map results. Validating a request does not authenticate with Earth Engine or start mapping.
