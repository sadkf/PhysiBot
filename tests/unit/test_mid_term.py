"""Unit tests for memory/mid_term.py (L2)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from physi_core.memory.mid_term import MidTermMemory


class TestMidTermSegments:
    def test_write_and_read_segment(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        ts = datetime(2026, 4, 5, 14, 30, tzinfo=timezone.utc)
        path = mem.write_segment("# 活动摘要\n编码中", ts=ts)
        assert path.name == "2026-04-05_1430.md"
        assert mem.read_segment("2026-04-05_1430.md") == "# 活动摘要\n编码中"

    def test_list_segments(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        ts1 = datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc)
        ts3 = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)
        mem.write_segment("seg1", ts=ts1)
        mem.write_segment("seg2", ts=ts2)
        mem.write_segment("seg3", ts=ts3)

        all_segs = mem.list_segments()
        assert len(all_segs) == 3
        assert all_segs[0].name == "2026-04-05_1000.md"  # newest first

    def test_list_segments_by_date(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_segment("a", ts=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc))
        mem.write_segment("b", ts=datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc))

        day5 = mem.list_segments("2026-04-05")
        assert len(day5) == 1

    def test_get_recent_segments(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_segment("old", ts=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc))
        mem.write_segment("mid", ts=datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc))
        mem.write_segment("new", ts=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc))

        recent = mem.get_recent_segments(2)
        assert len(recent) == 2
        assert recent[0] == "new"

    def test_get_segments_for_day(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_segment("a", ts=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc))
        mem.write_segment("b", ts=datetime(2026, 4, 5, 14, 0, tzinfo=timezone.utc))

        segs = mem.get_segments_for_day("2026-04-05")
        assert segs == ["a", "b"]

    def test_read_nonexistent_segment(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        assert mem.read_segment("nonexistent.md") is None

    def test_cleanup_segments(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_segment("a", ts=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc))
        mem.write_segment("b", ts=datetime(2026, 4, 5, 9, 30, tzinfo=timezone.utc))
        assert mem.segment_count == 2

        removed = mem.cleanup_segments(["2026-04-05_0900.md"])
        assert removed == 1
        assert mem.segment_count == 1

    def test_segment_count(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        assert mem.segment_count == 0
        mem.write_segment("x", ts=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc))
        assert mem.segment_count == 1


class TestMidTermDaily:
    def test_write_and_read_daily(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_daily("# 日报\n今天写了代码", date="2026-04-05")
        content = mem.read_daily("2026-04-05")
        assert content is not None
        assert "写了代码" in content

    def test_list_dailies(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_daily("d1", date="2026-04-04")
        mem.write_daily("d2", date="2026-04-05")
        assert mem.daily_count == 2
        dailies = mem.list_dailies()
        assert dailies[0].name == "2026-04-05.md"  # newest first

    def test_get_recent_dailies(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        for i in range(1, 6):
            mem.write_daily(f"day{i}", date=f"2026-04-0{i}")
        recent = mem.get_recent_dailies(3)
        assert len(recent) == 3


class TestMidTermWeekly:
    def test_write_and_read_weekly(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_weekly("# 周报\n本周写了 PhysiBot", week="2026-W14")
        content = mem.read_weekly("2026-W14")
        assert content is not None
        assert "PhysiBot" in content

    def test_list_weeklies(self, tmp_path: Path) -> None:
        mem = MidTermMemory(tmp_path / "mid_term")
        mem.write_weekly("w1", week="2026-W13")
        mem.write_weekly("w2", week="2026-W14")
        assert mem.weekly_count == 2
