"""Tool registry — manages and executes agent tools (Feature 16).

Provides a central registry that maps tool names to :class:`BaseTool`
instances, generates Gemini-compatible function declarations, and
executes tools with error isolation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools for an agent.

    Tools are registered by name and retrieved for execution or for
    building Gemini ``FunctionDeclaration`` lists.

    Usage::

        registry = ToolRegistry()
        registry.register(SearchPolicyTool(search_service))
        registry.register(GetLeaveBalanceTool(leave_repo))

        # For Gemini:
        declarations = registry.get_tool_declarations()

        # Execute a tool from an LLM function call:
        result = await registry.execute_tool("get_leave_balance", {}, context)
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance by its ``name``."""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        """Retrieve a tool by name, or ``None`` if not registered."""
        return self._tools.get(name)

    # ------------------------------------------------------------------
    # Gemini integration
    # ------------------------------------------------------------------

    def get_tool_declarations(self) -> list[dict]:
        """Return all registered tools as Gemini function-declaration dicts.

        Each dict has the shape ``{"name": ..., "description": ...,
        "parameters": ...}`` — ready for
        :meth:`~app.services.gemini.GeminiService._build_tool_declarations`.
        """
        return [tool.to_function_declaration() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute_tool(
        self, name: str, args: dict, context: dict
    ) -> ToolResult:
        """Execute a single tool by name.

        Args:
            name: Tool name (from the LLM's function call).
            args: Arguments from the LLM's function call.
            context: Request-scoped context dict.  Must include at minimum
                ``db`` (AsyncSession), ``user_id`` (str), ``user_role`` (str),
                and ``gemini_api_key`` (str).

        Returns:
            A :class:`ToolResult` — on failure, ``error`` is set and ``data``
            is empty.
        """
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("Unknown tool requested: %s", name)
            return ToolResult(
                tool_name=name,
                error=f"Unknown tool: {name}",
            )

        try:
            # Inject context into args so tools don't need to know
            # about the request lifecycle
            merged = {**context, **args}
            return await tool.execute(**merged)
        except Exception as exc:
            logger.exception("Tool '%s' execution failed", name)
            return ToolResult(
                tool_name=name,
                error=str(exc),
            )

    async def execute_tools(
        self, tool_calls: list[dict], context: dict
    ) -> list[ToolResult]:
        """Execute multiple tools in parallel.

        Each failure is isolated — one tool failing does not block the others.

        Args:
            tool_calls: List of ``{"tool": "name", "params": {...}}`` dicts
                (from :class:`~app.services.tool_selector.ToolSelectorService`
                or similar).
            context: Request-scoped context dict forwarded to each tool.

        Returns:
            One :class:`ToolResult` per tool call, in the same order.
        """
        if not tool_calls:
            return []

        async def _run(call: dict) -> ToolResult:
            name = call.get("tool", call.get("name", ""))
            args = call.get("params", call.get("args", {}))
            return await self.execute_tool(name, args, context)

        results = await asyncio.gather(*[_run(c) for c in tool_calls])
        return list(results)
