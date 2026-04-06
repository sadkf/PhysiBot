"""NapCatQQ OneBot v11 Reverse WebSocket server — QQ private chat interface."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class QQClient:
    """Reverse WebSocket server (Bot as Server, NapCat as Client).

    Standard OneBot v11 protocol with Echo Cancellation.
    """

    def __init__(
        self,
        ws_url: str,
        talk_qq: str | list[str] | None = None,
        *,
        owner_qq: str | list[str] | None = None,
    ) -> None:
        self._ws_url = ws_url
        if talk_qq is None:
            talk_qq = owner_qq or []
        # Normalise to a set of strings for O(1) lookup
        if isinstance(talk_qq, str):
            self._talk_qqs: set[str] = {talk_qq} if talk_qq else set()
        else:
            self._talk_qqs = {str(q) for q in talk_qq if str(q).strip()}
        self._handler: MessageHandler | None = None
        self._running = False
        self._connections: set[Any] = set()
        self._sent_cache: list[str] = []  # Last few messages to avoid loops
        self._max_cache = 5

    def on_private_message(self, handler: MessageHandler) -> None:
        """Register a handler for incoming private messages."""
        self._handler = handler

    async def start(self) -> None:
        """Start the WebSocket server."""
        try:
            import websockets
        except ImportError:
            logger.error("websockets package not installed. Run: uv add websockets")
            return

        # Default to 0.0.0.0:3001 and parse configured ws_url safely.
        host = "0.0.0.0"
        port = 3001
        try:
            parsed = urlparse(self._ws_url)
            if parsed.port:
                port = parsed.port
            if parsed.hostname and parsed.hostname not in {"localhost"}:
                host = parsed.hostname
        except ValueError:
            logger.warning("Invalid ws_url '%s', fallback to %s:%d", self._ws_url, host, port)

        self._running = True
        logger.info("Reverse WebSocket server listening on %s:%d", host, port)
        
        async with websockets.serve(self._handle_connection, host, port):  # type: ignore[attr-defined]
            while self._running:
                await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the server."""
        self._running = False

    async def _handle_connection(self, ws: Any) -> None:
        """Handle individual incoming connection from NapCat."""
        addr = getattr(ws, "remote_address", "?")
        logger.info("NapCat connected from %s", addr)
        self._connections.add(ws)
        try:
            async for raw in ws:
                try:
                    event = json.loads(raw)
                    await self._dispatch(event)
                except json.JSONDecodeError:
                    logger.warning("Non-JSON frame from NapCat: %r", raw[:100])
                except Exception:
                    logger.exception("Error dispatching NapCat event")
        except Exception as exc:
            logger.warning("NapCat connection closed: %s", exc)
        finally:
            self._connections.discard(ws)
            logger.info("NapCat disconnected (%d remaining)", len(self._connections))

    async def _dispatch(self, event: dict[str, Any]) -> None:
        """Filter and dispatch events."""
        post_type = event.get("post_type")
        msg_type = event.get("message_type")
        user_id = self.extract_user_id(event)

        # Debug: log every incoming event so we can inspect the structure
        logger.debug(
            "EVENT post_type=%s msg_type=%s user_id=%s self_id=%s target_id=%s text=%r",
            post_type, msg_type, user_id,
            event.get("self_id"), event.get("target_id"),
            self.extract_text(event)[:40],
        )

        if post_type not in {"message", "message_sent"}:
            return

        # Only private messages from allowed talk_qq peers
        if msg_type != "private":
            return
        if self._talk_qqs and user_id not in self._talk_qqs:
            logger.debug("FILTERED: user_id=%s not in talk_qqs=%s", user_id, self._talk_qqs)
            return

        # Echo Cancellation: Don't process what we just sent
        text = self.extract_text(event).strip()
        if post_type == "message_sent":
            if text in self._sent_cache:
                try:
                    self._sent_cache.remove(text)
                except ValueError:
                    pass
                return

        logger.info("Message from %s: %s...", user_id, text[:25])
        if self._handler:
            await self._handler(event)

    async def send_private_message(self, message: str, user_id: str | None = None) -> bool:
        """Send a private message via NapCat HTTP API (Fallback to 3000)."""
        default_target = next(iter(self._talk_qqs), None)
        target = user_id or default_target
        if not target:
            logger.error("No target QQ set for outgoing private message")
            return False
        
        # Use HTTP for sending as it's stateful and robust
        host = "127.0.0.1"
        try:
            parsed = urlparse(self._ws_url)
            if parsed.hostname:
                host = parsed.hostname
        except ValueError:
            pass
        if host in {"localhost", "0.0.0.0"}:
            host = "127.0.0.1"

        http_base = f"http://{host}:3000"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{http_base}/send_private_msg",
                    json={"user_id": int(target), "message": message},
                )
                resp.raise_for_status()
                
                # Update cache to avoid echo loops
                self._sent_cache.append(message.strip())
                if len(self._sent_cache) > self._max_cache:
                    self._sent_cache.pop(0)
                    
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

    @staticmethod
    def extract_user_id(event: dict[str, Any]) -> str:
        """Extract private chat peer user_id from OneBot event variants."""
        post_type = event.get("post_type")
        user_id = event.get("target_id") if post_type == "message_sent" else event.get("user_id")
        if user_id is None and isinstance(event.get("sender"), dict):
            user_id = event["sender"].get("user_id")
        if user_id is None and post_type == "message_sent":
            user_id = event.get("user_id")
        return str(user_id or "")
