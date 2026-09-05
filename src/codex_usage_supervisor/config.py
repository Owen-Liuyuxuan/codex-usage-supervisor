"""Persistent application settings."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "codex-usage-supervisor" / "settings.json"


@dataclass(slots=True)
class Settings:
    daily_token_budget: int = 500_000
    daily_focus_minutes: int = 240
    refresh_seconds: int = 30
    notify_at_percent: int = 90
    codex_home: str = str(Path.home() / ".codex")

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or config_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return cls()
        values = {key: raw[key] for key in asdict(cls()) if key in raw}
        try:
            return cls(**values).validated()
        except (TypeError, ValueError):
            return cls()

    def validated(self) -> "Settings":
        self.daily_token_budget = max(1, int(self.daily_token_budget))
        self.daily_focus_minutes = max(1, int(self.daily_focus_minutes))
        self.refresh_seconds = min(3600, max(5, int(self.refresh_seconds)))
        self.notify_at_percent = min(100, max(1, int(self.notify_at_percent)))
        self.codex_home = str(Path(self.codex_home).expanduser())
        return self

    def save(self, path: Path | None = None) -> None:
        path = path or config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

