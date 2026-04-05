"""Unit tests for integrations/activitywatch.py."""

from __future__ import annotations

from physi_core.integrations.activitywatch import ActivityWatchClient, AppUsage


class TestAppUsage:
    def test_duration_minutes(self) -> None:
        u = AppUsage(app="VSCode", title="main.py", duration_seconds=1200)
        assert u.duration_minutes == 20.0

    def test_zero_duration(self) -> None:
        u = AppUsage(app="App", title="", duration_seconds=0)
        assert u.duration_minutes == 0.0


class TestFormatForLLM:
    def test_format_basic(self) -> None:
        usages = [
            AppUsage("VSCode", "main.py", 1800),
            AppUsage("Chrome", "Google", 600),
        ]
        text = ActivityWatchClient.format_for_llm(usages)
        assert "VSCode" in text
        assert "30" in text  # 30 minutes
        assert "Chrome" in text

    def test_format_empty(self) -> None:
        text = ActivityWatchClient.format_for_llm([])
        assert "无" in text
