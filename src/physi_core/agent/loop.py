"""Agent Loop — the core Think→Act→Check→Repeat cycle."""

from __future__ import annotations

import logging
from typing import Any

from physi_core.agent.tools import ToolController
from physi_core.llm.adapter import LLMClient
from physi_core.llm.response import LLMResponse

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
    ) -> AgentResult:
        """Run the agent loop for a single user turn.

        Args:
            user_input: The user's message text.
            conversation: Optional prior conversation context.

        Returns:
            AgentResult with the final text response and execution trace.
        """
        messages = list(conversation or [])
        messages.append({"role": "user", "content": user_input})

        tool_schemas = self._tools.get_all_schemas() or None
        trace: list[TraceStep] = []

        for round_idx in range(MAX_TOOL_ROUNDS):
            logger.info("Agent loop round %d", round_idx + 1)

            response = await self._llm.chat(
                messages=messages,
                system=self._system,
                tools=tool_schemas,
            )

            trace.append(TraceStep(
                round_num=round_idx + 1,
                response=response,
            ))

            # If pure text response → done
            if not response.has_tool_calls():
                return AgentResult(
                    text=response.text or "",
                    thinking=response.thinking,
                    trace=trace,
                    total_usage=_sum_usage(trace),
                )

            # Execute tool calls
            for tc in response.tool_calls:
                # Permission check
                if self._tools.is_denied(tc.name):
                    tool_output = f"Tool '{tc.name}' is denied by security policy."
                elif self._tools.is_dangerous(tc.name):
                    tool_output = f"Tool '{tc.name}' requires user confirmation. [PENDING]"
                else:
                    result = await self._tools.execute(tc.name, tc.arguments)
                    tool_output = result.output if result.success else f"Error: {result.error}"

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
        return AgentResult(
            text="抱歉，我处理这个请求花了太长时间，请重新问我。",
            trace=trace,
            total_usage=_sum_usage(trace),
        )


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
