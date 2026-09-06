"""Fetch fresh ChatGPT account limits through the supported Codex app-server."""

from __future__ import annotations

import json
import os
import re
import selectors
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .metrics import RateLimits, RateWindow


class AccountLimitsError(RuntimeError):
    """Raised when a fresh account snapshot cannot be obtained."""


def find_codex_executable() -> Path | None:
    """Find Codex in PATH or common per-user Node installation locations."""
    discovered = shutil.which("codex")
    if discovered:
        return Path(discovered)

    candidates = [
        Path.home() / ".local/bin/codex",
        Path("/usr/local/bin/codex"),
        Path("/usr/bin/codex"),
    ]
    nvm_root = Path.home() / ".nvm/versions/node"
    nvm_candidates = list(nvm_root.glob("*/bin/codex"))
    nvm_candidates.sort(
        key=lambda path: tuple(
            int(part) for part in re.findall(r"\d+", path.parents[1].name)
        ),
        reverse=True,
    )
    candidates.extend(nvm_candidates)
    return next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def _window(value: Any) -> RateWindow | None:
    if not isinstance(value, dict) or not isinstance(value.get("usedPercent"), (int, float)):
        return None
    reset = value.get("resetsAt")
    return RateWindow(
        used_percent=float(value["usedPercent"]),
        window_minutes=int(value.get("windowDurationMins", 0) or 0),
        resets_at=datetime.fromtimestamp(reset).astimezone() if isinstance(reset, (int, float)) else None,
    )


def parse_rate_limits_response(message: dict[str, Any]) -> RateLimits:
    """Reduce an app-server response to the fields used by the desktop UI."""
    error = message.get("error")
    if error:
        detail = error.get("message", "unknown app-server error") if isinstance(error, dict) else str(error)
        raise AccountLimitsError(detail)

    result = message.get("result")
    if not isinstance(result, dict):
        raise AccountLimitsError("app-server returned no result")
    by_id = result.get("rateLimitsByLimitId")
    value = by_id.get("codex") if isinstance(by_id, dict) else None
    if not isinstance(value, dict):
        value = result.get("rateLimits")
    if not isinstance(value, dict):
        raise AccountLimitsError("app-server returned no Codex rate limits")

    primary = _window(value.get("primary"))
    secondary = _window(value.get("secondary"))
    if primary is None and secondary is None:
        raise AccountLimitsError("account rate-limit windows are unavailable")
    return RateLimits(
        plan_type=str(value.get("planType") or "unknown"),
        primary=primary,
        secondary=secondary,
        observed_at=datetime.now().astimezone(),
    )


def fetch_account_rate_limits(timeout: float = 8.0) -> RateLimits:
    """Start a short-lived app-server and request a backend account snapshot."""
    executable = find_codex_executable()
    if executable is None:
        raise AccountLimitsError("Codex executable was not found")

    process = subprocess.Popen(
        [str(executable), "app-server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise AccountLimitsError("could not open Codex app-server pipes")

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)

    def send(value: dict[str, Any]) -> None:
        process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def response(request_id: int, deadline: float) -> dict[str, Any]:
        while time.monotonic() < deadline:
            for key, _event in selector.select(timeout=0.25):
                line = key.fileobj.readline()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if message.get("id") == request_id:
                    return message
            if process.poll() is not None:
                raise AccountLimitsError("Codex app-server exited unexpectedly")
        raise AccountLimitsError("Codex account refresh timed out")

    deadline = time.monotonic() + timeout
    try:
        send({
            "method": "initialize",
            "id": 1,
            "params": {
                "clientInfo": {
                    "name": "codex-usage-supervisor",
                    "title": "Codex Usage Supervisor",
                    "version": "0.3.0",
                }
            },
        })
        initialized = response(1, deadline)
        if initialized.get("error"):
            raise AccountLimitsError("Codex app-server initialization failed")
        send({"method": "initialized", "params": {}})
        send({"method": "account/rateLimits/read", "id": 2})
        return parse_rate_limits_response(response(2, deadline))
    except (BrokenPipeError, OSError) as error:
        raise AccountLimitsError(f"Codex app-server communication failed: {error}") from error
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
