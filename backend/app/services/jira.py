"""Jira service layer — async HTTP client for Jira REST API v3.

Handles all communication with the Jira API for querying user tickets.
Uses ``httpx.AsyncClient`` with Basic Auth (bot email + API token).

Key design decisions:
- JQL is built server-side from a template — never from user input.
- Only 7 fields are extracted from Jira responses; all internal metadata
  is stripped.
- Read-only access — no ticket creation, updates, or deletions.
- All exceptions are ``JiraAPIError`` subclasses — never crashes the caller.

Reference: ``.claude/specs/17-jira-integration.md``
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.core.exceptions import (
    JiraAPIError,
    JiraAuthError,
    JiraNotFoundError,
    JiraRateLimitError,
    JiraTimeoutError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JQL template — user_email is the ONLY variable, injected server-side
# ---------------------------------------------------------------------------

_JQL_TEMPLATE = (
    'assignee = "{user_email}"'
    ' AND status NOT IN ("Done", "Closed", "Resolved", "Cancelled")'
    " ORDER BY created DESC"
)

# Fields requested from Jira to minimise payload size
_REQUESTED_FIELDS = "summary,status,priority,created,assignee,description"


class JiraService:
    """Async client for the Jira REST API v3 search endpoint.

    Authenticates via Basic Auth using a bot account (email + API token).
    All methods are read-only — no mutations are performed on Jira data.
    """

    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        timeout: int = 10,
        max_results: int = 20,
    ) -> None:
        """Initialise the Jira API client.

        Args:
            base_url: Jira instance URL (e.g. ``https://company.atlassian.net``).
            email: Bot account email for Basic Auth username.
            api_token: Jira API token for Basic Auth password.
            timeout: Request timeout in seconds.
            max_results: Default maximum tickets to return.

        Raises:
            ValueError: If *base_url*, *email*, or *api_token* is empty.
        """
        if not base_url:
            raise ValueError("JIRA_BASE_URL is required for Jira integration")
        if not email:
            raise ValueError("JIRA_BOT_EMAIL is required for Jira integration")
        if not api_token:
            raise ValueError("JIRA_API_TOKEN is required for Jira integration")

        self._base_url = base_url.rstrip("/")
        self._email = email
        self._api_token = api_token
        self._timeout = timeout
        self._max_results = max_results

        # Basic Auth: username=email, password=api_token
        auth = httpx.BasicAuth(username=email, password=api_token)
        self._client = httpx.AsyncClient(
            auth=auth,
            timeout=httpx.Timeout(timeout),
            headers={
                "Accept": "application/json",
                "User-Agent": "HR-QA-Agent/1.0",
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_open_tickets(
        self, user_email: str, max_results: int | None = None
    ) -> dict[str, Any]:
        """Fetch open Jira tickets for a user.

        Args:
            user_email: The reporter's email address (from auth context).
            max_results: Override the default max results (capped by config).

        Returns:
            ``{"total_open": int, "tickets": [dict, ...]}`` where each ticket
            dict contains *key*, *summary*, *status*, *priority*,
            *created_date*, *assignee*, and *url*.

        Raises:
            JiraAPIError: On any Jira API or network error.
        """
        jql = self._build_jql(user_email)
        limit = max_results if max_results is not None else self._max_results

        try:
            response = await self._client.post(
                f"{self._base_url}/rest/api/3/search/jql",
                json={
                    "jql": jql,
                    "maxResults": limit,
                    "fields": _REQUESTED_FIELDS.split(","),
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise JiraTimeoutError(
                f"Jira request timed out after {self._timeout}s"
            ) from None
        except httpx.HTTPStatusError as exc:
            self._handle_api_error(exc.response)
            raise  # unreachable — _handle_api_error always raises
        except httpx.RequestError as exc:
            raise JiraAPIError(
                f"Jira network error: {exc}"
            ) from exc

        data = response.json()
        tickets = self._parse_ticket_response(data)
        # New Jira API (search/jql) may not include "total" — use issues length
        total = data.get("total", len(tickets))

        logger.info(
            "Fetched %d open tickets for %s (total in Jira: %d)",
            len(tickets),
            user_email,
            total,
        )

        return {"total_open": total, "tickets": tickets}

    async def health_check(self) -> dict[str, Any]:
        """Lightweight connectivity check against Jira.

        Returns:
            ``{"status": "connected", "base_url": "..."}`` on success.

        Raises:
            JiraAPIError: If Jira is unreachable or auth fails.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/rest/api/3/myself",
            )
            response.raise_for_status()
            return {
                "status": "connected",
                "base_url": self._base_url,
            }
        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "base_url": self._base_url,
                "error": f"Timed out after {self._timeout}s",
            }
        except httpx.HTTPStatusError as exc:
            return {
                "status": "error",
                "base_url": self._base_url,
                "error": f"HTTP {exc.response.status_code}",
            }
        except httpx.RequestError as exc:
            return {
                "status": "unreachable",
                "base_url": self._base_url,
                "error": str(exc),
            }

    async def close(self) -> None:
        """Close the underlying ``httpx.AsyncClient``."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_jql(user_email: str) -> str:
        """Construct the JQL query for open tickets by reporter email.

        The email is the **only** user-controlled input; it is injected
        into a fixed template and never used to build free-form JQL.
        """
        return _JQL_TEMPLATE.format(user_email=user_email)

    def _parse_ticket_response(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract only the 7 relevant fields from each Jira issue.

        Strips all internal Jira metadata (custom fields, watchers,
        attachments, etc.).
        """
        issues = response.get("issues", [])
        tickets: list[dict[str, Any]] = []

        for issue in issues:
            fields = issue.get("fields", {})
            ticket = {
                "key": issue.get("key", ""),
                "summary": fields.get("summary", ""),
                "status": self._safe_get(fields, "status", "name", default="Unknown"),
                "priority": self._safe_get(
                    fields, "priority", "name", default="Not Set"
                ),
                "created_date": self._format_date(fields.get("created", "")),
                "assignee": self._safe_get(
                    fields, "assignee", "displayName", default="Unassigned"
                ),
                "url": f"{self._base_url}/browse/{issue.get('key', '')}",
            }
            tickets.append(ticket)

        return tickets

    @staticmethod
    def _safe_get(
        mapping: dict[str, Any],
        key: str,
        sub_key: str,
        default: str = "",
    ) -> str:
        """Safely extract a nested value from a Jira field.

        Many Jira fields (status, priority, assignee) are objects with a
        ``name`` / ``displayName`` sub-field.  If the field is missing or
        ``None``, return *default*.
        """
        obj = mapping.get(key)
        if obj is None:
            return default
        if isinstance(obj, dict):
            return str(obj.get(sub_key, default))
        return default

    @staticmethod
    def _format_date(iso_string: str) -> str:
        """Convert ISO-8601 Jira date to a human-readable format.

        Returns the original string if parsing fails.
        """
        if not iso_string:
            return ""
        try:
            # Jira returns dates like "2026-07-10T14:30:00.000+0000"
            # Strip timezone suffix for fromisoformat compatibility
            clean = iso_string.replace("+0000", "+00:00")
            dt = datetime.fromisoformat(clean)
            return dt.strftime("%B %d, %Y")
        except (ValueError, TypeError):
            return iso_string

    @staticmethod
    def _handle_api_error(response: httpx.Response) -> None:
        """Map Jira HTTP status codes to typed exceptions.

        Always raises — this is a "throw helper", never returns normally.
        """
        status = response.status_code
        detail = f"Jira API error: HTTP {status}"

        if status == 401:
            raise JiraAuthError(
                "Jira authentication failed. Check JIRA_API_TOKEN.", status
            )
        if status == 403:
            raise JiraAuthError(
                "Jira access denied. Check bot account permissions.", status
            )
        if status == 404:
            raise JiraNotFoundError("User or resource not found in Jira.", status)
        if status == 410:
            raise JiraAPIError(
                "Jira API endpoint has been deprecated. Update the integration.", status
            )
            raise JiraRateLimitError(
                "Jira rate limit exceeded. Wait and try again.", status
            )
        if 500 <= status < 600:
            raise JiraAPIError(f"Jira service unavailable (HTTP {status}).", status)

        raise JiraAPIError(detail, status)
