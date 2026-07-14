"""Leave-related Pydantic schemas (Feature 16)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LeaveBalanceItem(BaseModel):
    """A single leave-type balance."""

    leave_type: str = Field(
        ..., description="Type of leave: annual, sick, personal"
    )
    total_allocated: int = Field(..., description="Total days allocated")
    used: int = Field(..., description="Days used so far")
    remaining: int = Field(..., description="Days remaining (allocated - used)")


class LeaveBalanceResponse(BaseModel):
    """Full leave balance for an employee."""

    user_id: str = Field(..., description="Employee UUID")
    year: int = Field(..., description="Calendar year")
    balances: list[LeaveBalanceItem] = Field(
        default_factory=list, description="One entry per leave type"
    )
    total_used: int = Field(..., description="Sum of used days across all types")
    total_remaining: int = Field(
        ..., description="Sum of remaining days across all types"
    )


class SeedLeaveResponse(BaseModel):
    """Response from the seed endpoint."""

    seeded: int = Field(..., description="Number of rows inserted")
    message: str = Field(..., description="Human-readable summary")
