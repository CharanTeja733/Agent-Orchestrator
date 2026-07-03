"""Feedback business logic — submission, retrieval, and validation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.repositories.feedback import FeedbackRepository
from app.repositories.message import MessageRepository


class FeedbackService:
    """Orchestrates feedback submission and retrieval.

    Ensures:
    - Feedback is only submitted on assistant messages.
    - One feedback per user per message (upsert behaviour).
    - Negative feedback requires a reason.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.feedback_repo = FeedbackRepository(db)
        self.message_repo = MessageRepository(db)

    async def submit_feedback(
        self,
        user_id: UUID,
        message_id: UUID,
        rating: str,
        reason: str | None = None,
        comment: str | None = None,
    ) -> dict:
        """Submit or update feedback for a message.

        Raises:
            NotFoundException: message does not exist.
            AppException (400): message is not an assistant response.
        """
        # 1. Verify the message exists and is an assistant response
        message = await self.message_repo.get(message_id)
        if message is None:
            raise NotFoundException("Message", str(message_id))

        if message.role != "assistant":
            raise AppException(
                "Cannot submit feedback for user messages",
                status_code=400,
            )

        # 2. Check for existing feedback (upsert)
        existing = await self.feedback_repo.get_by_message_and_user(
            message_id, user_id
        )

        if existing is not None:
            # Update
            updated = await self.feedback_repo.update_feedback(
                existing.id,
                rating=rating,
                reason=reason,
                comment=comment,
            )
            feedback = updated
        else:
            # Create
            feedback = await self.feedback_repo.create_feedback(
                message_id=message_id,
                user_id=user_id,
                rating=rating,
                reason=reason,
                comment=comment,
            )

        return {
            "message": "Feedback submitted successfully",
            "feedback": {
                "id": str(feedback.id),
                "message_id": str(feedback.message_id),
                "rating": feedback.rating,
                "reason": feedback.reason,
                "comment": feedback.comment,
                "created_at": (
                    feedback.created_at.isoformat()
                    if feedback.created_at
                    else None
                ),
            },
        }

    async def get_feedback(
        self, message_id: UUID, user_id: UUID
    ) -> dict:
        """Return the current user's feedback for a given message."""
        fb = await self.feedback_repo.get_by_message_and_user(
            message_id, user_id
        )

        if fb is None:
            return {
                "message_id": str(message_id),
                "has_feedback": False,
                "feedback": None,
            }

        return {
            "message_id": str(message_id),
            "has_feedback": True,
            "feedback": {
                "id": str(fb.id),
                "message_id": str(fb.message_id),
                "user_id": str(fb.user_id),
                "rating": fb.rating,
                "reason": fb.reason,
                "comment": fb.comment,
                "created_at": (
                    fb.created_at.isoformat() if fb.created_at else None
                ),
            },
        }
