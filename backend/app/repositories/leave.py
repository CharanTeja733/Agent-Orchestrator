"""Leave balance repository — data access for leave_balances table (Feature 16)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import LeaveBalance

logger = __import__("logging").getLogger(__name__)


class LeaveRepository:
    """Data access for employee leave balances.

    Follows the standalone repository pattern (like LogRepository) — does
    NOT extend BaseRepository because leave balances are queried by
    user_id + year rather than by PK.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_balances(
        self, user_id: UUID, year: int | None = None
    ) -> list[dict]:
        """Return leave balances for a user, defaulting to the current year.

        Args:
            user_id: The employee's UUID.
            year: Calendar year (defaults to current UTC year).

        Returns:
            A list of dicts, one per leave type::

                [
                  {"leave_type": "annual", "total_allocated": 20, "used": 8, "remaining": 12},
                  {"leave_type": "sick", "total_allocated": 10, "used": 2, "remaining": 8},
                  ...
                ]

            Returns an empty list when no records exist for the user/year.
        """
        if year is None:
            year = datetime.utcnow().year

        result = await self.db.execute(
            select(LeaveBalance).where(
                and_(
                    LeaveBalance.user_id == user_id,
                    LeaveBalance.year == year,
                )
            )
        )
        rows = result.scalars().all()

        return [
            {
                "leave_type": r.leave_type,
                "total_allocated": r.total_allocated,
                "used": r.used,
                "remaining": r.total_allocated - r.used,
            }
            for r in rows
        ]

    async def get_balance_by_type(
        self, user_id: UUID, leave_type: str, year: int | None = None
    ) -> dict | None:
        """Return a single leave-type balance or ``None``."""
        balances = await self.get_balances(user_id, year=year)
        for b in balances:
            if b["leave_type"] == leave_type:
                return b
        return None

    async def seed_leave_data(self, seed_data: list[dict]) -> int:
        """Bulk-insert leave balance rows (idempotent via ON CONFLICT DO NOTHING).

        Each entry in *seed_data* should have:
          ``user_id``, ``leave_type``, ``total_allocated``, ``used``, ``year``
        """
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        count = 0
        for entry in seed_data:
            stmt = (
                pg_insert(LeaveBalance)
                .values(**entry)
                .on_conflict_do_nothing(
                    constraint="leave_balances_user_id_leave_type_year_key"
                )
            )
            result = await self.db.execute(stmt)
            count += result.rowcount
        await self.db.commit()
        return count
