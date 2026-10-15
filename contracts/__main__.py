"""Validate contract examples without Earth Engine, credentials or dependencies."""

import argparse
from pathlib import Path
import sys

from .models import ContractError, RunRequest, RunResult, RunStatus, validate_exchange


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("request", "status", "result", "exchange"))
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        if args.kind == "exchange":
            if len(args.files) != 3:
                parser.error("exchange requires request.json status.json result.json")
            request, status, result = [cls.from_json(path.read_text(encoding="utf-8"))
                                      for cls, path in zip((RunRequest, RunStatus, RunResult), args.files)]
            validate_exchange(request, status, result)
            print("Valid request/status/result exchange")
        else:
            cls = {"request": RunRequest, "status": RunStatus, "result": RunResult}[args.kind]
            for path in args.files:
                payload = cls.from_json(path.read_text(encoding="utf-8"))
                print(f"Valid {args.kind}: {path}")
                if isinstance(payload, RunRequest):
                    print(f"Resolved request fingerprint: {payload.fingerprint()}")
        return 0
    except (ContractError, OSError) as exc:
        print(f"Invalid contract: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
