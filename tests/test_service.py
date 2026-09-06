from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from codex_usage_supervisor.account import AccountLimitsError
from codex_usage_supervisor.metrics import (
    DashboardMetrics,
    RateLimits,
    RateWindow,
    SessionMetric,
    TokenUsage,
)
from codex_usage_supervisor.service import collect_summary, metrics_summary


class ServiceContractTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
