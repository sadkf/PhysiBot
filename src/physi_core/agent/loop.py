"""Agent Loop — the core Think→Act→Check→Repeat cycle."""

from __future__ import annotations

import logging
from typing import Any

from physi_core.agent.tools import ToolController
from physi_core.llm.adapter import LLMClient
from physi_core.llm.response import LLMResponse
from physi_core.observability import emit_event

logger = logging.getLogger(__name__)

# Maximum number of tool call rounds before forcing a text response
MAX_TOOL_ROUNDS = 10


class AgentLoop:
    """Core agent loop: sends messages to LLM, executes tool calls, repeats until text response."""

    def __init__(
        self,
        llm_client: LLMClient,
        tool_controller: ToolController,
        system_prompt: str = "",
    ) -> None:
        self._llm = llm_client
        self._tools = tool_controller
        self._system = system_prompt

    async def run(
        self,
        user_input: str,
        conversation: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> AgentResult:
        """Run the agent loop for a single user turn.

        Args:
            user_input: The user's message text.
            conversation: Optional prior conversation context.
            system: Override system prompt for this turn (e.g. refreshed memory).

        Returns:
            AgentResult with the final text response and execution trace.
        """
        messages = list(conversation or [])
        messages.append({"role": "user", "content": user_input})

        active_system = system if system is not None else self._system
        tool_schemas = self._tools.get_all_schemas() or None
        trace: list[TraceStep] = []

        for round_idx in range(MAX_TOOL_ROUNDS):
            logger.info("Agent round %d", round_idx + 1)
            emit_event("agent.round.start", round=round_idx + 1, max_rounds=MAX_TOOL_ROUNDS)

            response = await self._llm.chat(
                messages=messages,
                system=active_system,
                tools=tool_schemas,
            )

            trace.append(TraceStep(
                round_num=round_idx + 1,
                response=response,
            ))

            # If pure text response → done
            if not response.has_tool_calls():
                emit_event(
                    "agent.round.final",
                    round=round_idx + 1,
                    text_preview=(response.text or "")[:300],
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
                return AgentResult(
                    text=response.text or "",
                    thinking=response.thinking,
                    trace=trace,
                    total_usage=_sum_usage(trace),
                )

            # Execute tool calls
            for tc in response.tool_calls:
                emit_event("agent.tool.requested", round=round_idx + 1, tool=tc.name, arguments=tc.arguments)
                # Permission check
                if self._tools.is_denied(tc.name):
                    tool_output = f"Tool '{tc.name}' is denied by security policy."
                elif self._tools.is_dangerous(tc.name):
                    tool_output = f"Tool '{tc.name}' requires user confirmation. [PENDING]"
                else:
                    result = await self._tools.execute(tc.name, tc.arguments)
                    tool_output = result.output if result.success else f"Error: {result.error}"
                emit_event(
                    "agent.tool.result",
                    round=round_idx + 1,
                    tool=tc.name,
                    output_preview=tool_output[:500],
                    pending=self._tools.is_dangerous(tc.name),
                )

                # Add tool result to conversation
                messages.append({
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    }],
                })
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": tool_output,
                    }],
                })

        # Hit max rounds
        logger.warning("Agent loop hit MAX_TOOL_ROUNDS (%d)", MAX_TOOL_ROUNDS)
        emit_event("agent.round.max_reached", max_rounds=MAX_TOOL_ROUNDS)
        return AgentResult(
            text="抱歉，我处理这个请求花了太长时间，请重新问我。",
            trace=trace,
            total_usage=_sum_usage(trace),
        )

    async def run_stream(
        self,
        user_input: str,
        conversation: list[dict[str, Any]] | None = None,
    ):
        """Streaming version of the agent loop."""
        from physi_core.llm.response import StreamEventType
        import json
        
        messages = list(conversation or [])
        messages.append({"role": "user", "content": user_input})
        tool_schemas = self._tools.get_all_schemas() or None
        
        for round_idx in range(MAX_TOOL_ROUNDS):
            # We will stream the current turn
            # Accumulate text and thinking as we stream
            full_text = ""
            full_thinking = ""
            current_tool_id = ""
            current_tool_name = ""
            current_tool_args = ""
            
            tool_calls = []
            
            async for chunk in self._llm.chat_stream(
                messages=messages,
                system=self._system,
                tools=tool_schemas,
            ):
                yield chunk
                if chunk.event == StreamEventType.TEXT:
                    full_text += chunk.content
                elif chunk.event == StreamEventType.THINKING:
                    full_thinking += chunk.content
                elif chunk.event == StreamEventType.TOOL_START:
                    current_tool_name = chunk.content
                    current_tool_id = chunk.id or ""
                    current_tool_args = ""
                elif chunk.event == StreamEventType.TOOL_ARG_DELTA:
                    current_tool_args += chunk.content
            
            # Assuming Anthropic stream parsing finished, we check if any tools were called
            if current_tool_name:
                try:
                    args = json.loads(current_tool_args or "{}")
                except ValueError:
                    args = {}
                from physi_core.llm.response import ToolCall
                tool_calls.append(ToolCall(id=current_tool_id, name=current_tool_name, arguments=args))
                
            if not tool_calls:
                return  # Stream ends here (yielded all text)
                
            # If there are tools, execute them and continue loop
            for tc in tool_calls:
                if self._tools.is_denied(tc.name):
                    tool_output = f"Tool '{tc.name}' is denied by security policy."
                elif self._tools.is_dangerous(tc.name):
                    tool_output = f"Tool '{tc.name}' requires user confirmation. [PENDING]"
                else:
                    result = await self._tools.execute(tc.name, tc.arguments)
                    tool_output = result.output if result.success else f"Error: {result.error}"

                # Append assistant tool use request and user tool result manually into messages
                messages.append({
                    "role": "assistant",
                    "content": [{
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    }],
                })
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": tool_output,
                    }],
                })
                
        # MAX ROUNDS
        from physi_core.llm.response import StreamChunk, StreamEventType
        yield StreamChunk(StreamEventType.TEXT, "抱歉，我处理这个请求花了太长时间，请重新问我。")


class TraceStep:
    """One round of the agent loop."""

    def __init__(self, round_num: int, response: LLMResponse) -> None:
        self.round_num = round_num
        self.response = response


class AgentResult:
    """Final result of an agent loop execution."""

    def __init__(
        self,
        text: str,
        trace: list[TraceStep],
        total_usage: dict[str, int],
        thinking: str | None = None,
    ) -> None:
        self.text = text
        self.thinking = thinking
        self.trace = trace
        self.total_usage = total_usage

    @property
    def rounds(self) -> int:
        return len(self.trace)


def _sum_usage(trace: list[TraceStep]) -> dict[str, int]:
    total_in = sum(s.response.usage.input_tokens for s in trace)
    total_out = sum(s.response.usage.output_tokens for s in trace)
    return {"input_tokens": total_in, "output_tokens": total_out}
