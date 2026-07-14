"""Leave balance API endpoints (Feature 16).

Direct access to leave balances — GET for the authenticated user,
POST /seed for admin-only data seeding.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user, get_current_user
from app.database import get_db
from app.models.models import User
from app.repositories.leave import LeaveRepository
from app.schemas.leave import LeaveBalanceItem, LeaveBalanceResponse, SeedLeaveResponse
from app.utils.seed import seed_leave_balances as do_seed

router = APIRouter(prefix="/leave", tags=["Leave"])


@router.get("", response_model=LeaveBalanceResponse)
async def get_my_leave_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaveBalanceResponse:
    """Get the authenticated user's leave balance for the current year."""
    repo = LeaveRepository(db)
    balances = await repo.get_balances(current_user.id)

    total_used = sum(b["used"] for b in balances)
    total_remaining = sum(b["remaining"] for b in balances)

    return LeaveBalanceResponse(
        user_id=str(current_user.id),
        year=2026,
        balances=[LeaveBalanceItem(**b) for b in balances],
        total_used=total_used,
        total_remaining=total_remaining,
    )


@router.post("/seed", response_model=SeedLeaveResponse)
async def seed_leave_data(
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> SeedLeaveResponse:
    """Seed leave balance data for all demo users (admin only, idempotent)."""
    count = await do_seed(db)
    return SeedLeaveResponse(
        seeded=count,
        message=f"Seeded {count} leave balance rows for demo users",
    )
