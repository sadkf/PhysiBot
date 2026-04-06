"""Unified LLM client adapter — abstracts away provider differences.

Full I/O logging: every chat() call writes one request record and one response
record to physi-data/logs/llm_calls.jsonl, keyed by a per-call request_id that
is also embedded in the Trace event so the HTML monitor can cross-reference.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from physi_core.config.settings import LLMConfig
from physi_core.llm.providers import resolve_provider
from physi_core.llm.response import LLMResponse, TokenUsage, ToolCall
from physi_core.observability import emit_event, get_observability

logger = logging.getLogger(__name__)

# Module-level file handle (opened once, stays open for the process lifetime)
_llm_log_path: Path | None = None
_llm_log_file: Any = None


def _init_llm_log(data_dir: Path) -> None:
    """Open the llm_calls.jsonl log file. Called once by LLMClient on first use."""
    global _llm_log_path, _llm_log_file
    if _llm_log_file is not None:
        return
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _llm_log_path = log_dir / "llm_calls.jsonl"
    try:
        _llm_log_file = _llm_log_path.open("a", encoding="utf-8", buffering=1)
        logger.info("LLM full I/O log: %s", _llm_log_path)
    except Exception as e:
        logger.warning("Cannot open llm_calls.jsonl: %s", e)


def _append_llm_log(record: dict[str, Any]) -> None:
    if _llm_log_file is None:
        return
    try:
        _llm_log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("llm_calls.jsonl write error: %s", e)


def _current_trace_id() -> str | None:
    """Read the active trace id from the observability context var."""
    obs = get_observability()
    if obs is None:
        return None
    from physi_core.observability import _current_trace_id as _ctx
    return _ctx.get()


class LLMClient:
    """Unified async LLM client supporting Anthropic SDK and OpenAI SDK providers."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._sdk_type, self._base_url = resolve_provider(config)
        self._client: Any = None
        self._data_dir: Path | None = None

    def set_data_dir(self, data_dir: Path) -> None:
        """Configure the data directory for llm_calls.jsonl logging."""
        self._data_dir = data_dir
        _init_llm_log(data_dir)

    def _ensure_client(self) -> None:
        """Initialize the appropriate SDK client."""
        if self._client is not None:
            return

        if self._sdk_type == "anthropic":
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self._config.api_key,
                base_url=self._base_url,
            )
        else:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._config.api_key,
                base_url=self._base_url,
            )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Send a chat request and return a standardized response.

        Writes full request + response to llm_calls.jsonl (keyed by request_id).
        """
        self._ensure_client()

        request_id = uuid.uuid4().hex[:12]
        trace_id = _current_trace_id()
        ts_req = time.strftime("%Y-%m-%dT%H:%M:%S")

        # ── Log full request ─────────────────────────────────────────────────
        _append_llm_log({
            "ts": ts_req,
            "request_id": request_id,
            "trace_id": trace_id,
            "direction": "request",
            "provider_sdk": self._sdk_type,
            "model": self._config.model,
            "system": system,
            "messages": messages,
            "tools": tools or [],
            "tool_choice": tool_choice,
            "max_tokens": max_tokens,
        })

        start_t0 = time.perf_counter()

        if self._sdk_type == "anthropic":
            resp = await self._chat_anthropic(messages, system, tools, max_tokens, tool_choice)
        else:
            resp = await self._chat_openai(messages, system, tools, max_tokens, tool_choice)

        latency_ms = int((time.perf_counter() - start_t0) * 1000)

        # ── Log full response ────────────────────────────────────────────────
        _append_llm_log({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "request_id": request_id,
            "trace_id": trace_id,
            "direction": "response",
            "text": resp.text,
            "thinking": resp.thinking,
            "tool_calls": [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in resp.tool_calls
            ],
            "usage": {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
            },
            "latency_ms": latency_ms,
        })

        emit_event(
            "llm_call",
            request_id=request_id,
            provider_sdk=self._sdk_type,
            model=self._config.model,
            system_len=len(system or ""),
            messages_count=len(messages),
            last_user_preview=(
                str((messages[-1] or {}).get("content", ""))[:400] if messages else ""
            ),
            tools=[t.get("function", {}).get("name", "") for t in (tools or [])],
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            tool_calls=[tc.name for tc in resp.tool_calls],
            text_preview=(resp.text or "")[:400],
            latency_ms=latency_ms,
        )
        return resp

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ):
        """Stream a chat request yielding StreamChunk events."""
        self._ensure_client()

        if self._sdk_type == "anthropic":
            from physi_core.llm.response import StreamChunk, StreamEventType

            kwargs: dict[str, Any] = {
                "model": self._config.model,
                "max_tokens": max_tokens,
                "messages": messages,
                "system": system,
            }
            if tools:
                kwargs["tools"] = self._convert_tools_anthropic(tools)

            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        if event.content_block.type == "tool_use":
                            yield StreamChunk(StreamEventType.TOOL_START, event.content_block.name, id=event.content_block.id)
                    elif event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield StreamChunk(StreamEventType.TEXT, event.delta.text)
                        elif getattr(event.delta, "type", "") == "thinking_delta":
                            yield StreamChunk(StreamEventType.THINKING, event.delta.thinking)
                        elif event.delta.type == "input_json_delta":
                            yield StreamChunk(StreamEventType.TOOL_ARG_DELTA, event.delta.partial_json)
        else:
            resp = await self._chat_openai(messages, system, tools, max_tokens)
            if resp.text:
                from physi_core.llm.response import StreamChunk, StreamEventType
                yield StreamChunk(StreamEventType.TEXT, resp.text)

    @staticmethod
    def _convert_tools_anthropic(
        tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Convert OpenAI-style tool defs to Anthropic-native format.

        OpenAI:    {"type":"function","function":{"name":...,"parameters":...}}
        Anthropic: {"name":...,"description":...,"input_schema":...}
        """
        result = []
        for tool in tools:
            if "function" in tool:
                fn = tool["function"]
                result.append({
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object"}),
                })
            elif "name" in tool:
                result.append(tool)
            else:
                result.append(tool)
        return result

    async def _chat_anthropic(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Call Anthropic-compatible API (MiniMax / Anthropic)."""
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools_anthropic(tools)
            if tool_choice:
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice}
            else:
                kwargs["tool_choice"] = {"type": "auto"}

        response = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "thinking":
                    thinking_parts.append(block.thinking)
                elif block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        )
                    )

        text = "\n".join(text_parts) if text_parts else None
        thinking = "\n".join(thinking_parts) if thinking_parts else None

        if text is None and thinking and not tool_calls:
            logger.debug("No text block found, falling back to thinking")
            text = thinking

        return LLMResponse(
            text=text,
            thinking=thinking,
            tool_calls=tool_calls,
            usage=TokenUsage(
                input_tokens=getattr(response.usage, "input_tokens", 0),
                output_tokens=getattr(response.usage, "output_tokens", 0),
            ),
        )

    async def _chat_openai(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """Call OpenAI-compatible API."""
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "messages": full_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = {"type": "function", "function": {"name": tool_choice}}

        response = await self._client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        msg = choice.message

        tool_calls: list[ToolCall] = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments)
                        if tc.function.arguments
                        else {},
                    )
                )

        return LLMResponse(
            text=msg.content,
            tool_calls=tool_calls,
            usage=TokenUsage(
                input_tokens=getattr(response.usage, "prompt_tokens", 0),
                output_tokens=getattr(response.usage, "completion_tokens", 0),
            ),
        )
