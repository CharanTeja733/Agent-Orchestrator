"""Repository for session persistence operations."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Session
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """Data-access layer for the ``sessions`` table."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Session, db)

    # ------------------------------------------------------------------
    # Existing methods
    # ------------------------------------------------------------------

    async def get_active_by_user(self, user_id: UUID) -> list[Session]:
        """Return all active sessions for a user, most recent first."""
        result = await self.db.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.is_active == True)  # noqa: E712
            .order_by(Session.last_active.desc())
        )
        return list(result.scalars().all())

    async def create_session(
        self, user_id: UUID, device_info: dict | None = None
    ) -> Session:
        """Create a new session for the user.

        ``created_at``, ``last_active`` and ``expires_at`` are set by the
        database via server-side defaults.
        """
        return await self.create(user_id=user_id, device_info=device_info)

    async def update_last_active(self, session_id: UUID) -> None:
        """Touch the ``last_active`` timestamp without a full commit."""
        await self.db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(last_active=func.now())
        )
        await self.db.flush()

    async def count_active_sessions(self) -> int:
        """Count sessions that have been active within the last hour."""
        result = await self.db.execute(
            select(func.count(Session.id))
            .where(
                Session.is_active == True,  # noqa: E712
                Session.last_active >= func.now() - text("INTERVAL '1 hour'"),
            )
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Feature 9 — session listing, update, delete, cleanup
    # ------------------------------------------------------------------

    _ALLOWED_SORT_COLUMNS = {
        "last_active": Session.last_active,
        "created_at": Session.created_at,
        "title": Session.title,
    }

    async def list_by_user(
        self,
        user_id: UUID,
        is_active: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "last_active",
        sort_order: str = "desc",
    ) -> tuple[list[Session], int]:
        """Paginated, filtered, sorted session list for a user.

        Returns:
            ``(sessions, total_count)`` tuple.
        """
        conditions = [Session.user_id == user_id]
        if is_active is not None:
            conditions.append(Session.is_active == is_active)  # noqa: E712

        sort_col = self._ALLOWED_SORT_COLUMNS.get(sort_by, Session.last_active)
        order = sort_col.desc() if sort_order == "desc" else sort_col.asc()

        # Total count (before pagination)
        count_result = await self.db.execute(
            select(func.count(Session.id)).where(*conditions)
        )
        total = count_result.scalar_one()

        # Paginated query
        result = await self.db.execute(
            select(Session)
            .where(*conditions)
            .order_by(order)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def update_session(
        self, session_id: UUID, **kwargs
    ) -> Session | None:
        """Partial update of session fields.

        Accepts ``title``, ``is_active``, ``updated_at`` as keyword
        arguments.  Delegates to :meth:`BaseRepository.update` which
        commits and refreshes.
        """
        # Always bump updated_at on partial updates
        kwargs.setdefault("updated_at", func.now())
        return await self.update(session_id, **kwargs)

    async def delete_with_count(self, session_id: UUID) -> int:
        """Delete a session and return the number of messages that were
        attached to it (pre-delete count).

        The FK cascade (``ON DELETE CASCADE`` on ``messages.session_id``)
        handles removing the messages automatically.
        """
        from app.models.models import Message

        # Count messages before deletion
        count_result = await self.db.execute(
            select(func.count(Message.id)).where(
                Message.session_id == session_id
            )
        )
        messages_count = count_result.scalar_one()

        # Delete the session (cascade removes messages + their feedback)
        await self.db.execute(
            delete(Session).where(Session.id == session_id)
        )
        await self.db.commit()

        return messages_count

    async def get_active_count(self, user_id: UUID) -> int:
        """Count active (non-expired) sessions for a user."""
        result = await self.db.execute(
            select(func.count(Session.id)).where(
                Session.user_id == user_id,
                Session.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def get_expired_count(self, user_id: UUID) -> int:
        """Count expired / deactivated sessions for a user."""
        result = await self.db.execute(
            select(func.count(Session.id)).where(
                Session.user_id == user_id,
                Session.is_active == False,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def get_expired_sessions(
        self, cutoff_date: datetime
    ) -> list[Session]:
        """Return sessions whose ``expires_at`` is before *cutoff_date*."""
        result = await self.db.execute(
            select(Session).where(Session.expires_at < cutoff_date)
        )
        return list(result.scalars().all())

    async def delete_expired_sessions(self, cutoff_date: datetime) -> int:
        """Hard-delete sessions expired before *cutoff_date*.

        Returns the number of sessions deleted.
        """
        # Count first, then delete
        count_result = await self.db.execute(
            select(func.count(Session.id)).where(
                Session.expires_at < cutoff_date
            )
        )
        total = count_result.scalar_one()

        if total > 0:
            await self.db.execute(
                delete(Session).where(Session.expires_at < cutoff_date)
            )
            await self.db.commit()

        return total

    async def extend_expiry(self, session_id: UUID) -> None:
        """Extend ``expires_at``, touch ``last_active``, and set
        ``is_active = true`` (re-activation).

        Does **not** commit — the caller decides when to commit.
        """
        from app.config import settings

        await self.db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(
                last_active=func.now(),
                expires_at=func.now()
                + text(f"INTERVAL '{settings.SESSION_EXPIRY_HOURS} hours'"),
                is_active=True,
            )
        )
        await self.db.flush()
