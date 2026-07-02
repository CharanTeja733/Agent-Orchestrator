"""Session and conversation management routes (Feature 9).

Thin controllers — parse request, call :class:`SessionService`, return
response.  All endpoints require JWT authentication.

Reference: ``.claude/specs/09-session-and-conversation-management.md``
Section 4.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.models import User
from app.schemas.session import (
    MessageListResponse,
    SessionClearResponse,
    SessionCreate,
    SessionDeleteResponse,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
    SessionUpdateResponse,
)
from app.services.session import SessionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])


# ---------------------------------------------------------------------------
# POST /sessions
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    data: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new conversation session."""
    service = SessionService(db)
    return await service.create_session(
        user_id=current_user.id,
        title=data.title,
        device_info=data.device_info,
    )


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(
        default="last_active",
        pattern=r"^(last_active|created_at|title)$",
    ),
    sort_order: str = Query(
        default="desc",
        pattern=r"^(asc|desc)$",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sessions for the current user with pagination."""
    service = SessionService(db)
    return await service.list_sessions(
        user_id=current_user.id,
        is_active=is_active,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get session details with message count and first message time."""
    service = SessionService(db)
    return await service.get_session(
        session_id=session_id,
        user_id=current_user.id,
    )


# ---------------------------------------------------------------------------
# PATCH /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.patch("/{session_id}")
async def update_session(
    session_id: UUID,
    data: SessionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update session title or active status."""
    service = SessionService(db)
    return await service.update_session(
        session_id=session_id,
        user_id=current_user.id,
        title=data.title,
        is_active=data.is_active,
    )


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.delete("/{session_id}")
async def delete_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a session and all its messages (cascade)."""
    service = SessionService(db)
    return await service.delete_session(
        session_id=session_id,
        user_id=current_user.id,
    )


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.get("/{session_id}/messages")
async def get_messages(
    session_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    before: datetime | None = Query(default=None),
    after: datetime | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated messages for a session, oldest first."""
    service = SessionService(db)
    return await service.get_messages(
        session_id=session_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        before=before,
        after=after,
    )


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.delete("/{session_id}/messages")
async def clear_messages(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear all messages in a session."""
    service = SessionService(db)
    return await service.clear_messages(
        session_id=session_id,
        user_id=current_user.id,
    )
