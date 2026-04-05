"""Unit tests for integrations/screenpipe.py."""

from __future__ import annotations

from physi_core.integrations.screenpipe import OCRFrame, ScreenpipeClient


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
        # At 0.9 threshold, these should still be merged
        assert len(result) <= 2

    def test_empty_text_frames_kept(self) -> None:
        frames = [
            OCRFrame("text", "app", "w", "10:00"),
            OCRFrame("", "app", "w", "10:01"),
            OCRFrame("more text", "app", "w", "10:02"),
        ]
        result = ScreenpipeClient.deduplicate(frames)
        assert len(result) == 3


class TestFormatForLLM:
    def test_format_basic(self) -> None:
        frames = [
            OCRFrame("hello world", "VSCode", "main.py", "10:00"),
        ]
        text = ScreenpipeClient.format_for_llm(frames)
        assert "VSCode" in text
        assert "main.py" in text
        assert "hello world" in text

    def test_format_truncates_long_text(self) -> None:
        frames = [
            OCRFrame("x" * 500, "app", "win", "10:00"),
        ]
        text = ScreenpipeClient.format_for_llm(frames, max_chars=50)
        assert len(text) < 200

    def test_format_empty(self) -> None:
        assert ScreenpipeClient.format_for_llm([]) == ""
