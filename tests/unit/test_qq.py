"""Unit tests for integrations/qq.py."""

from __future__ import annotations

import pytest

from physi_core.integrations.qq import QQClient


class TestQQMessageFilter:
    """AC-20: Only handle private messages from bound owner QQ."""

    @pytest.fixture
    def client(self) -> QQClient:
        return QQClient(ws_url="ws://localhost:3001", owner_qq="123456")

    @pytest.mark.asyncio
    async def test_dispatch_private_from_owner(self, client: QQClient) -> None:
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        client.on_private_message(handler)

        event = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 123456,
            "message": [{"type": "text", "data": {"text": "你好"}}],
        }
        await client._dispatch(event)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_ignores_group_message(self, client: QQClient) -> None:
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        client.on_private_message(handler)

        event = {
            "post_type": "message",
            "message_type": "group",
            "user_id": 123456,
            "message": "group msg",
        }
        await client._dispatch(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_ignores_other_user(self, client: QQClient) -> None:
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        client.on_private_message(handler)

        event = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 999999,
            "message": "stranger",
        }
        await client._dispatch(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_ignores_non_message_event(self, client: QQClient) -> None:
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        client.on_private_message(handler)

        event = {"post_type": "notice", "notice_type": "friend_add"}
        await client._dispatch(event)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_no_handler_registered(self, client: QQClient) -> None:
        """Should not crash if no handler registered."""
        event = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 123456,
            "message": "hi",
        }
        await client._dispatch(event)  # Should not raise

    @pytest.mark.asyncio
    async def test_dispatch_private_with_sender_user_id(self, client: QQClient) -> None:
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        client.on_private_message(handler)

        event = {
            "post_type": "message",
            "message_type": "private",
            "sender": {"user_id": 123456},
            "message": "hello",
        }
        await client._dispatch(event)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_dispatch_message_sent_with_user_id_fallback(self, client: QQClient) -> None:
        received: list[dict] = []

        async def handler(event: dict) -> None:
            received.append(event)

        client.on_private_message(handler)

        event = {
            "post_type": "message_sent",
            "message_type": "private",
            "user_id": 123456,
            "message": "hello",
        }
        await client._dispatch(event)
        assert len(received) == 1


class TestQQTextExtract:
    def test_extract_text_from_segments(self) -> None:
        event = {
            "message": [
                {"type": "text", "data": {"text": "你好"}},
                {"type": "image", "data": {"url": "..."}},
                {"type": "text", "data": {"text": "世界"}},
            ],
        }
        assert QQClient.extract_text(event) == "你好世界"

    def test_extract_text_from_string(self) -> None:
        event = {"message": "纯文本消息"}
        assert QQClient.extract_text(event) == "纯文本消息"

    def test_extract_empty_message(self) -> None:
        assert QQClient.extract_text({}) == ""
        assert QQClient.extract_text({"message": []}) == ""


class TestQQUserIdExtract:
    def test_extract_user_id_from_message(self) -> None:
        event = {"post_type": "message", "user_id": 123456}
        assert QQClient.extract_user_id(event) == "123456"

    def test_extract_user_id_from_sender(self) -> None:
        event = {"post_type": "message", "sender": {"user_id": 123456}}
        assert QQClient.extract_user_id(event) == "123456"

    def test_extract_user_id_from_message_sent_target(self) -> None:
        event = {"post_type": "message_sent", "target_id": 123456}
        assert QQClient.extract_user_id(event) == "123456"
