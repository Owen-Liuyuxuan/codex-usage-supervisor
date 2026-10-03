"""Fetch fresh ChatGPT account limits through the supported Codex app-server."""

from __future__ import annotations

import json
import os
import re
import queue
import threading
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
    override = os.environ.get("CODEX_EXECUTABLE")
    if override and Path(override).is_file():
        return Path(override)
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI/Codex/bin"
        native = sorted(root.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True)
        if native:
            return native[0]
    discovered = shutil.which("codex")
    if discovered:
        if os.name == "nt" and Path(discovered).suffix.lower() in {".cmd", ".bat", ".ps1"}:
            # npm wrappers are shell scripts; launch their packaged native binary directly.
            root = Path(discovered).parent / "node_modules/@openai"
            native = list(root.glob("codex*/**/codex.exe"))
            if native:
                return native[0]
            return None
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


def fetch_account_rate_limits(timeout: float = 8.0, codex_home: str | None = None) -> RateLimits:
    """Start a short-lived app-server and request a backend account snapshot."""
    executable = find_codex_executable()
    if executable is None:
        raise AccountLimitsError("Codex executable was not found")

    environment = os.environ.copy()
    if codex_home:
        environment["CODEX_HOME"] = codex_home
    try:
        process = subprocess.Popen(
            [str(executable), "app-server", "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1, env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except OSError as error:
        raise AccountLimitsError(f"Could not start Codex app-server: {error}") from error
    lines: queue.Queue[str | None] = queue.Queue()

    def read_lines() -> None:
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read_lines, daemon=True)
    reader.start()

    def send(value: dict[str, Any]) -> None:
        process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        process.stdin.flush()

    def response(request_id: int, deadline: float) -> dict[str, Any]:
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=max(0.001, deadline - time.monotonic()))
            except queue.Empty:
                break
            if line is None:
                raise AccountLimitsError("Codex app-server exited unexpectedly")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("id") == request_id:
                return message
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
                    "version": "0.4.1",
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
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        reader.join(timeout=2)
        process.stdin.close()
        process.stdout.close()
