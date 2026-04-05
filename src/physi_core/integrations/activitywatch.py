"""ActivityWatch API client — application usage statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

logger = logging.getLogger(__name__)


@dataclass
class AppUsage:
    """Application usage entry."""

    app: str
    title: str
    duration_seconds: float

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60


class ActivityWatchClient:
    """Client for the local ActivityWatch REST API (http://localhost:5600)."""

    def __init__(self, api_url: str = "http://localhost:5600") -> None:
        self._base_url = api_url.rstrip("/")

    async def get_app_usage(self, minutes: int = 30) -> list[AppUsage]:
        """Get application usage stats for the last N minutes, sorted by duration."""
        end = datetime.now(UTC)
        start = end - timedelta(minutes=minutes)

        # AW query: merge by app, filter AFK, sort by duration
        hostname = await self._get_hostname()
        if not hostname:
            return []

        query = [
            f'events = query_bucket("aw-watcher-window_{hostname}");',
            f'events = filter_period_intersect(events, query_bucket("aw-watcher-afk_{hostname}"));',
            'RETURN = sort_by_duration(merge_events_by_keys(events, ["app"]));',
        ]

        timeperiods = [f"{start.isoformat()}/{end.isoformat()}"]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/0/query/",
                    json={"query": query, "timeperiods": timeperiods},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("ActivityWatch API error: %s", e)
            return []

        results: list[AppUsage] = []
        for event in data[0] if data else []:
            event_data = event.get("data", {})
            results.append(AppUsage(
                app=event_data.get("app", "unknown"),
                title=event_data.get("title", ""),
                duration_seconds=event.get("duration", 0),
            ))
        return results

    async def _get_hostname(self) -> str | None:
        """Get the AW server hostname for bucket naming."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/0/info")
                resp.raise_for_status()
                return resp.json().get("hostname", "")
        except httpx.HTTPError:
            logger.error("Cannot reach ActivityWatch")
            return None

    @staticmethod
    def format_for_llm(usages: list[AppUsage]) -> str:
        """Format app usage into compact text for LLM."""
        if not usages:
            return "无应用活动数据"
        lines = ["应用使用统计:"]
        for u in usages:
            lines.append(f"- {u.app}: {u.duration_minutes:.0f} 分钟")
        return "\n".join(lines)

    async def health_check(self) -> bool:
        """Check if ActivityWatch is running."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/api/0/info")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
