"""Unit tests for integrations/clipboard.py."""

from __future__ import annotations

from physi_core.integrations.clipboard import ClipboardEntry, ClipboardMonitor


class TestClipboardMonitor:
    def test_initial_state(self) -> None:
        cm = ClipboardMonitor(poll_interval=1)
        assert cm.entry_count == 0
        assert cm.get_recent() == []

    def test_format_empty(self) -> None:
        cm = ClipboardMonitor()
        assert cm.format_for_llm() == ""

    def test_history_dedup(self) -> None:
        cm = ClipboardMonitor()
        # Simulate adding entries
        cm._history.append(ClipboardEntry("hello", "ts1"))
        cm._history.append(ClipboardEntry("world", "ts2"))
        assert cm.entry_count == 2
        assert cm.get_recent(1) == ["world"]

    def test_format_for_llm(self) -> None:
        cm = ClipboardMonitor()
        cm._history.append(ClipboardEntry("copied text", "10:00"))
        text = cm.format_for_llm()
        assert "剪贴板" in text
        assert "copied text" in text

    def test_max_history_enforced(self) -> None:
        cm = ClipboardMonitor(max_history=3)
        for i in range(5):
            cm._history.append(ClipboardEntry(f"text{i}", f"ts{i}"))
        assert cm.entry_count == 3
        assert cm.get_recent()[0] == "text2"
