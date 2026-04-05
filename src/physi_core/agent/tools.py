"""Agent Tool Controller — tool registration, permission gating, and execution."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """Tool permission levels."""

    SAFE = "safe"  # Execute without confirmation
    CONFIRM = "confirm"  # Require user confirmation before execution
    DENY = "deny"  # Never execute


# Type alias for async tool functions
ToolFunction = Callable[..., Coroutine[Any, Any, Any]]


@dataclass
class ToolDefinition:
    """A registered tool with its metadata and implementation."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the tool's parameters
    function: ToolFunction
    permission: PermissionLevel = PermissionLevel.SAFE

    def to_llm_schema(self) -> dict[str, Any]:
        """Convert to LLM-compatible tool schema (Anthropic/OpenAI format)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    """Result of a tool execution."""

    tool_name: str
    success: bool
    output: str
    error: str | None = None


class ToolController:
    """Manages tool registration, permission checks, and execution."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        function: ToolFunction,
        permission: PermissionLevel = PermissionLevel.SAFE,
    ) -> None:
        """Register a tool."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            function=function,
            permission=permission,
        )
        logger.info("Registered tool: %s (permission: %s)", name, permission.value)

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def is_dangerous(self, tool_name: str) -> bool:
        """Check if a tool requires confirmation."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return True  # Unknown tools are dangerous by default
        return tool.permission in (PermissionLevel.CONFIRM, PermissionLevel.DENY)

    def is_denied(self, tool_name: str) -> bool:
        """Check if a tool is permanently denied."""
        tool = self._tools.get(tool_name)
        return tool is not None and tool.permission == PermissionLevel.DENY

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with the given arguments."""
        tool = self._tools.get(tool_name)

        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}",
            )

        if tool.permission == PermissionLevel.DENY:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=f"Tool '{tool_name}' is denied by policy",
            )

        try:
            result = await tool.function(**arguments)
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output=str(result),
            )
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=str(e),
            )

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """Get LLM-compatible schemas for all registered tools."""
        return [tool.to_llm_schema() for tool in self._tools.values()]

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
