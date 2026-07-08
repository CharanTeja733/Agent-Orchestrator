"""Repository for message persistence operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Message
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    """Data-access layer for the ``messages`` table."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Message, db)

    # ------------------------------------------------------------------
    # Existing methods
    # ------------------------------------------------------------------

    async def get_conversation_history(
        self, session_id: UUID, limit: int = 6
    ) -> list[Message]:
        """Return the most recent *limit* messages in chronological order.

        Fetches the last N messages by ``created_at`` descending, then
        reverses the list so callers receive oldest-first ordering.
        """
        result = await self.db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def create_message(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        role: str,
        content: str,
        sources: list | None = None,
        confidence: str | None = None,
        tokens_used: int | None = None,
        classification: str | None = None,
        processing_time_ms: float | None = None,
        agent_name: str | None = None,
    ) -> Message:
        """Create and persist a new message.

        All optional metadata fields are keyword-only so callers can pass only
        what is relevant for the message role.
        """
        return await self.create(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            sources=sources,
            confidence=confidence,
            tokens_used=tokens_used,
            classification=classification,
            processing_time_ms=processing_time_ms,
            agent_name=agent_name,
        )

    # ------------------------------------------------------------------
    # Feature 9 — paginated retrieval, deletion, counts, preview
    # ------------------------------------------------------------------

    async def get_by_session(
        self,
        session_id: UUID,
        limit: int = 50,
        offset: int = 0,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> tuple[list[Message], int]:
        """Paginated messages for a session with optional time-range
        filters.

        Returns:
            ``(messages, total_count)`` tuple.  Messages are ordered by
            ``created_at`` ascending (oldest first).
        """
        conditions = [Message.session_id == session_id]
        if before is not None:
            conditions.append(Message.created_at < before)
        if after is not None:
            conditions.append(Message.created_at > after)

        # Total count
        count_result = await self.db.execute(
            select(func.count(Message.id)).where(*conditions)
        )
        total = count_result.scalar_one()

        # Paginated query — oldest first for chronological display
        result = await self.db.execute(
            select(Message)
            .where(*conditions)
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def delete_by_session(self, session_id: UUID) -> int:
        """Delete all messages in a session and return the count deleted."""
        # Count first
        count_result = await self.db.execute(
            select(func.count(Message.id)).where(
                Message.session_id == session_id
            )
        )
        total = count_result.scalar_one()

        if total > 0:
            await self.db.execute(
                delete(Message).where(Message.session_id == session_id)
            )
            await self.db.commit()

        return total

    async def count_by_session(self, session_id: UUID) -> int:
        """Return the number of messages in a session."""
        result = await self.db.execute(
            select(func.count(Message.id)).where(
                Message.session_id == session_id
            )
        )
        return result.scalar_one()

    async def get_last_message(
        self, session_id: UUID, role_filter: str | None = None
    ) -> Message | None:
        """Return the most recent message for a session.

        Args:
            session_id: Session to query.
            role_filter: If set, only return messages with this role
                (e.g. ``"user"`` for the last-message preview).
        """
        conditions = [Message.session_id == session_id]
        if role_filter is not None:
            conditions.append(Message.role == role_filter)

        result = await self.db.execute(
            select(Message)
            .where(*conditions)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_last_agent_name(self, session_id: UUID) -> str | None:
        """Return the ``agent_name`` of the most recent assistant message
        in a session.

        Used by the orchestrator (Feature 14) to route follow-up queries
        to the same agent that handled the previous message.

        Args:
            session_id: Session to query.

        Returns:
            Agent name string (``"hr"``, ``"it"``, …) or ``None`` if no
            matching message exists.
        """
        result = await self.db.execute(
            select(Message.agent_name)
            .where(Message.session_id == session_id)
            .where(Message.role == "assistant")
            .where(Message.agent_name.isnot(None))
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
