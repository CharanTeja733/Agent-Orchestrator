"""Feedback submission and retrieval endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.models import User
from app.schemas.feedback import FeedbackCreate, MessageFeedbackResponse
from app.services.feedback import FeedbackService

router = APIRouter(prefix="/feedback", tags=["Feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    data: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit or update feedback for an assistant message.

    - **message_id**: UUID of the assistant message to rate.
    - **rating**: ``positive`` or ``negative``.
    - **reason**: Required when rating is ``negative``. Must be one of the
      pre-defined reasons (e.g. ``incorrect_information``,
      ``incomplete_answer``, etc.).
    - **comment**: Optional free-text (max 500 characters).

    Only one feedback entry per user per message — submitting again updates
    the existing entry.
    """
    service = FeedbackService(db)
    return await service.submit_feedback(
        user_id=current_user.id,
        message_id=data.message_id,
        rating=data.rating,
        reason=data.reason,
        comment=data.comment,
    )


@router.get("/{message_id}", response_model=MessageFeedbackResponse)
async def get_feedback(
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the current user's feedback for a specific message.

    Returns ``has_feedback: false`` with ``feedback: null`` when no feedback
    has been submitted yet.
    """
    service = FeedbackService(db)
    return await service.get_feedback(message_id, current_user.id)
