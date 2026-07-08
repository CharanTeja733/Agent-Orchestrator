"""Session and conversation management schemas (Feature 9).

Reference: ``.claude/specs/09-session-and-conversation-management.md`` Section 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    """Payload for ``POST /sessions``."""

    title: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional session title. Auto-generated from first message if omitted.",
    )
    device_info: Optional[dict[str, Any]] = Field(
        default=None,
        description="Device / browser metadata stored as JSONB.",
    )


class SessionUpdate(BaseModel):
    """Payload for ``PATCH /sessions/{id}`` — all fields optional."""

    title: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Session response schemas
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    """Full session detail returned by ``GET /sessions/{id}``."""

    id: UUID
    user_id: UUID
    title: Optional[str] = None
    is_active: bool
    device_info: Optional[Any] = None
    message_count: int = 0
    first_message_at: Optional[datetime] = None
    last_active: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SessionListItem(BaseModel):
    """Shorter session representation used in list responses."""

    id: UUID
    title: Optional[str] = None
    is_active: bool
    message_count: int = 0
    last_message_preview: Optional[str] = None
    last_active: datetime
    expires_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Paginated session list returned by ``GET /sessions``."""

    sessions: list[SessionListItem]
    total: int
    limit: int
    offset: int
    active_count: int
    expired_count: int


class SessionUpdateResponse(BaseModel):
    """Response for ``PATCH /sessions/{id}``."""

    id: UUID
    title: Optional[str] = None
    is_active: bool
    updated_at: Optional[datetime] = None
    message: str = "Session updated successfully"


class SessionDeleteResponse(BaseModel):
    """Response for ``DELETE /sessions/{id}``."""

    message: str = "Session deleted successfully"
    session_id: UUID
    messages_deleted: int


class SessionClearResponse(BaseModel):
    """Response for ``DELETE /sessions/{id}/messages``."""

    message: str = "All messages cleared"
    session_id: UUID
    messages_deleted: int


# ---------------------------------------------------------------------------
# Message response schemas (used by the sessions messages endpoints)
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    """Individual message returned in a paginated list."""

    id: UUID
    role: str
    content: str
    sources: Optional[Any] = None
    confidence: Optional[str] = None
    classification: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime
    agent_name: Optional[str] = None

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    """Paginated message list returned by ``GET /sessions/{id}/messages``."""

    session_id: UUID
    messages: list[MessageResponse]
    total: int
    limit: int
    offset: int
