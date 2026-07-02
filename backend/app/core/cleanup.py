"""Background session cleanup task (Feature 9).

Runs every ``SESSION_CLEANUP_INTERVAL_HOURS`` and hard-deletes sessions
that expired more than ``SESSION_CLEANUP_AFTER_DAYS`` ago.

Reference: ``.claude/specs/09-session-and-conversation-management.md``
Section 7 (Session Expiry Logic).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.repositories.session import SessionRepository

logger = logging.getLogger(__name__)


class SessionCleanup:
    """Background task that periodically purges stale expired sessions.

    Usage in ``main.py`` lifespan::

        cleanup = SessionCleanup(AsyncSessionLocal)
        await cleanup.start_background_task()
        # ... app runs ...
        await cleanup.stop_background_task()
    """

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def run_cleanup(self) -> int:
        """Hard-delete sessions expired > ``SESSION_CLEANUP_AFTER_DAYS``
        days ago.

        Returns the count of deleted sessions.
        """
        async with self.session_factory() as db:
            repo = SessionRepository(db)
            cutoff = datetime.now(timezone.utc) - timedelta(
                days=settings.SESSION_CLEANUP_AFTER_DAYS
            )
            deleted = await repo.delete_expired_sessions(cutoff)
            if deleted > 0:
                logger.info(
                    "Session cleanup: deleted %d expired sessions "
                    "(cutoff: %s)",
                    deleted,
                    cutoff.isoformat(),
                )
            return deleted

    async def start_background_task(self) -> None:
        """Start the periodic cleanup loop as a background asyncio task."""
        interval_seconds = settings.SESSION_CLEANUP_INTERVAL_HOURS * 3600
        logger.info(
            "Session cleanup task starting (interval=%dh, "
            "retention=%dd after expiry)",
            settings.SESSION_CLEANUP_INTERVAL_HOURS,
            settings.SESSION_CLEANUP_AFTER_DAYS,
        )

        async def _loop() -> None:
            while not self._stop_event.is_set():
                try:
                    await self.run_cleanup()
                except Exception:
                    logger.exception(
                        "Session cleanup iteration failed — will retry"
                    )
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=interval_seconds
                    )
                    break  # Stop event was set
                except asyncio.TimeoutError:
                    continue  # Timeout → run again

        self._task = asyncio.create_task(_loop())

    async def stop_background_task(self) -> None:
        """Gracefully stop the cleanup loop."""
        if self._task is None:
            return
        logger.info("Stopping session cleanup task...")
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("Session cleanup task stopped")
