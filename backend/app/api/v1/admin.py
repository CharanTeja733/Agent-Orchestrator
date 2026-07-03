"""Admin analytics, feedback management, and log retrieval endpoints.

All endpoints require the ``hr_admin`` role.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user
from app.database import get_db
from app.models.models import User
from app.schemas.admin import (
    DailyStats,
    FeedbackListResponse,
    FeedbackStats,
    LogListResponse,
    NegativeFeedbackResponse,
    OverviewStats,
    PerformanceStats,
    QueryStats,
)
from app.services.analytics import AnalyticsService
from app.services.feedback import FeedbackService

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Stats — overview
# ---------------------------------------------------------------------------


@router.get("/stats/overview", response_model=OverviewStats)
async def get_overview_stats(
    period: str = Query(
        "30d", pattern="^(7d|30d|90d|all)$"
    ),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Overall usage statistics: queries, sessions, users, tokens, cost."""
    service = AnalyticsService(db)
    return await service.get_overview_stats(period)


# ---------------------------------------------------------------------------
# Stats — feedback
# ---------------------------------------------------------------------------


@router.get("/stats/feedback", response_model=FeedbackStats)
async def get_feedback_stats(
    period: str = Query(
        "30d", pattern="^(7d|30d|90d|all)$"
    ),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Feedback analytics: satisfaction rate, breakdowns by reason and
    source."""
    service = AnalyticsService(db)
    return await service.get_feedback_stats(period)


# ---------------------------------------------------------------------------
# Stats — queries
# ---------------------------------------------------------------------------


@router.get("/stats/queries", response_model=QueryStats)
async def get_query_stats(
    period: str = Query(
        "30d", pattern="^(7d|30d|90d|all)$"
    ),
    limit: int = Query(20, ge=1, le=100),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Query analytics: classification distribution, top queries, no-match
    queries."""
    service = AnalyticsService(db)
    return await service.get_query_stats(period, limit)


# ---------------------------------------------------------------------------
# Stats — performance
# ---------------------------------------------------------------------------


@router.get("/stats/performance", response_model=PerformanceStats)
async def get_performance_stats(
    period: str = Query(
        "30d", pattern="^(7d|30d|90d|all)$"
    ),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Performance metrics: latency (avg/p95/p99), tokens, error rate."""
    service = AnalyticsService(db)
    return await service.get_performance_stats(period)


# ---------------------------------------------------------------------------
# Stats — daily
# ---------------------------------------------------------------------------


@router.get("/stats/daily", response_model=DailyStats)
async def get_daily_stats(
    period: str = Query(
        "30d", pattern="^(7d|30d|90d|all)$"
    ),
    metric: str = Query(
        "queries",
        pattern="^(queries|feedback|tokens|users)$",
    ),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Daily trend data for the chosen metric."""
    service = AnalyticsService(db)
    return await service.get_daily_stats(period, metric)


# ---------------------------------------------------------------------------
# Feedback — all
# ---------------------------------------------------------------------------


@router.get("/feedback", response_model=FeedbackListResponse)
async def get_all_feedback(
    rating: str | None = Query(
        None, pattern="^(positive|negative)$"
    ),
    reason: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: str = Query(
        "created_at", pattern="^(created_at|rating)$"
    ),
    sort_order: str = Query(
        "desc", pattern="^(asc|desc)$"
    ),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Paginated list of all feedback with message and user details."""
    repo = AnalyticsService(db).analytics_repo
    items, total = await repo.get_all_feedback_with_details(
        rating=rating,
        reason=reason,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return {
        "feedback": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Feedback — negative
# ---------------------------------------------------------------------------


@router.get(
    "/feedback/negative", response_model=NegativeFeedbackResponse
)
async def get_negative_feedback(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """All negative feedback, with a ``needs_attention`` count for high-
    confidence responses that were rated negatively."""
    repo = AnalyticsService(db).analytics_repo
    items, total_negative, needs_attention = (
        await repo.get_negative_feedback(limit, offset)
    )
    return {
        "negative_feedback": items,
        "total_negative": total_negative,
        "needs_attention": needs_attention,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@router.get("/logs", response_model=LogListResponse)
async def get_logs(
    level: str | None = Query(
        None, pattern="^(ERROR|WARNING|INFO)$"
    ),
    component: str | None = Query(None),
    before: datetime | None = Query(None),
    after: datetime | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """System logs with optional level, component, and time-range filters."""
    service = AnalyticsService(db)
    return await service.get_logs(
        level=level,
        component=component,
        before=before,
        after=after,
        limit=limit,
    )
