"""Jira ticket endpoints — direct access for testing and verification (Feature 17).

Provides a direct endpoint to query the authenticated user's open Jira tickets,
bypassing the agent pipeline.  Useful for debugging Jira connectivity and
verifying the JiraService integration.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.models import User
from app.services.jira import JiraService
from app.core.exceptions import JiraAPIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.get("/")
async def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's open Jira tickets.

    Calls the Jira REST API directly — does NOT go through the agent
    pipeline.  Returns the total count of open tickets and ticket details
    (key, summary, status, priority, created date, assignee, URL).

    Requires a valid JWT access token.
    """
    try:
        jira_service = JiraService(
            base_url=settings.JIRA_BASE_URL,
            email=settings.JIRA_BOT_EMAIL,
            api_token=settings.JIRA_API_TOKEN,
            timeout=settings.JIRA_REQUEST_TIMEOUT_SECONDS,
            max_results=settings.JIRA_MAX_RESULTS,
        )
        result = await jira_service.get_open_tickets(current_user.email)
        await jira_service.close()
        return result

    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Jira integration not configured: {exc}",
        ) from exc
    except JiraAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Jira API error: {exc.message}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error fetching Jira tickets")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch Jira tickets",
        ) from exc
