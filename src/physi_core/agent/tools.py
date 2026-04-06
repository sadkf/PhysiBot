"""Agent Tool Controller — tool registration, permission gating, and execution."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from typing import Any

from physi_core.observability import emit_event

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
    exposed_to_llm: bool = True

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

    @staticmethod
    def _infer_schema(func: ToolFunction) -> dict[str, Any]:
        """Infer JSON schema parameters from function annotations."""
        import inspect
        sig = inspect.signature(func)
        properties = {}
        required = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
        }

        for name, param in sig.parameters.items():
            if name == "self":
                continue
            
            param_type = type_map.get(param.annotation, "string")
            param_schema: dict[str, Any] = {"type": param_type}
            
            if param.default is not inspect.Parameter.empty:
                param_schema["default"] = param.default
            else:
                required.append(name)
                
            properties[name] = param_schema

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def register_func(
        self,
        description: str,
        permission: PermissionLevel = PermissionLevel.SAFE,
    ) -> Callable[[ToolFunction], ToolFunction]:
        """Decorator to register a tool and infer its schema from signature."""
        def decorator(func: ToolFunction) -> ToolFunction:
            self.register(
                name=func.__name__,
                description=description,
                parameters=self._infer_schema(func),
                function=func,
                permission=permission,
            )
            return func
        return decorator

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        function: ToolFunction,
        permission: PermissionLevel = PermissionLevel.SAFE,
        exposed_to_llm: bool = True,
    ) -> None:
        """Register a tool."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            function=function,
            permission=permission,
            exposed_to_llm=exposed_to_llm,
        )
        logger.info(
            "Registered tool: %s (permission: %s, exposed_to_llm: %s)",
            name,
            permission.value,
            exposed_to_llm,
        )
        emit_event(
            "tool.registered",
            tool=name,
            permission=permission.value,
            exposed_to_llm=exposed_to_llm,
        )

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def is_dangerous(self, tool_name: str) -> bool:
        """Check if a tool requires confirmation."""
        # 暂时将所有工具设为不需要用户确认
        return False

    def is_denied(self, tool_name: str) -> bool:
        """Check if a tool is permanently denied."""
        tool = self._tools.get(tool_name)
        return tool is not None and tool.permission == PermissionLevel.DENY

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with the given arguments."""
        tool = self._tools.get(tool_name)
        start_t0 = time.perf_counter()

        if tool is None:
            latency_ms = int((time.perf_counter() - start_t0) * 1000)
            emit_event("tool_call", tool=tool_name, args=arguments, success=False, error=f"Unknown tool: {tool_name}", latency_ms=latency_ms)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}",
            )

        if tool.permission == PermissionLevel.DENY:
            latency_ms = int((time.perf_counter() - start_t0) * 1000)
            emit_event("tool_call", tool=tool_name, args=arguments, success=False, error="denied by policy", latency_ms=latency_ms)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=f"Tool '{tool_name}' is denied by policy",
            )

        try:
            result = await tool.function(**arguments)
            text = str(result)
            latency_ms = int((time.perf_counter() - start_t0) * 1000)
            emit_event(
                "tool_call",
                tool=tool_name,
                args=arguments,
                success=True,
                output_preview=text[:1200],
                output_len=len(text),
                latency_ms=latency_ms,
            )
            return ToolResult(
                tool_name=tool_name,
                success=True,
                output=text,
            )
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            latency_ms = int((time.perf_counter() - start_t0) * 1000)
            emit_event("tool_call", tool=tool_name, args=arguments, success=False, error=str(e), latency_ms=latency_ms)
            return ToolResult(
                tool_name=tool_name,
                success=False,
                output="",
                error=str(e),
            )

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """Get LLM-compatible schemas for all registered tools."""
        return [tool.to_llm_schema() for tool in self._tools.values() if tool.exposed_to_llm]

    @property
    def tool_count(self) -> int:
        return len(self._tools)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def list_exposed_tools(self) -> list[str]:
        return [name for name, tool in self._tools.items() if tool.exposed_to_llm]
