"""Tool infrastructure for agent tool-use (Feature 16).

Provides the base classes and registry that enable Gemini-native function
calling within the HR Agent pipeline.
"""

from app.tools.base import BaseTool, ToolResult
from app.tools.registry import ToolRegistry
from app.tools.search_policy import SearchPolicyTool
from app.tools.get_leave_balance import GetLeaveBalanceTool
from app.tools.get_my_tickets import GetMyTicketsTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "SearchPolicyTool",
    "GetLeaveBalanceTool",
    "GetMyTicketsTool",
]
