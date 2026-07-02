"""Message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class MessageCreate(BaseModel):
    session_id: UUID
    role: str
    content: str


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    role: str
    content: str
    sources: Optional[Any] = None
    confidence: Optional[str] = None
    tokens_used: Optional[int] = None
    classification: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
