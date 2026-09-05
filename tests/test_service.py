from __future__ import annotations

import unittest
from datetime import datetime

from codex_usage_supervisor.metrics import DashboardMetrics, SessionMetric, TokenUsage
from codex_usage_supervisor.service import metrics_summary


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
        self.assertNotIn("content", str(result).lower())


if __name__ == "__main__":
    unittest.main()
