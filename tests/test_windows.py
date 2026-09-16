"""Platform-independent transport tests also run on Windows CI."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_usage_supervisor.account import AccountLimitsError, fetch_account_rate_limits
from codex_usage_supervisor.config import Settings
from codex_usage_supervisor.metrics import collect_metrics


class TransportTests(unittest.TestCase):
    def run_server(self, source, timeout=2):
        real_popen = subprocess.Popen
        processes = []
        def launch(_args, **kwargs):
            process = real_popen([sys.executable, "-u", "-c", source], **kwargs)
            processes.append(process)
            return process
        with patch("codex_usage_supervisor.account.find_codex_executable", return_value=Path(sys.executable)), patch("codex_usage_supervisor.account.subprocess.Popen", side_effect=launch):
            try:
                return fetch_account_rate_limits(timeout=timeout, codex_home="test-custom-home")
            finally:
                self.assertTrue(all(p.poll() is not None for p in processes))

    def test_fragmented_lines_notifications_and_custom_home(self):
        result = self.run_server('''
import json, sys, os
assert os.environ['CODEX_HOME'] == 'test-custom-home'
for line in sys.stdin:
    request = json.loads(line)
    if request.get('id') == 1:
        print('not-json', flush=True)
        print(json.dumps({'method':'notice'}), flush=True)
        print(json.dumps({'id':1,'result':{}}), flush=True)
    elif request.get('id') == 2:
        sys.stdout.write('{"id":2,'); sys.stdout.flush()
        print('"result":{"rateLimits":{"primary":{"usedPercent":42,"windowDurationMins":300}}}}', flush=True)
''')
        self.assertEqual(result.primary.used_percent, 42)

    def test_timeout_kills_child(self):
        with self.assertRaisesRegex(AccountLimitsError, "timed out"):
            self.run_server("import time; time.sleep(30)", timeout=0.2)

    def test_exit_is_reported(self):
        with self.assertRaisesRegex(AccountLimitsError, "exited unexpectedly"):
            self.run_server("pass")

    def test_launch_error_is_recoverable(self):
        with patch("codex_usage_supervisor.account.find_codex_executable", return_value=Path("missing")), patch("codex_usage_supervisor.account.subprocess.Popen", side_effect=OSError("missing")):
            with self.assertRaises(AccountLimitsError):
                fetch_account_rate_limits()

    def test_backend_recovers_after_bad_request_and_eof(self):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        process = subprocess.run([sys.executable, "-m", "codex_usage_supervisor.windows_backend"], input='invalid\n{"method":"settings/read"}\n', text=True, capture_output=True, env=environment, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        results = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertIn("error", results[0])
        self.assertIn("refresh_seconds", results[1]["result"])


class WindowsMetricsTests(unittest.TestCase):
    def test_cache_invalidates_on_append_and_day_change(self):
        from datetime import datetime, timedelta
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sessions").mkdir()
            path = root / "sessions/test.jsonl"
            now = datetime.now().astimezone()
            def record(tokens):
                return json.dumps({"timestamp": now.isoformat(), "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": tokens}}}}) + "\n"
            path.write_text(record(100), encoding="utf-8")
            first = collect_metrics(root, now)
            self.assertEqual(first.today_tokens, 100)
            self.assertEqual(first.week_tokens, 100)
            with patch("codex_usage_supervisor.metrics.parse_session", side_effect=AssertionError("cache missed")):
                self.assertEqual(collect_metrics(root, now).today_tokens, 100)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(record(200))
            self.assertEqual(collect_metrics(root, now).today_tokens, 200)
            self.assertEqual(collect_metrics(root, now + timedelta(days=1)).today_tokens, 0)
            path.unlink()
            self.assertEqual(collect_metrics(root, now).today_tokens, 0)

    def test_corrupt_settings_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(Settings.load(path).refresh_seconds, 30)


if __name__ == "__main__":
    unittest.main()
