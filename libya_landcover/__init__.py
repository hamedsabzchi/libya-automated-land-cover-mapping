"""Public assistant API. Importing this package never initializes Earth Engine."""

from python.assistant_adapter import request_from_inputs, run_request
from contracts import RunRequest, RunResult, RunStatus

__version__ = "0.8.1"
__all__ = ["request_from_inputs", "run_request", "RunRequest", "RunResult", "RunStatus"]

