"""GetMyTicketsTool — Jira ticket query (Feature 17).

Queries the Jira REST API for the authenticated user's open tickets.
Privacy is enforced by ignoring any ``user_email`` from the LLM and
always using the authenticated user's email from the execution context.
"""

from __future__ import annotations

from app.core.exceptions import JiraAPIError
from app.tools.base import BaseTool, ToolResult


class GetMyTicketsTool(BaseTool):
    """Get open Jira tickets for the current authenticated user.

    Returns total count and ticket details including key, summary,
    status, priority, created date, assignee, and URL.

    **Security:** This tool IGNORES any ``user_email`` parameter from the
    LLM function call.  It always uses the authenticated user's email
    from the execution context, preventing cross-user data access.
    """

    name = "get_my_tickets"
    description = (
        "Get the current employee's open Jira tickets. "
        "Returns the total number of open tickets and details for each: "
        "ticket key, summary, status, priority, created date, assignee, "
        "and a direct link to view the ticket in Jira. "
        "Use this when the user asks about their OWN tickets — "
        "'my open tickets', 'ticket status', 'any update on my ticket', "
        "'how many tickets do I have', 'what are my tickets', etc. "
        "ONLY works for the current authenticated user — never call it "
        "for other employees."
    )
    parameters = {
        "type": "object",
        "properties": {},
        # No required parameters — user_email is taken from auth context
    }

    def __init__(self, jira_service) -> None:
        """Initialise with a :class:`JiraService` instance."""
        self._jira_service = jira_service

    async def execute(self, **params: object) -> ToolResult:
        """Execute a Jira ticket query.

        Expected *params* (injected by :meth:`ToolRegistry.execute_tool`):
            user_email (str): Authenticated user's email (FROM CONTEXT, NOT LLM).

        The ``user_email`` from the execution context is ALWAYS used,
        regardless of any value the LLM may have passed.
        """
        user_email = str(params.get("user_email", "")) if params else ""

        if not user_email:
            return ToolResult(
                tool_name=self.name,
                error="No authenticated user email available for Jira ticket query",
            )

        try:
            ticket_data = await self._jira_service.get_open_tickets(
                user_email=user_email,
            )
        except JiraAPIError as exc:
            return ToolResult(
                tool_name=self.name,
                error=f"Jira query failed: {exc.message}",
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                error=f"Unexpected error querying Jira tickets: {exc}",
            )

        tickets = ticket_data.get("tickets", [])
        total_open = ticket_data["total_open"]

        return ToolResult(
            tool_name=self.name,
            data={
                "label": "JIRA TICKETS",
                "total_open": total_open,
                "tickets": tickets,
                "formatted": self._format_tickets(tickets, total_open),
            },
        )

    @staticmethod
    def _format_tickets(tickets: list[dict], total_open: int) -> str:
        """Format Jira ticket data for prompt injection.

        Spec format (Feature 17 Section 17):
            Total Open Tickets: N

            1. KEY — summary
               Status: X | Priority: Y | Opened: date
               Assigned to: name
               URL: link
        """
        if not tickets:
            return (
                "You have no open tickets. Everything looks good! "
                "If you need to report a new IT issue, please create a "
                "ticket in Jira or contact the IT support team."
            )

        lines: list[str] = [f"Total Open Tickets: {total_open}"]

        for i, t in enumerate(tickets, 1):
            lines.append("")
            lines.append(f"{i}. {t['key']} — {t['summary']}")
            lines.append(
                f"   Status: {t['status']} | Priority: {t['priority']}"
                f" | Opened: {t['created_date']}"
            )
            lines.append(f"   Assigned to: {t['assignee']}")
            lines.append(f"   URL: {t['url']}")

        if total_open > len(tickets):
            lines.append("")
            lines.append(
                f"(Showing {len(tickets)} most recent. "
                f"View all {total_open} tickets in Jira.)"
            )

        return "\n".join(lines)
