from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from codex_usage_supervisor.account import AccountLimitsError
from codex_usage_supervisor.config import Settings
from codex_usage_supervisor.network_cache import load_network_limits, save_network_limits
from codex_usage_supervisor.metrics import (
    DashboardMetrics,
    RateLimits,
    RateWindow,
    SessionMetric,
    TokenUsage,
)
from codex_usage_supervisor.service import collect_summary, metrics_summary


class ServiceContractTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache_path = Path(directory.name) / "network.json"
        patcher = patch("codex_usage_supervisor.service.network_cache_path", return_value=self.cache_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_summary_contract_contains_only_desktop_fields(self) -> None:
        now = datetime.now().astimezone()
        metric = SessionMetric(
            session_id="id",
            name="Example task",
            cwd="/work/planner",
            model="gpt-test",
            updated_at=now,
            turns=3,
            usage=TokenUsage(total_tokens=1_234),
        )
        result = metrics_summary(DashboardMetrics(
            sessions=[metric],
            today_tokens=1_234,
            week_tokens=4_321,
            today_minutes=25,
            today_sessions=1,
            generated_at=now,
        ))
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["recent"][0]["project"], "planner")
        self.assertEqual(result["today"]["focus_minutes"], 25)
        self.assertEqual(result["rate_limits_source"], "local-session")
        self.assertNotIn("content", str(result).lower())

    def test_account_limits_override_local_snapshot(self) -> None:
        now = datetime.now().astimezone()
        local = RateLimits(
            plan_type="plus",
            primary=RateWindow(used_percent=10, window_minutes=300, resets_at=None),
            secondary=None,
            observed_at=now,
        )
        account = RateLimits(
            plan_type="plus",
            primary=RateWindow(used_percent=80, window_minutes=300, resets_at=None),
            secondary=None,
            observed_at=now,
        )
        metrics = DashboardMetrics(
            sessions=[],
            today_tokens=0,
            week_tokens=0,
            today_minutes=0,
            today_sessions=0,
            generated_at=now,
            rate_limits=local,
        )

        result = metrics_summary(metrics, account)

        self.assertEqual(result["rate_limits"]["primary"]["used_percent"], 80)
        self.assertEqual(result["rate_limits_source"], "app-server")

    @patch("codex_usage_supervisor.service.fetch_account_rate_limits")
    @patch("codex_usage_supervisor.service.collect_metrics")
    def test_collect_summary_falls_back_when_account_refresh_fails(
        self,
        collect_metrics_mock,
        fetch_account_rate_limits_mock,
    ) -> None:
        now = datetime.now().astimezone()
        collect_metrics_mock.return_value = DashboardMetrics(
            sessions=[],
            today_tokens=0,
            week_tokens=0,
            today_minutes=0,
            today_sessions=0,
            generated_at=now,
        )
        fetch_account_rate_limits_mock.side_effect = AccountLimitsError("offline")

        result = collect_summary()

        self.assertEqual(result["rate_limits_source"], "local-session")
        self.assertEqual(result["rate_limits_refresh_error"], "offline")


    def test_selects_newest_snapshot_and_preserves_observation_time(self) -> None:
        now = datetime.now().astimezone()
        def limits(offset, used):
            return RateLimits("plus", RateWindow(used, 300, None), None, now + timedelta(minutes=offset))
        for local_time, network_time, account_time, expected in [
            (0, 1, 2, "app-server"),
            (2, 1, 0, "local-session"),
            (0, 2, 1, "network-cache"),
            (0, 1, 1, "app-server"),
        ]:
            with self.subTest(source=expected, times=(local_time, network_time, account_time)):
                local = limits(local_time, 10)
                cached = limits(network_time, 80)
                account = limits(account_time, 20)
                metrics = DashboardMetrics([], 0, 0, 0, 0, now, local)
                result = metrics_summary(metrics, account, cached)
                self.assertEqual(result["rate_limits_source"], expected)
                self.assertEqual(result["rate_limits"]["observed_at"],
                                 (now + timedelta(minutes=max(local_time, network_time, account_time))).isoformat())

    @patch("codex_usage_supervisor.service.fetch_account_rate_limits")
    @patch("codex_usage_supervisor.service.collect_metrics")
    def test_network_cache_survives_offline_refresh_and_restart(self, metrics_mock, fetch_mock) -> None:
        now = datetime.now().astimezone()
        local = RateLimits("plus", RateWindow(10, 300, None), None, now - timedelta(hours=1))
        account = RateLimits("plus", RateWindow(80, 300, now + timedelta(hours=4)), None, now)
        metrics_mock.return_value = DashboardMetrics([], 0, 0, 0, 0, now, local)
        fetch_mock.return_value = account
        self.assertEqual(collect_summary()["rate_limits_source"], "app-server")
        self.assertEqual(load_network_limits(self.cache_path), account)

        # A fresh invocation reads disk; no service instance or in-memory cache is needed.
        fetch_mock.side_effect = AccountLimitsError("offline")
        for _ in range(2):
            result = collect_summary()
            self.assertEqual(result["rate_limits_source"], "network-cache")
            self.assertEqual(result["rate_limits"]["primary"]["used_percent"], 80)
            self.assertEqual(result["rate_limits"]["observed_at"], now.isoformat())
            self.assertEqual(result["rate_limits_refresh_error"], "offline")

        # New local data wins while offline, even if its percentage is lower after reset.
        local.observed_at = now + timedelta(minutes=1)
        self.assertEqual(collect_summary()["rate_limits_source"], "local-session")
        self.assertEqual(load_network_limits(self.cache_path), account)

        # Reconnection saves the new account result and restores the live source label.
        account.observed_at = now + timedelta(minutes=2)
        account.primary.used_percent = 5
        fetch_mock.side_effect = None
        self.assertEqual(collect_summary()["rate_limits"]["primary"]["used_percent"], 5)
        self.assertEqual(load_network_limits(self.cache_path), account)

    @patch("codex_usage_supervisor.service.fetch_account_rate_limits")
    @patch("codex_usage_supervisor.service.collect_metrics")
    def test_failed_cache_write_does_not_hide_fresh_account_limits(self, metrics_mock, fetch_mock) -> None:
        now = datetime.now().astimezone()
        metrics_mock.return_value = DashboardMetrics([], 0, 0, 0, 0, now)
        fetch_mock.return_value = RateLimits("plus", RateWindow(80, 300, None), None, now)
        with patch("codex_usage_supervisor.service.save_network_limits", side_effect=OSError("read-only")):
            result = collect_summary(Settings())
        self.assertEqual(result["rate_limits_source"], "app-server")
        self.assertEqual(result["rate_limits_cache_error"], "read-only")

    @patch("codex_usage_supervisor.service.fetch_account_rate_limits")
    @patch("codex_usage_supervisor.service.collect_metrics")
    def test_older_account_response_does_not_overwrite_newer_network_cache(self, metrics_mock, fetch_mock) -> None:
        now = datetime.now().astimezone()
        newer = RateLimits("plus", RateWindow(80, 300, None), None, now)
        save_network_limits(self.cache_path, newer)
        metrics_mock.return_value = DashboardMetrics([], 0, 0, 0, 0, now)
        fetch_mock.return_value = RateLimits("plus", RateWindow(10, 300, None), None, now - timedelta(minutes=1))
        self.assertEqual(collect_summary()["rate_limits_source"], "network-cache")
        self.assertEqual(load_network_limits(self.cache_path), newer)


if __name__ == "__main__":
    unittest.main()
