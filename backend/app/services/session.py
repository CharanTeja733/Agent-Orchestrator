"""Session management business logic (Feature 9).

Follows the same pattern as :class:`AuthService`: accepts an
:class:`AsyncSession`, creates repositories internally, and returns plain
dicts or raises :class:`AppException` subclasses.

Reference: ``.claude/specs/09-session-and-conversation-management.md``.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ForbiddenException,
    NotFoundException,
    SessionDeactivatedException,
    SessionExpiredException,
)
from app.models.models import Session
from app.repositories.message import MessageRepository
from app.repositories.session import SessionRepository

logger = logging.getLogger(__name__)

# Greeting words that should NOT trigger auto-title generation
_GREETINGS: set[str] = {
    "hi",
    "hello",
    "hey",
    "greetings",
    "good morning",
    "good afternoon",
    "good evening",
    "yo",
    "sup",
    "heya",
    "howdy",
}


class SessionService:
    """Business logic for session CRUD, message management, and RAG
    pipeline integration."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.session_repo = SessionRepository(db)
        self.message_repo = MessageRepository(db)
        # Feature 11 — feedback lookup
        from app.repositories.feedback import FeedbackRepository
        self.feedback_repo = FeedbackRepository(db)

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    async def create_session(
        self,
        user_id: UUID,
        title: str | None = None,
        device_info: dict | None = None,
    ) -> dict:
        """Create a new conversation session.

        Returns a dict matching :class:`SessionResponse`.
        """
        session = await self.session_repo.create_session(
            user_id=user_id, device_info=device_info
        )
        # Set title if provided (otherwise stays null — auto-generated later)
        if title:
            await self.session_repo.update_session(
                session.id, title=title
            )
            # Re-fetch since update committed
            session = await self.session_repo.get(session.id)

        return await self._session_to_detail_dict(session)

    async def get_session(self, session_id: UUID, user_id: UUID) -> dict:
        """Get full session detail with computed message counts.

        Raises:
            NotFoundException: Session does not exist.
            ForbiddenException: Session belongs to a different user.
        """
        session = await self._get_session_and_verify_ownership(
            session_id, user_id
        )
        return await self._session_to_detail_dict(session)

    async def _session_to_detail_dict(self, session: Session) -> dict:
        """Build a detail dict for a session including computed
        ``message_count`` and ``first_message_at``."""
        msg_count = await self.message_repo.count_by_session(session.id)

        # Get first message timestamp
        messages, _ = await self.message_repo.get_by_session(
            session.id, limit=1, offset=0
        )
        first_message_at = messages[0].created_at if messages else None

        return {
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "is_active": session.is_active,
            "device_info": session.device_info,
            "message_count": msg_count,
            "first_message_at": first_message_at,
            "last_active": session.last_active,
            "expires_at": session.expires_at,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    async def list_sessions(
        self,
        user_id: UUID,
        is_active: bool | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "last_active",
        sort_order: str = "desc",
    ) -> dict:
        """Paginated session list with metadata.

        Returns a dict matching :class:`SessionListResponse`.
        """
        sessions, total = await self.session_repo.list_by_user(
            user_id=user_id,
            is_active=is_active,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        active_count = await self.session_repo.get_active_count(user_id)
        expired_count = await self.session_repo.get_expired_count(user_id)

        items: list[dict] = []
        for s in sessions:
            msg_count = await self.message_repo.count_by_session(s.id)
            last_msg = await self.message_repo.get_last_message(
                s.id, role_filter="user"
            )
            items.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "is_active": s.is_active,
                    "message_count": msg_count,
                    "last_message_preview": (
                        last_msg.content[:100] if last_msg else None
                    ),
                    "last_active": s.last_active,
                    "expires_at": s.expires_at,
                    "created_at": s.created_at,
                }
            )

        return {
            "sessions": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "active_count": active_count,
            "expired_count": expired_count,
        }

    async def update_session(
        self,
        session_id: UUID,
        user_id: UUID,
        title: str | None = None,
        is_active: bool | None = None,
    ) -> dict:
        """Partial update of session title and / or active status.

        Returns a dict matching :class:`SessionUpdateResponse`.
        """
        session = await self._get_session_and_verify_ownership(
            session_id, user_id
        )

        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if is_active is not None:
            updates["is_active"] = is_active

        if not updates:
            # Nothing to update — return current state
            return {
                "id": str(session.id),
                "title": session.title,
                "is_active": session.is_active,
                "updated_at": session.updated_at,
                "message": "No changes provided",
            }

        updated = await self.session_repo.update_session(
            session_id, **updates
        )
        return {
            "id": str(updated.id),
            "title": updated.title,
            "is_active": updated.is_active,
            "updated_at": updated.updated_at,
            "message": "Session updated successfully",
        }

    async def delete_session(
        self, session_id: UUID, user_id: UUID
    ) -> dict:
        """Delete a session and all its messages (cascade).

        Returns a dict matching :class:`SessionDeleteResponse`.
        """
        await self._get_session_and_verify_ownership(session_id, user_id)
        messages_deleted = await self.session_repo.delete_with_count(
            session_id
        )
        return {
            "message": "Session deleted successfully",
            "session_id": session_id,
            "messages_deleted": messages_deleted,
        }

    # ------------------------------------------------------------------
    # Message management
    # ------------------------------------------------------------------

    async def get_messages(
        self,
        session_id: UUID,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
        before: datetime | None = None,
        after: datetime | None = None,
    ) -> dict:
        """Paginated messages for a session, oldest first.

        Returns a dict matching :class:`MessageListResponse`.
        """
        await self._get_session_and_verify_ownership(session_id, user_id)

        messages, total = await self.message_repo.get_by_session(
            session_id=session_id,
            limit=limit,
            offset=offset,
            before=before,
            after=after,
        )

        # Feature 11: Load feedback for assistant messages
        feedback_dict: dict[str, dict] = {}
        for m in messages:
            if m.role == "assistant":
                fb = await self.feedback_repo.get_by_message_and_user(
                    m.id, user_id
                )
                if fb:
                    feedback_dict[str(m.id)] = {
                        "id": str(fb.id),
                        "message_id": str(fb.message_id),
                        "user_id": str(fb.user_id),
                        "rating": fb.rating,
                        "reason": fb.reason,
                        "comment": fb.comment,
                        "created_at": (
                            fb.created_at.isoformat()
                            if fb.created_at
                            else None
                        ),
                    }

        return {
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "sources": m.sources,
                    "confidence": m.confidence,
                    "classification": m.classification,
                    "tokens_used": m.tokens_used,
                    "created_at": m.created_at,
                    "feedback": feedback_dict.get(str(m.id)),
                    "agent_name": getattr(m, "agent_name", None),
                }
                for m in messages
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def clear_messages(
        self, session_id: UUID, user_id: UUID
    ) -> dict:
        """Delete all messages in a session.

        Returns a dict matching :class:`SessionClearResponse`.
        """
        await self._get_session_and_verify_ownership(session_id, user_id)
        deleted = await self.message_repo.delete_by_session(session_id)
        return {
            "message": "All messages cleared",
            "session_id": session_id,
            "messages_deleted": deleted,
        }

    # ------------------------------------------------------------------
    # RAG pipeline helpers
    # ------------------------------------------------------------------

    async def get_or_create_session(
        self,
        user_id: UUID,
        session_id: UUID | None = None,
    ) -> Session:
        """Load an existing session or create a new one.

        Used by :class:`RAGService._load_context` instead of its inline
        session-management code.

        Expiry behaviour (per spec Section 14):
        - If the session is expired (``expires_at < NOW``) but not
          manually deactivated, it is **re-activated** — expiry is
          extended and ``is_active`` is set back to ``true``.
        - If the session was manually deactivated (``is_active=False``
          and not expired), raises :class:`SessionDeactivatedException`.

        Raises:
            NotFoundException: *session_id* does not exist.
            ForbiddenException: Session belongs to a different user.
            SessionDeactivatedException: Session is manually deactivated.
        """
        from datetime import datetime, timezone

        if session_id is not None:
            session = await self.session_repo.get(session_id)
            if session is None:
                raise NotFoundException("Session", str(session_id))
            if session.user_id != user_id:
                raise ForbiddenException(
                    "You don't have access to this session"
                )

            now = datetime.now(timezone.utc)

            # Check for manual deactivation (not time-expired)
            if (
                not session.is_active
                and session.expires_at is not None
                and session.expires_at > now
            ):
                raise SessionDeactivatedException()

            # Re-activate expired sessions (spec Section 14)
            if (
                session.expires_at is not None
                and session.expires_at < now
            ):
                await self.session_repo.extend_expiry(session_id)

            return session

        # Auto-create new session
        return await self.session_repo.create_session(user_id=user_id)

    async def update_activity(self, session_id: UUID) -> None:
        """Extend expiry, update ``last_active``, and re-activate the
        session (idempotent — safe to call after every message)."""
        await self.session_repo.extend_expiry(session_id)

    # ------------------------------------------------------------------
    # Title auto-generation
    # ------------------------------------------------------------------

    def generate_title(self, first_message: str) -> str | None:
        """Generate a session title from the first substantive user
        message.

        Rules (per spec Section 6):
        1. Clean whitespace, lowercase for classification.
        2. If message is a greeting → return ``None``.
        3. Strip greeting prefix (e.g. "hello, I want..." → "I want...").
        4. If ≤ 50 chars → use as-is with first letter capitalised.
        5. If > 50 chars → truncate to 50 chars + "...".
        6. Validate result ≤ 100 chars.
        """
        cleaned = first_message.strip()
        if not cleaned:
            return None

        lower = cleaned.lower()

        # Is the entire message just a greeting?
        if lower in _GREETINGS:
            return None

        # Remove greeting prefix: "hello, I want to know..." → "I want to know..."
        for greeting in sorted(_GREETINGS, key=len, reverse=True):
            pattern = r"^" + re.escape(greeting) + r"[,\s!.:;]+"
            cleaned = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE).strip()
            if cleaned:
                break

        # If after stripping greeting nothing remains, return None
        if not cleaned:
            return None

        # If message is still too short / greeting-like
        if len(cleaned) <= 5:
            return None

        max_len = settings.AUTO_TITLE_MAX_LENGTH  # 50
        if len(cleaned) <= max_len:
            title = cleaned
        else:
            # Truncate at word boundary if possible
            truncated = cleaned[:max_len].rsplit(" ", 1)[0]
            title = truncated + "..."

        # Capitalise first letter, ensure ≤ 100 chars
        title = title[0].upper() + title[1:] if title else title
        return title[:100] if title else None

    async def maybe_update_title(
        self, session_id: UUID, message_content: str
    ) -> None:
        """Called after storing the first user message in a session.

        Updates the session title only when the current title is
        ``None`` or ``"New Conversation"`` and *message_content*
        qualifies as substantive.
        """
        session = await self.session_repo.get(session_id)
        if session is None:
            return

        # Only update if title hasn't been set or is the placeholder
        if session.title is not None and session.title != "New Conversation":
            return

        title = self.generate_title(message_content)
        if title is None:
            return

        await self.session_repo.update_session(session_id, title=title)
        logger.debug(
            "Auto-generated title for session %s: %s", session_id, title
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_session_and_verify_ownership(
        self, session_id: UUID, user_id: UUID
    ) -> Session:
        """Load a session by ID and verify it belongs to *user_id*.

        Raises:
            NotFoundException: Session does not exist.
            ForbiddenException: Session belongs to a different user.
        """
        session = await self.session_repo.get(session_id)
        if session is None:
            raise NotFoundException("Session", str(session_id))
        if session.user_id != user_id:
            raise ForbiddenException(
                "You don't have access to this session"
            )
        return session
