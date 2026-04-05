"""L2 Mid-Term Memory — 30-minute activity segments + daily/weekly summaries."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class MidTermMemory:
    """Manages L2 mid-term episodic memory: 30-min segments, daily, and weekly summaries.

    Directory layout:
        mid_term/
        ├── segments/      # 30-min activity snapshots
        ├── daily/         # day-level summaries
        └── weekly/        # week-level summaries
    """

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._segments_dir = directory / "segments"
        self._daily_dir = directory / "daily"
        self._weekly_dir = directory / "weekly"
        for d in (self._segments_dir, self._daily_dir, self._weekly_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── Segments (30 min) ──────────────────────────

    def write_segment(self, content: str, ts: datetime | None = None) -> Path:
        """Write a 30-min segment file. Returns the path written."""
        ts = ts or datetime.now(UTC)
        filename = ts.strftime("%Y-%m-%d_%H%M") + ".md"
        path = self._segments_dir / filename
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote segment: %s (%d chars)", filename, len(content))
        return path

    def read_segment(self, filename: str) -> str | None:
        """Read a specific segment file."""
        path = self._segments_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else None

    def list_segments(self, date: str | None = None) -> list[Path]:
        """List segment files, optionally filtered by date (YYYY-MM-DD). Newest first."""
        pattern = f"{date}_*.md" if date else "*.md"
        return sorted(self._segments_dir.glob(pattern), reverse=True)

    def get_recent_segments(self, count: int = 2) -> list[str]:
        """Get content of the N most recent segments."""
        paths = self.list_segments()[:count]
        return [p.read_text(encoding="utf-8") for p in paths]

    def get_segments_for_day(self, date: str) -> list[str]:
        """Get all segment contents for a specific date (YYYY-MM-DD)."""
        paths = sorted(self._segments_dir.glob(f"{date}_*.md"))
        return [p.read_text(encoding="utf-8") for p in paths]

    # ── Daily summaries ────────────────────────────

    def write_daily(self, content: str, date: str | None = None) -> Path:
        """Write a daily summary. date format: YYYY-MM-DD."""
        date = date or datetime.now(UTC).strftime("%Y-%m-%d")
        path = self._daily_dir / f"{date}.md"
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote daily summary: %s", date)
        return path

    def read_daily(self, date: str) -> str | None:
        """Read a daily summary."""
        path = self._daily_dir / f"{date}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_today_summary(self) -> str:
        """Get today's daily summary, empty if not yet generated."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return self.read_daily(today) or ""

    def list_dailies(self) -> list[Path]:
        """List daily summary files, newest first."""
        return sorted(self._daily_dir.glob("*.md"), reverse=True)

    def get_recent_dailies(self, count: int = 7) -> list[str]:
        """Get content of the N most recent daily summaries."""
        paths = self.list_dailies()[:count]
        return [p.read_text(encoding="utf-8") for p in paths]

    # ── Weekly summaries ───────────────────────────

    def write_weekly(self, content: str, week: str | None = None) -> Path:
        """Write a weekly summary. week format: YYYY-WNN."""
        week = week or datetime.now(UTC).strftime("%G-W%V")
        path = self._weekly_dir / f"{week}.md"
        path.write_text(content, encoding="utf-8")
        logger.info("Wrote weekly summary: %s", week)
        return path

    def read_weekly(self, week: str) -> str | None:
        """Read a weekly summary."""
        path = self._weekly_dir / f"{week}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def list_weeklies(self) -> list[Path]:
        """List weekly summary files, newest first."""
        return sorted(self._weekly_dir.glob("*.md"), reverse=True)

    # ── Cleanup ────────────────────────────────────

    def cleanup_segments(self, paths_to_remove: list[str]) -> int:
        """Remove segments that LLM marked as recyclable. Returns count removed."""
        removed = 0
        for name in paths_to_remove:
            path = self._segments_dir / name
            if path.exists():
                path.unlink()
                removed += 1
        logger.info("Cleaned up %d segment files", removed)
        return removed

    # ── Stats ──────────────────────────────────────

    @property
    def segment_count(self) -> int:
        return len(list(self._segments_dir.glob("*.md")))

    @property
    def daily_count(self) -> int:
        return len(list(self._daily_dir.glob("*.md")))

    @property
    def weekly_count(self) -> int:
        return len(list(self._weekly_dir.glob("*.md")))
