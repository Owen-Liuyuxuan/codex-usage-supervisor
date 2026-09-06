from __future__ import annotations

import unittest

from codex_usage_supervisor.account import AccountLimitsError, parse_rate_limits_response


class AccountLimitsTest(unittest.TestCase):
    def test_prefers_named_codex_bucket(self) -> None:
        result = parse_rate_limits_response({
            "id": 2,
            "result": {
                "rateLimits": {
                    "planType": "fallback",
                    "primary": {"usedPercent": 1, "windowDurationMins": 60},
                },
                "rateLimitsByLimitId": {
                    "codex": {
                        "planType": "plus",
                        "primary": {
                            "usedPercent": 84,
                            "windowDurationMins": 300,
                            "resetsAt": 1_788_615_814,
                        },
                        "secondary": {
                            "usedPercent": 13,
                            "windowDurationMins": 10_080,
                            "resetsAt": 1_789_202_614,
                        },
                    }
                },
            },
        })
        self.assertEqual(result.plan_type, "plus")
        self.assertEqual(result.primary.used_percent, 84)
        self.assertEqual(result.primary.window_minutes, 300)
        self.assertEqual(result.secondary.used_percent, 13)

    def test_rejects_empty_limit_windows(self) -> None:
        with self.assertRaisesRegex(AccountLimitsError, "windows are unavailable"):
            parse_rate_limits_response({
                "id": 2,
                "result": {"rateLimits": {"primary": None, "secondary": None}},
            })


if __name__ == "__main__":
    unittest.main()
