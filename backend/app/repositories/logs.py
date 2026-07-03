"""Repository for system log persistence and retrieval."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import SystemLog


class LogRepository:
    """Data-access layer for the ``system_logs`` table.

    Does *not* extend ``BaseRepository`` — the logging use case is
    append-heavy with nullable FKs and special filtering needs.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> SystemLog:
        """Insert a single log entry."""
        entry = SystemLog(**kwargs)
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def get_logs(
        self,
        level: str | None = None,
        component: str | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        """Retrieve paginated log entries with optional filters.

        Returns:
            ``(logs_as_dicts, total_count)`` tuple.
        """
        conditions = []
        if level is not None:
            conditions.append(SystemLog.level == level.upper())
        if component is not None:
            conditions.append(SystemLog.component == component)
        if before is not None:
            conditions.append(SystemLog.timestamp < before)
        if after is not None:
            conditions.append(SystemLog.timestamp > after)

        # Total count
        count_result = await self.db.execute(
            select(func.count(SystemLog.id)).where(*conditions)
        )
        total = count_result.scalar_one()

        # Paginated results — newest first
        result = await self.db.execute(
            select(SystemLog)
            .where(*conditions)
            .order_by(SystemLog.timestamp.desc())
            .limit(limit)
        )
        logs = result.scalars().all()

        entries = []
        for log in logs:
            entries.append(
                {
                    "timestamp": (
                        log.timestamp.isoformat() if log.timestamp else None
                    ),
                    "level": log.level,
                    "component": log.component,
                    "event": log.event,
                    "details": log.details,
                    "error_trace": log.error_trace,
                }
            )

        return entries, total

    async def cleanup_old_logs(self, retention_days: int) -> int:
        """Delete log entries older than *retention_days* days.

        Returns the number of rows deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        result = await self.db.execute(
            delete(SystemLog).where(SystemLog.timestamp < cutoff)
        )
        await self.db.commit()
        return result.rowcount
