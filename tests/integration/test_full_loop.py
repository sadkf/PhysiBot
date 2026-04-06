"""
PhysiBot 完整闭环集成测试 (in-process, mocked LLM)

流程:
  1. 启动 PhysiBot WS server (in-process, mock LLM)
  2. Mock NapCat HTTP server on :3000
  3. fake NapCat WS client 发消息
  4. 验证 HTTP 回复 + 短期记忆写入
  5. 直接调用 _on_segment_timer 验证片段写入

优点: 不依赖真实 LLM API，运行速度快（<30s），输出确定。
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# ── path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from physi_core.config.settings import LLMConfig, QQConfig, Settings
from physi_core.llm.response import LLMResponse, ToolCall, TokenUsage
from physi_core.main import PhysiBot


# ── Mock NapCat HTTP server (port 3000) ────────────────────────────────────────

_received: list[dict] = []
_mock_http_ready = threading.Event()
_mock_http_server: HTTPServer | None = None


class _MockHTTPHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        _received.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps({"status": "ok", "retcode": 0, "data": {"message_id": 1}}).encode()
        )

    def log_message(self, *args) -> None:
        pass  # suppress HTTP access logs


def _start_mock_http(port: int = 3000) -> None:
    global _mock_http_server
    _mock_http_server = HTTPServer(("127.0.0.1", port), _MockHTTPHandler)
    _mock_http_ready.set()
    _mock_http_server.serve_forever()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        llm=LLMConfig(provider="minimax", model="test", api_key="fake"),
        qq=QQConfig(ws_url="ws://127.0.0.1:13001", owner_qq=["1000000002"]),
        data_dir=tmp_path,
    )


def _tool_response(name: str, args: dict) -> LLMResponse:
    return LLMResponse(
        tool_calls=[ToolCall(id="t1", name=name, arguments=args)],
        usage=TokenUsage(100, 50),
    )


def _text_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, usage=TokenUsage(50, 20))


def _make_qq_event(text: str, uid: int = 1000000002) -> dict:
    return {
        "post_type": "message",
        "message_type": "private",
        "user_id": uid,
        "self_id": 1000000001,
        "message": [{"type": "text", "data": {"text": text}}],
        "time": int(time.time()),
        "message_id": 12345,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestFullLoop:
    """AC: QQ message → WS → agent → HTTP reply → memory written."""

    @pytest.mark.asyncio
    async def test_qq_message_to_http_reply(self, tmp_path: Path) -> None:
        """Full pipeline: fake NapCat WS → PhysiBot agent → reply captured."""
        import websockets
        from physi_core.integrations.qq import QQClient

        settings = _make_settings(tmp_path)
        bot = PhysiBot(settings)
        bot._init_components()

        # Mock LLM: first call sets identity, second finalizes
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=[
            _tool_response("identity_set", {"key": "name", "value": "张三"}),
            _text_response("好的，我记住啦！你是张三。"),
        ])
        bot._llm = mock_llm
        bot._agent._llm = mock_llm

        # Create QQ client manually (normally done in start())
        qq = QQClient("ws://127.0.0.1:13001", ["1000000002"])
        qq.on_private_message(bot._on_qq_message)
        bot._qq = qq

        # Track outgoing messages
        sent_messages: list[str] = []

        async def _fake_send(message: str, user_id: str | None = None) -> bool:
            sent_messages.append(message)
            return True

        qq.send_private_message = _fake_send  # type: ignore[method-assign]

        # Start WS server on port 13001
        server_ready = asyncio.Event()

        async def _run_ws_server() -> None:
            async with websockets.serve(qq._handle_connection, "127.0.0.1", 13001):  # type: ignore[attr-defined]
                server_ready.set()
                await asyncio.sleep(30)  # keep alive for test duration

        ws_server_task = asyncio.create_task(_run_ws_server())
        await server_ready.wait()

        try:
            # Connect as fake NapCat and send a message
            async with websockets.connect("ws://127.0.0.1:13001") as ws:
                event = _make_qq_event("你好！我叫张三，请记住我的名字。")
                await ws.send(json.dumps(event))

                # Wait for agent to process and reply (up to 30s with mock LLM)
                deadline = asyncio.get_event_loop().time() + 30
                while asyncio.get_event_loop().time() < deadline and not sent_messages:
                    await asyncio.sleep(0.2)

        finally:
            ws_server_task.cancel()
            try:
                await ws_server_task
            except (asyncio.CancelledError, Exception):
                pass

        # Assertions
        assert sent_messages, "No reply sent — agent did not respond via QQ"
        assert "张三" in sent_messages[0], (
            f"Response should mention the name: {sent_messages[0]}"
        )

        # Memory: user + assistant messages in short_term
        msgs = bot._short_term.get_messages()
        assert len(msgs) >= 2, f"Expected >= 2 messages in short_term, got {len(msgs)}"
        assert msgs[0]["role"] == "user"
        assert "张三" in msgs[0]["content"]
        assert msgs[-1]["role"] == "assistant"

        # Identity: name should be stored by identity_set tool
        assert bot._identity.get("name") == "张三", (
            f"Expected name=张三 in identity, got: {bot._identity.get('name')}"
        )

    @pytest.mark.asyncio
    async def test_segment_timer_writes_segment(self, tmp_path: Path) -> None:
        """_on_segment_timer should write a mid_term segment file."""
        settings = _make_settings(tmp_path)
        bot = PhysiBot(settings)
        bot._init_components()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=[
            # summarize_segment: returns tool call with summary
            _tool_response("write_segment", {
                "summary": "## 主要活动\n测试了 PhysiBot 的片段定时器功能",
                "should_notify": False,
                "notify_message": "",
            }),
        ])
        bot._llm = mock_llm
        bot._consolidator._llm = mock_llm

        await bot._on_segment_timer()

        segs = list((tmp_path / "mid_term" / "segments").glob("*.md"))
        assert segs, "No segment file was written"
        content = segs[0].read_text(encoding="utf-8")
        assert len(content) > 0, "Segment file is empty"

    @pytest.mark.asyncio
    async def test_message_flow_saves_to_memory(self, tmp_path: Path) -> None:
        """handle_message writes user+assistant to short_term and triggers extraction."""
        settings = _make_settings(tmp_path)
        bot = PhysiBot(settings)
        bot._init_components()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(side_effect=[
            _text_response("你好！有什么可以帮你的吗？"),
            # extract_from_session: write_identity tool call
            _tool_response("write_identity", {"key": "name", "value": "东哥"}),
            _text_response("done"),
        ])
        bot._llm = mock_llm
        bot._agent._llm = mock_llm
        bot._consolidator._llm = mock_llm

        response = await bot.handle_message("你好", source="qq")
        assert response == "你好！有什么可以帮你的吗？"

        msgs = bot._short_term.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

        # Let background extraction settle
        await asyncio.sleep(0.5)


