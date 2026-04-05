"""Unified LLM client adapter — abstracts away provider differences."""

from __future__ import annotations

import json
import logging
from typing import Any

from physi_core.config.settings import LLMConfig
from physi_core.llm.providers import resolve_provider
from physi_core.llm.response import LLMResponse, TokenUsage, ToolCall

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified async LLM client supporting Anthropic SDK and OpenAI SDK providers."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._sdk_type, self._base_url = resolve_provider(config)
        self._client: Any = None

    def _ensure_client(self) -> None:
        """Lazy-init the SDK client."""
        if self._client is not None:
            return

        if self._sdk_type == "anthropic":
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=self._config.api_key,
                base_url=self._base_url,
            )
        else:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._config.api_key,
                base_url=self._base_url,
            )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat request and return a standardized response."""
        self._ensure_client()

        if self._sdk_type == "anthropic":
            return await self._chat_anthropic(messages, system, tools, max_tokens)
        else:
            return await self._chat_openai(messages, system, tools, max_tokens)

    async def _chat_anthropic(
        self,
        messages: list[dict[str, Any]],
        system: str,
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
    ) -> LLMResponse:
        """Call Anthropic-compatible API (MiniMax / Anthropic)."""
        import asyncio

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        # Run sync client in thread to avoid blocking
        response = await asyncio.to_thread(self._client.messages.create, **kwargs)

        # Parse response
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

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            thinking="\n".join(thinking_parts) if thinking_parts else None,
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
    ) -> LLMResponse:
        """Call OpenAI-compatible API."""
        import asyncio

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": max_tokens,
            "messages": full_messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await asyncio.to_thread(
            self._client.chat.completions.create, **kwargs
        )

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
