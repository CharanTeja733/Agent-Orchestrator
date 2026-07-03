"""Feedback schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.config import settings


class FeedbackCreate(BaseModel):
    message_id: UUID
    rating: str
    reason: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: str) -> str:
        if v not in ("positive", "negative"):
            raise ValueError("Rating must be 'positive' or 'negative'")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in settings.FEEDBACK_REASONS:
            raise ValueError(
                f"Reason must be one of: {', '.join(settings.FEEDBACK_REASONS)}"
            )
        return v

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 500:
            raise ValueError("Comment must be at most 500 characters")
        return v


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


class MessageFeedbackResponse(BaseModel):
    message_id: UUID
    has_feedback: bool
    feedback: Optional[FeedbackResponse] = None
