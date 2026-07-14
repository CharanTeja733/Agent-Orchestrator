"""GetLeaveBalanceTool — personal leave balance query (Feature 16).

Queries the ``leave_balances`` table for the authenticated user's leave
data.  Privacy is enforced by ignoring any ``user_id`` from the LLM and
always using the authenticated user from the execution context.
"""

from __future__ import annotations

from uuid import UUID

from app.tools.base import BaseTool, ToolResult


class GetLeaveBalanceTool(BaseTool):
    """Get the current leave balance for the authenticated employee.

    Returns allocated, used, and remaining days for each leave type
    (annual, sick, personal) for the current year.

    **Security:** This tool IGNORES any ``user_id`` parameter from the
    LLM function call.  It always uses the authenticated user's ID
    from the execution context, preventing cross-user data access.
    """

    name = "get_leave_balance"
    description = (
        "Get the current leave balance for the authenticated employee. "
        "Returns allocated, used, and remaining days for each leave type "
        "(annual leave, sick leave, personal leave). "
        "Use this when the user asks about their OWN personal leave balance, "
        "remaining vacation days, or how many leaves they have left. "
        "ONLY works for the current authenticated user — never call it "
        "for other employees."
    )
    parameters = {
        "type": "object",
        "properties": {},
        # No required parameters — user_id is taken from auth context
    }

    def __init__(self, leave_repository) -> None:
        """Initialise with a :class:`LeaveRepository` instance."""
        self._leave_repo = leave_repository

    async def execute(self, **params: object) -> ToolResult:
        """Execute a leave balance query.

        Expected *params* (injected by :meth:`ToolRegistry.execute_tool`):
            user_id (str): Authenticated user's UUID (FROM CONTEXT, NOT LLM).
            db: Database session (unused — repo has its own).

        The ``user_id`` from the execution context is ALWAYS used,
        regardless of any value the LLM may have passed.
        """
        user_id_str = str(params.get("user_id", "")) if params else ""

        if not user_id_str:
            return ToolResult(
                tool_name=self.name,
                error="No authenticated user available for leave balance query",
            )

        try:
            user_id = UUID(user_id_str)
        except (ValueError, TypeError):
            return ToolResult(
                tool_name=self.name,
                error=f"Invalid user_id: {user_id_str}",
            )

        try:
            balances = await self._leave_repo.get_balances(user_id)
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                error=f"Failed to query leave balances: {exc}",
            )

        return ToolResult(
            tool_name=self.name,
            data={
                "label": "LEAVE BALANCE",
                "user_id": user_id_str,
                "year": 2026,
                "balances": balances,
                "formatted": self._format_balances(balances),
            },
        )

    @staticmethod
    def _format_balances(balances: list[dict]) -> str:
        """Format leave balance data for prompt injection."""
        if not balances:
            return (
                "No leave balance records found for the current year. "
                "The employee may not have been allocated leave yet, or "
                "records may not have been set up."
            )

        total_used = sum(b["used"] for b in balances)
        total_remaining = sum(b["remaining"] for b in balances)

        lines: list[str] = []
        for b in balances:
            lt = b["leave_type"].capitalize()
            lines.append(
                f"• {lt} Leave: {b['remaining']} days remaining "
                f"({b['total_allocated']} allocated, {b['used']} used)"
            )
        lines.append(
            f"\nTotal: {total_remaining} remaining across all leave types "
            f"({total_used} used)"
        )
        return "\n".join(lines)
