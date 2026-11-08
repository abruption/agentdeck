"""Synthetic contract tests; no network, CLI installation, credentials or device."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import remote_agy as agy

FIXTURE = json.loads((Path(__file__).parent / "fixtures/agy_quota.json").read_text())


def quota(groups):
    return {"status": "SUCCESS", "command": {"data": {"groups": groups}}}


class ParseTests(unittest.TestCase):
    def test_model_groups_windows_zero_and_timezone(self):
        buckets = agy.parse_quota(FIXTURE)
        self.assertEqual([(b.group, b.window, b.remaining) for b in buckets], [
            ("Synthetic model A", "5h", 0.0),
            ("Synthetic model A", "weekly", .75),
            ("Synthetic model B", "5h", 1.0)])
        self.assertEqual(buckets[1].reset.isoformat(), "2030-01-07T12:00:00+00:00")
        self.assertIsNone(buckets[2].reset)

    def test_unavailable_and_wrong_shapes(self):
        for payload in [None, [], 0, {}, {"usage": {"input_tokens": 123}},
                        quota(None), quota([]), quota([None]),
                        quota([{"disabled": True}]), quota([{"enabled": False}]),
                        quota([{"name": "A", "buckets": None}]),
                        {"status": "SUCCESS", "groups": FIXTURE["command"]["data"]["groups"]}]:
            with self.subTest(payload=payload):
                self.assertIsNone(agy.parse_quota(payload))
        for command in [None, [], "usage", {}, {"data": None}, {"data": []}]:
            self.assertIsNone(agy.parse_quota({"status": "SUCCESS", "command": command}))

    def test_invalid_bucket_values_fail_closed(self):
        for field, values in {
            "remaining_fraction": [True, "0", -1, 2, float("nan"), float("inf"), {}, []],
            "window": [None, "daily", 5],
            "reset_time": [True, {}, "bad", "2030-01-01T12:00:00", ""],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    bucket = {"window": "5h", "remaining_fraction": 0}
                    bucket[field] = value
                    self.assertIsNone(agy.parse_quota(quota([
                        {"name": "A", "buckets": [bucket]}])))

    def test_missing_null_disabled_are_not_zero(self):
        for bucket in [{}, {"remaining_fraction": None},
                       {"remaining_fraction": 0, "enabled": False},
                       {"remaining_fraction": 0, "disabled": True}]:
            self.assertIsNone(agy.parse_quota(quota([
                {"name": "A", "buckets": [bucket]}])))

    def test_status_required_even_with_valid_groups(self):
        for status in [None, "ERROR", "FAILED", "success", True, {}, []]:
            with self.subTest(status=status):
                self.assertIsNone(agy.parse_quota({**FIXTURE, "status": status}))
        self.assertIsNone(agy.parse_quota({"command": FIXTURE["command"]}))
        self.assertIsNone(agy.parse_quota({**FIXTURE, "error": "synthetic"}))

    def test_sparse_success_and_unrelated_metadata(self):
        minimal = quota([{"name": "Synthetic", "buckets": [
            {"window": "weekly", "remaining_fraction": 0.42}]}])
        expected = [agy.Bucket("Synthetic", "weekly", .42, None)]
        self.assertEqual(agy.parse_quota(minimal), expected)
        self.assertEqual(agy.parse_quota({**minimal, "response": "not JSON",
            "usage": {"remaining_fraction": 0, "total_tokens": 123}}), expected)
        self.assertIsNone(agy.parse_quota({"status": "SUCCESS", "response": json.dumps(minimal),
            "usage": {"total_tokens": 123}}))

    def test_old_camel_case_is_not_quota(self):
        self.assertIsNone(agy.parse_quota(quota([
            {"displayName": "Synthetic", "buckets": [
                {"window": "weekly", "remainingFraction": .42}]}])))


class TransportTests(unittest.TestCase):
    @patch.object(agy, "HOST", None)
    @patch.object(agy.subprocess, "run")
    def test_disabled_does_not_connect(self, run):
        self.assertIsNone(agy.agy_quota())
        run.assert_not_called()

    @patch.object(agy, "HOST", "synthetic-host")
    @patch.object(agy.subprocess, "run")
    def test_transport_and_payload(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps(FIXTURE))
        self.assertEqual(len(agy.agy_quota()), 3)
        args, kwargs = run.call_args
        self.assertIn("BatchMode=yes", args[0])
        self.assertIn("-T", args[0])
        self.assertEqual(kwargs["timeout"], 90)
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["input"], agy.REMOTE)

    @patch.object(agy, "HOST", "synthetic-host")
    @patch.object(agy.subprocess, "run")
    def test_failures_return_none(self, run):
        for error in [FileNotFoundError(), subprocess.TimeoutExpired("ssh", 90),
                      subprocess.CalledProcessError(255, "ssh"),
                      subprocess.CalledProcessError(1, "ssh", json.dumps(FIXTURE))]:
            run.side_effect = error
            self.assertIsNone(agy.agy_quota())
        run.side_effect = None
        for output in ["not JSON", "", "null", "[]", '{"usage":{"total_tokens":10}}',
                       json.dumps({**FIXTURE, "status": "ERROR"})]:
            run.return_value = subprocess.CompletedProcess([], 0, output)
            self.assertIsNone(agy.agy_quota())


class RemoteScriptTests(unittest.TestCase):
    def execute(self, outcomes):
        output = io.StringIO()
        with patch("subprocess.run", side_effect=outcomes) as run, contextlib.redirect_stdout(output):
            try:
                exec(agy.REMOTE, {})
            except SystemExit as error:
                return error.code, output.getvalue(), run
        return 0, output.getvalue(), run

    def test_supported_cli_and_noninteractive_path(self):
        for version in ["1.1.11", "agy v1.2.15\n", "1.5.3", "v2.0.0"]:
            code, output, run = self.execute([
                subprocess.CompletedProcess([], 0, version),
                subprocess.CompletedProcess([], 0, json.dumps(FIXTURE))])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output), FIXTURE)
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["agy", "-p", "/usage", "--output-format", "json"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["timeout"], 60)
            self.assertTrue(kwargs["check"])
            self.assertIn("/opt/homebrew/bin:", kwargs["env"]["PATH"])
            self.assertIn("/.local/bin:", kwargs["env"]["PATH"])

    def test_old_unknown_cli_never_runs_usage(self):
        for version in ["1.1.10", "0.9.0", "unknown", "1.2.15-preview", ""]:
            code, output, run = self.execute([subprocess.CompletedProcess([], 0, version)])
            self.assertEqual((code, output, run.call_count), (1, "", 1))

    def test_missing_auth_exit_timeout_no_retry_or_output(self):
        for error in [FileNotFoundError(), subprocess.CalledProcessError(1, "agy", json.dumps(FIXTURE)),
                      subprocess.TimeoutExpired("agy", 60)]:
            for outcomes in [[error], [subprocess.CompletedProcess([], 0, "1.2.15"), error]]:
                code, output, run = self.execute(outcomes)
                self.assertEqual((code, output), (1, ""))
                self.assertEqual(run.call_count, len(outcomes))


if __name__ == "__main__":
    unittest.main()
