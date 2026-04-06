"""Screenpipe REST API client — local OCR text extraction.

Processing pipeline (best-practice approach):
  1. Fetch frames from Screenpipe with min_length filter to drop noise.
  2. Group frames by (app_name, window_name).
  3. Within each group: exact-hash dedup → similarity dedup via
     difflib.SequenceMatcher (replaces the old prefix-char comparison).
  4. Format for LLM with per-group budget allocation based on activity level.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from physi_core.observability import emit_event

logger = logging.getLogger(__name__)

# Minimum OCR text length to bother keeping (filters Tesseract garbage)
_MIN_TEXT_LEN = 8
# Similarity threshold: frames with ratio >= this are considered duplicates
_DEDUP_RATIO = 0.85


@dataclass
class OCRFrame:
    """A single OCR capture frame."""

    text: str
    app_name: str
    window_name: str
    timestamp: str


@dataclass
class AppGroup:
    """Deduplicated, time-ordered frames from one (app, window) pair."""

    app_name: str
    window_name: str
    frames: list[OCRFrame] = field(default_factory=list)

    @property
    def time_start(self) -> str:
        return self.frames[0].timestamp if self.frames else ""

    @property
    def time_end(self) -> str:
        return self.frames[-1].timestamp if self.frames else ""

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    def merged_text(self) -> str:
        """Return all unique frame texts joined with newlines."""
        return "\n".join(f.text for f in self.frames)


class ScreenpipeClient:
    """Client for the local Screenpipe REST API (http://localhost:3030)."""

    def __init__(self, api_url: str = "http://localhost:3030") -> None:
        self._base_url = api_url.rstrip("/")

    # ── Text cleaning ────────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove surrogate pairs and non-printable chars left by Tesseract OCR."""
        cleaned = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        cleaned = cleaned.replace("\ufffd", "")
        return cleaned.strip()

    # ── API access ───────────────────────────────────────────────────────────

    async def search_ocr(
        self,
        minutes: int = 30,
        limit: int = 100,
        query: str | None = None,
    ) -> list[OCRFrame]:
        """Fetch OCR text from the last N minutes.

        Uses min_length to filter out very short / garbled OCR fragments at the
        server level, reducing bandwidth and client-side noise.
        """
        params: dict[str, Any] = {
            "content_type": "ocr",
            "start_time": f"{minutes}m ago",
            "end_time": "now",
            "limit": limit,
            "min_length": _MIN_TEXT_LEN,
        }
        if query:
            params["q"] = query

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("Screenpipe API error: %s", e)
            emit_event("screenpipe.query.error", error=str(e), minutes=minutes, query=query or "")
            return []

        frames: list[OCRFrame] = []
        for item in data.get("data", []):
            content = item.get("content", {})
            raw_text = content.get("text", "")
            cleaned = self._clean_text(raw_text)
            if len(cleaned) < _MIN_TEXT_LEN:
                continue
            frames.append(OCRFrame(
                text=cleaned,
                app_name=content.get("app_name", ""),
                window_name=content.get("window_name", ""),
                timestamp=item.get("timestamp", ""),
            ))

        emit_event(
            "screenpipe.query.ok",
            minutes=minutes,
            query=query or "",
            frames=len(frames),
        )
        logger.debug("Screenpipe: fetched %d frames (last %dm)", len(frames), minutes)
        return frames

    async def health_check(self) -> bool:
        """Check if Screenpipe is running."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # ── Processing pipeline ──────────────────────────────────────────────────

    @staticmethod
    def group_and_deduplicate(frames: list[OCRFrame]) -> list[AppGroup]:
        """Group frames by (app, window) and deduplicate within each group.

        Steps per group:
          1. Exact-hash dedup — drops frames with identical text.
          2. Similarity dedup — drops frames where SequenceMatcher ratio
             to the previous kept frame is >= _DEDUP_RATIO (handles scrolling,
             appended text, minor OCR drift, unlike prefix-char comparison).
        """
        if not frames:
            return []

        # Build ordered groups (preserves first-seen order of app+window combos)
        group_index: dict[tuple[str, str], AppGroup] = {}
        for frame in frames:
            key = (frame.app_name, frame.window_name)
            if key not in group_index:
                group_index[key] = AppGroup(app_name=frame.app_name, window_name=frame.window_name)
            group_index[key].frames.append(frame)

        result: list[AppGroup] = []
        total_before = 0
        total_after = 0

        for group in group_index.values():
            total_before += len(group.frames)
            deduped = _dedup_frames(group.frames)
            total_after += len(deduped)
            if deduped:
                group.frames = deduped
                result.append(group)

        logger.debug(
            "OCR dedup: %d → %d frames across %d windows",
            total_before,
            total_after,
            len(result),
        )
        emit_event(
            "screenpipe.dedup",
            frames_before=total_before,
            frames_after=total_after,
            groups=len(result),
        )
        return result

    @staticmethod
    def format_for_llm(groups: list[AppGroup], budget: int = 4000) -> str:
        """Format grouped frames into a compact text for LLM consumption.

        Allocates the character budget proportionally by activity level
        (frame count), so the most active window gets the most space.
        Groups are sorted most-active-first.
        """
        if not groups:
            return ""

        # Sort by activity (most frames first)
        sorted_groups = sorted(groups, key=lambda g: g.frame_count, reverse=True)
        total_frames = sum(g.frame_count for g in sorted_groups)

        lines: list[str] = []
        for group in sorted_groups:
            # Proportional budget for this group (min 200 chars)
            share = max(200, int(budget * group.frame_count / total_frames))
            text = group.merged_text()

            # Format time range (show HH:MM portion only)
            t_start = _fmt_time(group.time_start)
            t_end = _fmt_time(group.time_end)
            time_range = f"{t_start}–{t_end}" if t_start and t_end and t_start != t_end else t_start

            header = f"[{group.app_name}] {group.window_name}"
            if time_range:
                header += f"  ({time_range})"
            lines.append(header)

            # Smart truncation: keep beginning + end if text > share
            if len(text) <= share:
                lines.append(text)
            else:
                half = share // 2
                lines.append(text[:half])
                lines.append(f"  … ({len(text) - share} 字符省略) …")
                lines.append(text[-half:])

            lines.append("")  # blank separator between groups

        return "\n".join(lines).rstrip()

    # ── Legacy compatibility shim ────────────────────────────────────────────

    @staticmethod
    def deduplicate(frames: list[OCRFrame], threshold: float = _DEDUP_RATIO) -> list[OCRFrame]:
        """Flat dedup for backward compatibility (used by the agent tool).

        Prefers group_and_deduplicate for the perception pipeline.
        """
        return _dedup_frames(frames, threshold=threshold)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace"), usedforsecurity=False).hexdigest()


def _similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio — handles insertions, deletions, reordering."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _dedup_frames(
    frames: list[OCRFrame],
    threshold: float = _DEDUP_RATIO,
) -> list[OCRFrame]:
    """Deduplicate a flat list of frames using hash + similarity."""
    if not frames:
        return []

    seen_hashes: set[str] = set()
    kept: list[OCRFrame] = []

    for frame in frames:
        h = _content_hash(frame.text)
        if h in seen_hashes:
            continue  # exact duplicate
        seen_hashes.add(h)

        if kept and _similarity(kept[-1].text, frame.text) >= threshold:
            continue  # highly similar to previous — skip

        kept.append(frame)

    return kept


def _fmt_time(iso_ts: str) -> str:
    """Extract HH:MM from an ISO 8601 timestamp string."""
    if not iso_ts:
        return ""
    # "2026-04-06T14:30:05.123Z" → "14:30"
    try:
        t_part = iso_ts.split("T")[1] if "T" in iso_ts else iso_ts
        hhmm = t_part[:5]
        return hhmm
    except Exception:
        return ""
