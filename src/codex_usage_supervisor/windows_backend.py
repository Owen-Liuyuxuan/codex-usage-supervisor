"""Private newline-delimited JSON IPC. No listening port or third-party service."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict

from .config import Settings
from .service import collect_summary


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            method = request.get("method")
            if method == "settings/read":
                result = asdict(Settings.load())
            elif method == "settings/write":
                raw = request["settings"]
                settings = Settings(**{k: v for k, v in raw.items() if k in asdict(Settings())}).validated()
                settings.save()
                result = asdict(settings)
            elif method == "snapshot":
                result = collect_summary()
            else:
                raise ValueError("Unknown method")
            response = {"result": result}
        except Exception as error:
            response = {"error": str(error)}
        print(json.dumps(response, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
