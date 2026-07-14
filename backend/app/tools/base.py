"""Base tool interface — abstract contract for all agent tools (Feature 16)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """Result from executing a tool.

    Attributes:
        tool_name: The tool that produced this result.
        data: Arbitrary structured data from the tool (e.g. leave balances,
            search results).
        error: Error message if the tool failed, ``None`` on success.
    """

    tool_name: str
    data: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """``True`` when the tool executed without error."""
        return self.error is None


class BaseTool(ABC):
    """Abstract base for all agent tools.

    Each tool has a name, description, and JSON Schema parameters dict
    that maps directly to a Gemini ``FunctionDeclaration``.  Subclasses
    implement ``execute()`` with the actual logic.

    Class attributes (set on subclasses):
        name: Unique tool identifier (e.g. ``"get_leave_balance"``).
        description: Human-readable tool description for the LLM.
        parameters: JSON Schema ``dict`` describing the function arguments.
    """

    name: str = ""
    description: str = ""
    parameters: dict = {}

    def to_function_declaration(self) -> dict:
        """Return a dict suitable for :meth:`GeminiService._build_tool_declarations`.

        The returned shape matches what ``generate_with_tools()`` expects::

            {"name": "...", "description": "...", "parameters": {...}}
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @abstractmethod
    async def execute(self, **params: object) -> ToolResult:
        """Execute the tool with the given parameters.

        Args:
            **params: Keyword arguments matching the tool's ``parameters`` schema.

        Returns:
            A :class:`ToolResult` with the execution outcome.
        """
        ...
