"""Screenpipe REST API client — local OCR text extraction."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class OCRFrame:
    """A single OCR capture frame."""

    text: str
    app_name: str
    window_name: str
    timestamp: str


class ScreenpipeClient:
    """Client for the local Screenpipe REST API (http://localhost:3030)."""

    def __init__(self, api_url: str = "http://localhost:3030") -> None:
        self._base_url = api_url.rstrip("/")

    async def search_ocr(
        self,
        minutes: int = 30,
        limit: int = 50,
        query: str | None = None,
    ) -> list[OCRFrame]:
        """Fetch OCR text from the last N minutes."""
        end = datetime.now(UTC)
        start = end - timedelta(minutes=minutes)

        params: dict[str, Any] = {
            "content_type": "ocr",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "limit": limit,
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
            return []

        frames: list[OCRFrame] = []
        for item in data.get("data", []):
            content = item.get("content", {})
            frames.append(OCRFrame(
                text=content.get("text", ""),
                app_name=content.get("app_name", ""),
                window_name=content.get("window_name", ""),
                timestamp=item.get("timestamp", ""),
            ))
        return frames

    @staticmethod
    def deduplicate(frames: list[OCRFrame], threshold: float = 0.8) -> list[OCRFrame]:
        """Remove consecutive frames with similar OCR text."""
        if not frames:
            return []

        unique: list[OCRFrame] = [frames[0]]
        for frame in frames[1:]:
            last_text = unique[-1].text
            if not last_text or not frame.text:
                unique.append(frame)
                continue
            # Simple similarity: shared character ratio
            shorter = min(len(last_text), len(frame.text))
            if shorter == 0:
                unique.append(frame)
                continue
            common = sum(
                a == b
                for a, b in zip(last_text[:shorter], frame.text[:shorter], strict=True)
            )
            similarity = common / shorter
            if similarity < threshold:
                unique.append(frame)
        return unique

    @staticmethod
    def format_for_llm(frames: list[OCRFrame], max_chars: int = 200) -> str:
        """Format frames into a compact text summary for LLM consumption."""
        lines: list[str] = []
        for f in frames:
            lines.append(f"[{f.timestamp}] {f.app_name} | {f.window_name}")
            if f.text:
                lines.append(f"  内容: {f.text[:max_chars]}")
        return "\n".join(lines)

    async def health_check(self) -> bool:
        """Check if Screenpipe is running."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
