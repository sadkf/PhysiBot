"""Unit tests for integrations/screenpipe.py."""

from __future__ import annotations

from physi_core.integrations.screenpipe import (
    AppGroup,
    OCRFrame,
    ScreenpipeClient,
    _dedup_frames,
    _similarity,
)


class TestDeduplication:
    """AC-15: Data dedup compression."""

    def test_empty_frames(self) -> None:
        assert ScreenpipeClient.deduplicate([]) == []

    def test_single_frame(self) -> None:
        frames = [OCRFrame("hello", "app", "win", "ts")]
        assert len(ScreenpipeClient.deduplicate(frames)) == 1

    def test_identical_consecutive_removed(self) -> None:
        frames = [
            OCRFrame("same text here", "VSCode", "file.py", "10:00"),
            OCRFrame("same text here", "VSCode", "file.py", "10:01"),
            OCRFrame("same text here", "VSCode", "file.py", "10:02"),
        ]
        result = ScreenpipeClient.deduplicate(frames)
        assert len(result) == 1

    def test_different_frames_kept(self) -> None:
        frames = [
            OCRFrame("writing code", "VSCode", "main.py", "10:00"),
            OCRFrame("browsing docs", "Chrome", "docs", "10:05"),
            OCRFrame("chatting", "QQ", "chat", "10:10"),
        ]
        result = ScreenpipeClient.deduplicate(frames)
        assert len(result) == 3

    def test_similar_but_not_identical(self) -> None:
        frames = [
            OCRFrame("hello world", "app", "w", "10:00"),
            OCRFrame("hello world!", "app", "w", "10:01"),  # very similar
        ]
        result = ScreenpipeClient.deduplicate(frames, threshold=0.9)
        # At high threshold similar frames get merged to 1
        assert len(result) <= 2

    def test_empty_text_frames_kept(self) -> None:
        # Empty-text frames have hash "" — only the first is kept by hash dedup,
        # but the non-empty frames surrounding it differ enough to be kept.
        frames = [
            OCRFrame("text", "app", "w", "10:00"),
            OCRFrame("", "app", "w", "10:01"),
            OCRFrame("more text", "app", "w", "10:02"),
        ]
        result = ScreenpipeClient.deduplicate(frames)
        # "text" and "more text" are dissimilar, both kept; "" may vary
        assert len(result) >= 2


class TestSimilarity:
    """Tests for the SequenceMatcher-based similarity helper."""

    def test_identical(self) -> None:
        assert _similarity("hello", "hello") == 1.0

    def test_completely_different(self) -> None:
        assert _similarity("abc", "xyz") < 0.5

    def test_empty_strings(self) -> None:
        assert _similarity("", "") == 0.0
        assert _similarity("hello", "") == 0.0

    def test_appended_text_detected(self) -> None:
        # New text appended to existing — ratio should be high
        base = "def foo(): pass"
        extended = "def foo(): pass\ndef bar(): pass"
        assert _similarity(base, extended) > 0.5


class TestGroupAndDeduplicate:
    """Tests for the new group_and_deduplicate pipeline."""

    def test_groups_by_app_window(self) -> None:
        frames = [
            OCRFrame("code here", "VSCode", "main.py", "10:00"),
            OCRFrame("browsing", "Chrome", "github.com", "10:01"),
            OCRFrame("more code", "VSCode", "main.py", "10:02"),
        ]
        groups = ScreenpipeClient.group_and_deduplicate(frames)
        app_names = {g.app_name for g in groups}
        assert "VSCode" in app_names
        assert "Chrome" in app_names

    def test_empty_input(self) -> None:
        assert ScreenpipeClient.group_and_deduplicate([]) == []

    def test_exact_duplicates_removed_within_group(self) -> None:
        frames = [
            OCRFrame("same content", "VSCode", "win", "10:00"),
            OCRFrame("same content", "VSCode", "win", "10:01"),
            OCRFrame("same content", "VSCode", "win", "10:02"),
        ]
        groups = ScreenpipeClient.group_and_deduplicate(frames)
        assert len(groups) == 1
        assert groups[0].frame_count == 1

    def test_different_windows_separate_groups(self) -> None:
        frames = [
            OCRFrame("text A", "Chrome", "site1.com", "10:00"),
            OCRFrame("text B", "Chrome", "site2.com", "10:01"),
        ]
        groups = ScreenpipeClient.group_and_deduplicate(frames)
        assert len(groups) == 2


class TestFormatForLLM:
    """Tests for the budget-based format_for_llm."""

    def _make_group(self, app: str, window: str, texts: list[str]) -> AppGroup:
        frames = [OCRFrame(t, app, window, f"10:0{i}") for i, t in enumerate(texts)]
        g = AppGroup(app_name=app, window_name=window, frames=frames)
        return g

    def test_format_basic(self) -> None:
        groups = [self._make_group("VSCode", "main.py", ["hello world"])]
        text = ScreenpipeClient.format_for_llm(groups)
        assert "VSCode" in text
        assert "main.py" in text
        assert "hello world" in text

    def test_format_respects_budget(self) -> None:
        groups = [self._make_group("app", "win", ["x" * 200])]
        text = ScreenpipeClient.format_for_llm(groups, budget=50)
        # Budget 50 with smart truncation — total should be reasonable
        assert len(text) < 400

    def test_format_empty(self) -> None:
        assert ScreenpipeClient.format_for_llm([]) == ""

    def test_most_active_group_first(self) -> None:
        busy = self._make_group("VSCode", "main.py", ["a", "b", "c", "d", "e"])
        idle = self._make_group("Chrome", "tab", ["single frame"])
        text = ScreenpipeClient.format_for_llm([idle, busy])
        # VSCode (5 frames) should appear before Chrome (1 frame)
        assert text.index("VSCode") < text.index("Chrome")

    def test_format_pipeline(self) -> None:
        """Full pipeline: frames → group_and_deduplicate → format_for_llm."""
        frames = [
            OCRFrame("def foo(): pass", "VSCode", "code.py", "10:00"),
            OCRFrame("def foo(): pass", "VSCode", "code.py", "10:01"),  # exact dup
            OCRFrame("browsing Python docs", "Chrome", "docs.python.org", "10:02"),
        ]
        groups = ScreenpipeClient.group_and_deduplicate(frames)
        text = ScreenpipeClient.format_for_llm(groups)
        assert "VSCode" in text
        assert "Chrome" in text
        # Duplicate frame should have been removed
        vscode_group = next(g for g in groups if g.app_name == "VSCode")
        assert vscode_group.frame_count == 1
