from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from codex_usage_supervisor.config import Settings
from codex_usage_supervisor.metrics import collect_metrics


class MetricsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        session_dir = self.root / "sessions" / "2026" / "09" / "05"
        session_dir.mkdir(parents=True)
        (self.root / "session_index.jsonl").write_text(
            json.dumps({"id": "test-id", "thread_name": "Build the monitor"}) + "\n",
            encoding="utf-8",
        )
        records = [
            self.record("2026-09-05T01:00:00Z", "session_meta", {"id": "test-id", "cwd": "/work/demo"}),
            self.record("2026-09-05T01:01:00Z", "turn_context", {"turn_id": "one", "model": "gpt-test"}),
            self.record("2026-09-05T01:04:00Z", "event_msg", self.tokens(1_200)),
            self.record("2026-09-05T01:40:00Z", "turn_context", {"turn_id": "two", "model": "gpt-test"}),
            self.record("2026-09-05T01:42:00Z", "event_msg", self.tokens(3_000, with_limits=True)),
        ]
        (session_dir / "rollout-test-id.jsonl").write_text(
            "\n".join(json.dumps(item) for item in records) + "\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def record(stamp: str, kind: str, payload: dict) -> dict:
        return {"timestamp": stamp, "type": kind, "payload": payload}

    @staticmethod
    def tokens(total: int, with_limits: bool = False) -> dict:
        value = {"type": "token_count", "info": {"total_token_usage": {
            "input_tokens": total - 100, "output_tokens": 100, "total_tokens": total,
        }}}
        if with_limits:
            value["rate_limits"] = {
                "plan_type": "test",
                "primary": {"used_percent": 42.0, "window_minutes": 300, "resets_at": 1788590000},
                "secondary": {"used_percent": 8.0, "window_minutes": 10080, "resets_at": 1789000000},
            }
        return value

    def test_collects_latest_cumulative_counter_without_double_counting(self) -> None:
        result = collect_metrics(self.root, datetime.fromisoformat("2026-09-05T12:00:00+00:00"))
        self.assertEqual(result.today_tokens, 3_000)
        self.assertEqual(result.week_tokens, 3_000)
        self.assertEqual(result.today_sessions, 1)
        self.assertEqual(result.sessions[0].name, "Build the monitor")
        self.assertEqual(result.sessions[0].turns, 2)
        self.assertEqual(result.sessions[0].model, "gpt-test")
        self.assertEqual(result.sessions[0].today_minutes, 22)
        self.assertIsNotNone(result.rate_limits)
        self.assertEqual(result.rate_limits.primary.used_percent, 42.0)

    def test_settings_validation_and_round_trip(self) -> None:
        path = self.root / "settings.json"
        Settings(10, 20, 1, 150, "~/custom-codex").validated().save(path)
        loaded = Settings.load(path)
        self.assertEqual(loaded.refresh_seconds, 5)
        self.assertEqual(loaded.notify_at_percent, 100)
        self.assertTrue(loaded.codex_home.endswith("custom-codex"))


if __name__ == "__main__":
    unittest.main()
