"""Persistent network snapshots must remain usable across offline restarts."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from codex_usage_supervisor.metrics import RateLimits, RateWindow
from codex_usage_supervisor.network_cache import (
    limits_dict,
    load_network_limits,
    network_cache_path,
    save_network_limits,
)


class NetworkCacheTests(unittest.TestCase):
    def test_round_trip_retains_both_windows_and_timezone(self):
        now = datetime(2026, 10, 3, 12, tzinfo=timezone(timedelta(hours=9)))
        limits = RateLimits("plus", RateWindow(42.5, 300, now), RateWindow(70, 10080, None), now)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "network.json"
            save_network_limits(path, limits)
            self.assertEqual(load_network_limits(path), limits)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_missing_corrupt_or_invalid_cache_is_ignored(self):
        now = datetime.now(timezone.utc)
        record = {"schema_version": 1, "rate_limits": limits_dict(
            RateLimits("plus", RateWindow(42, 300, None), None, now)
        )}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            self.assertIsNone(load_network_limits(path))
            bad_records = ["{", "[]", "null", json.dumps({"schema_version": 2})]
            for field, value in [("observed_at", "2026-10-03"), ("primary", []), ("primary", None)]:
                modified = json.loads(json.dumps(record))
                modified["rate_limits"][field] = value
                bad_records.append(json.dumps(modified))
            for invalid in bad_records:
                with self.subTest(record=invalid):
                    path.write_text(invalid, encoding="utf-8")
                    self.assertIsNone(load_network_limits(path))

    def test_profiles_have_separate_paths_in_platform_cache_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XDG_CACHE_HOME": directory, "LOCALAPPDATA": directory}):
                first = network_cache_path(str(Path(directory) / "profile-a"))
                second = network_cache_path(str(Path(directory) / "profile-b"))
                self.assertNotEqual(first, second)
                self.assertEqual(first.parent, Path(directory) / "codex-usage-supervisor")

    def test_failed_replace_keeps_previous_snapshot_and_cleans_temporary_file(self):
        now = datetime.now(timezone.utc)
        old = RateLimits("plus", RateWindow(80, 300, None), None, now)
        new = RateLimits("plus", RateWindow(5, 300, None), None, now + timedelta(minutes=1))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.json"
            save_network_limits(path, old)
            with patch.object(Path, "replace", side_effect=OSError("read-only")):
                with self.assertRaises(OSError):
                    save_network_limits(path, new)
            self.assertEqual(load_network_limits(path), old)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
