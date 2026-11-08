"""Device-free integration checks; install requirements.txt to enable these."""
import importlib.util
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import remote_agy

HAS_DEPS = all(importlib.util.find_spec(name) is not None
               for name in ("hid", "PIL", "certifi", "websockets"))


@unittest.skipUnless(HAS_DEPS, "dashboard checks require requirements.txt")
class DashboardQuotaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dashboard
        import pages
        from usage import ClaudeUsage, CodexUsage
        cls.dashboard = dashboard
        cls.pages = pages
        cls.claude_type = ClaudeUsage
        cls.codex_type = CodexUsage

    def collect(self, buckets):
        with patch.object(self.dashboard, "agy_quota", return_value=buckets), \
             patch.object(self.dashboard, "claude_usage", return_value=self.claude_type()), \
             patch.object(self.dashboard, "codex_live", return_value=self.codex_type()), \
             ThreadPoolExecutor(max_workers=2) as pool:
            return self.dashboard.collect_llms(pool)

    def test_fixture_reaches_dashboard_with_existing_group_policy(self):
        payload = json.loads((Path(__file__).parent / "fixtures/agy_quota.json").read_text())
        llms = self.collect(remote_agy.parse_quota(payload))
        agy = llms[2]
        self.assertEqual(agy.name, "AGY")
        # The later model's 5h bucket remains the dashboard's displayed value.
        self.assertEqual(agy.five.remaining, 1.0)
        self.assertIsNone(agy.five.reset)
        self.assertEqual(agy.week.remaining, .75)
        self.assertEqual(agy.week.reset.isoformat(), "2030-01-07T12:00:00+00:00")
        grid = self.pages.page_grid(llms, datetime(2030, 1, 1, tzinfo=timezone.utc))
        self.assertEqual((grid[2].title, grid[7].title), ("100%", "75%"))

    def test_exhausted_quota_remains_zero_in_summary_and_grid(self):
        payload = {"status": "SUCCESS", "command": {"data": {"groups": [
            {"name": "Synthetic", "buckets": [
                {"window": "5h", "remaining_fraction": 0},
                {"window": "weekly", "remaining_fraction": .75}]}]}}}
        llms = self.collect(remote_agy.parse_quota(payload))
        grid = self.pages.page_grid(llms, datetime.now(timezone.utc))
        self.assertEqual(grid[2].title, "0%")
        self.assertEqual(grid[2].ratio, 0)
        self.assertEqual(self.pages.llm_tile(llms[2]).title, "0%")

    def test_unavailable_quota_displays_placeholder_instead_of_zero(self):
        llms = self.collect(None)
        self.assertIsNone(llms[2].five)
        self.assertIsNone(llms[2].week)
        grid = self.pages.page_grid(llms, datetime.now(timezone.utc))
        for index in (2, 7):
            self.assertEqual(grid[index].title, "-")
            self.assertIsNone(grid[index].ratio)
        self.assertEqual(self.pages.llm_tile(llms[2]).title, "-")
