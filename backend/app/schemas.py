"""Pydantic schemas for request / response validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UserRole(str, Enum):
    employee = "employee"
    manager = "manager"
    hr_admin = "hr_admin"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    database: str
    gemini_api: str


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "employee"
    department: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    department: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: str
    password: str


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class SessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    is_active: bool
    created_at: datetime
    last_active: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------

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
    classification: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackCreate(BaseModel):
    message_id: UUID
    rating: str
    reason: Optional[str] = None
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: UUID
    message_id: UUID
    user_id: UUID
    rating: str
    reason: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Document chunk
# ---------------------------------------------------------------------------

class DocumentChunk(BaseModel):
    content: str
    source: str
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_index: int
    access_level: str = "all"
