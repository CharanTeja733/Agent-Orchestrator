"""Repository for feedback persistence operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Feedback
from app.repositories.base import BaseRepository


class FeedbackRepository(BaseRepository[Feedback]):
    """Data-access layer for the ``feedback`` table."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Feedback, db)

    async def get_by_message_and_user(
        self, message_id: UUID, user_id: UUID
    ) -> Feedback | None:
        """Return the feedback entry for a given message and user, if any."""
        result = await self.db.execute(
            select(Feedback).where(
                Feedback.message_id == message_id,
                Feedback.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_feedback(self, **kwargs) -> Feedback:
        """Create a new feedback entry."""
        return await self.create(**kwargs)

    async def update_feedback(self, feedback_id: UUID, **kwargs) -> Feedback | None:
        """Update an existing feedback entry."""
        return await self.update(feedback_id, **kwargs)
