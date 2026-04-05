"""NapCatQQ OneBot v11 WebSocket client — QQ private chat interface."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class QQClient:
    """WebSocket client for NapCatQQ (OneBot v11 protocol).

    Only handles private messages from the configured owner QQ.
    """

    def __init__(self, ws_url: str, owner_qq: str) -> None:
        self._ws_url = ws_url
        self._owner_qq = owner_qq
        self._handler: MessageHandler | None = None
        self._running = False

    def on_private_message(self, handler: MessageHandler) -> None:
        """Register a handler for incoming private messages."""
        self._handler = handler

    async def start(self) -> None:
        """Start the WebSocket listener loop."""
        try:
            import websockets
        except ImportError:
            logger.error("websockets package not installed. Run: uv add websockets")
            return

        self._running = True
        while self._running:
            try:
                async with websockets.connect(self._ws_url) as ws:  # type: ignore[attr-defined]
                    logger.info("Connected to NapCat at %s", self._ws_url)
                    async for raw in ws:
                        try:
                            event = json.loads(raw)
                            await self._dispatch(event)
                        except json.JSONDecodeError:
                            logger.warning("Invalid JSON from WebSocket")
            except Exception as e:
                if self._running:
                    logger.error("WebSocket disconnected: %s. Reconnecting in 5s...", e)
                    await asyncio.sleep(5)

    async def stop(self) -> None:
        """Stop the listener loop."""
        self._running = False

    async def _dispatch(self, event: dict[str, Any]) -> None:
        """Filter and dispatch events."""
        # Only message events
        if event.get("post_type") != "message":
            return

        # Only private messages
        if event.get("message_type") != "private":
            return

        # Only from owner
        if str(event.get("user_id", "")) != self._owner_qq:
            return

        if self._handler:
            await self._handler(event)

    async def send_private_message(self, message: str, user_id: str | None = None) -> bool:
        """Send a private message via NapCat HTTP API."""
        target = user_id or self._owner_qq
        # NapCat exposes HTTP API on the same host, port 3000 typically
        http_url = self._ws_url.replace("ws://", "http://").replace("wss://", "https://")
        # Replace WebSocket port with HTTP API port
        http_base = http_url.rsplit(":", 1)[0] + ":3000"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{http_base}/send_private_msg",
                    json={"user_id": int(target), "message": message},
                )
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error("Failed to send QQ message: %s", e)
            return False

    @staticmethod
    def extract_text(event: dict[str, Any]) -> str:
        """Extract plain text from a OneBot message event."""
        message = event.get("message", [])
        if isinstance(message, str):
            return message
        parts: list[str] = []
        for seg in message:
            if isinstance(seg, dict) and seg.get("type") == "text":
                parts.append(seg.get("data", {}).get("text", ""))
        return "".join(parts)
