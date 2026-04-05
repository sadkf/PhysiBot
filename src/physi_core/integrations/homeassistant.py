"""Home Assistant REST API client — IoT device control."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DeviceState:
    """State of an HA entity."""

    entity_id: str
    state: str
    friendly_name: str
    attributes: dict[str, Any]


class HomeAssistantClient:
    """Client for the Home Assistant REST API."""

    def __init__(self, url: str, token: str) -> None:
        self._base_url = url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def get_state(self, entity_id: str) -> DeviceState | None:
        """Get the current state of an entity."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/states/{entity_id}",
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return DeviceState(
                    entity_id=data["entity_id"],
                    state=data["state"],
                    friendly_name=data.get("attributes", {}).get("friendly_name", ""),
                    attributes=data.get("attributes", {}),
                )
        except httpx.HTTPError as e:
            logger.error("HA get_state error for %s: %s", entity_id, e)
            return None

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        **kwargs: Any,
    ) -> bool:
        """Call an HA service (e.g., light.turn_on)."""
        payload: dict[str, Any] = {"entity_id": entity_id, **kwargs}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/services/{domain}/{service}",
                    headers=self._headers,
                    json=payload,
                )
                resp.raise_for_status()
                return True
        except httpx.HTTPError as e:
            logger.error("HA call_service error: %s", e)
            return False

    async def turn_on(self, entity_id: str) -> bool:
        """Turn on a device."""
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "turn_on", entity_id)

    async def turn_off(self, entity_id: str) -> bool:
        """Turn off a device."""
        domain = entity_id.split(".")[0]
        return await self.call_service(domain, "turn_off", entity_id)

    async def list_entities(self, domain: str | None = None) -> list[DeviceState]:
        """List all entities, optionally filtered by domain."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/states",
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            logger.error("HA list_entities error: %s", e)
            return []

        entities: list[DeviceState] = []
        for item in data:
            eid = item["entity_id"]
            if domain and not eid.startswith(f"{domain}."):
                continue
            entities.append(DeviceState(
                entity_id=eid,
                state=item["state"],
                friendly_name=item.get("attributes", {}).get("friendly_name", ""),
                attributes=item.get("attributes", {}),
            ))
        return entities

    async def health_check(self) -> bool:
        """Check if Home Assistant is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/",
                    headers=self._headers,
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
