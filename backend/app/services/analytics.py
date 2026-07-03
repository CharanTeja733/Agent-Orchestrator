"""Analytics business logic — stat computation and period normalisation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.analytics import AnalyticsRepository
from app.repositories.logs import LogRepository


class AnalyticsService:
    """Orchestrates analytics queries for the admin dashboard.

    Each public method:
    1. Parses and normalises the ``period`` parameter.
    2. Delegates raw aggregation to ``AnalyticsRepository``.
    3. Adds ``generated_at`` and the normalised ``period`` string.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analytics_repo = AnalyticsRepository(db)
        self.log_repo = LogRepository(db)

    # ------------------------------------------------------------------
    # Period helper
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_period(period: str) -> tuple[str, datetime | None]:
        """Normalise period string and return a ``since`` datetime."""
        valid = {"7d", "30d", "90d", "all"}
        period = period if period in valid else "30d"
        since = AnalyticsRepository._period_since(period)
        return period, since

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def get_overview_stats(self, period: str = "30d") -> dict:
        """Overall usage statistics for the admin dashboard."""
        period, since = self._parse_period(period)
        stats = await self.analytics_repo.get_overview_stats(since)
        stats["period"] = period
        stats["generated_at"] = datetime.now(timezone.utc)
        return stats

    async def get_feedback_stats(self, period: str = "30d") -> dict:
        """Feedback analytics — satisfaction rate, breakdowns."""
        period, since = self._parse_period(period)
        stats = await self.analytics_repo.get_feedback_stats(since)
        stats["period"] = period
        stats["generated_at"] = datetime.now(timezone.utc)
        return stats

    async def get_query_stats(
        self, period: str = "30d", limit: int = 20
    ) -> dict:
        """Query analytics — top queries, classification distribution."""
        period, since = self._parse_period(period)
        stats = await self.analytics_repo.get_query_stats(since, limit)
        stats["period"] = period
        stats["generated_at"] = datetime.now(timezone.utc)
        return stats

    async def get_performance_stats(self, period: str = "30d") -> dict:
        """Performance metrics — latency, tokens, error rate."""
        period, since = self._parse_period(period)
        stats = await self.analytics_repo.get_performance_stats(since)
        stats["period"] = period
        stats["generated_at"] = datetime.now(timezone.utc)
        return stats

    async def get_daily_stats(
        self, period: str = "30d", metric: str = "queries"
    ) -> dict:
        """Daily trend data for the chosen metric."""
        period, since = self._parse_period(period)
        data = await self.analytics_repo.get_daily_metric(since, metric)

        # Compute trend
        trend, trend_pct = self._compute_trend(data)

        return {
            "period": period,
            "metric": metric,
            "data": data,
            "trend": trend,
            "trend_percentage": trend_pct,
            "generated_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def _compute_trend(data: list[dict]) -> tuple[str, float]:
        """Compare the last half of *data* to the first half.

        Returns:
            ``(trend_label, percentage_change)``.
        """
        if len(data) < 4:
            return ("stable", 0.0)

        mid = len(data) // 2
        first_half = data[:mid]
        second_half = data[mid:]

        first_avg = sum(d["value"] for d in first_half) / max(len(first_half), 1)
        second_avg = sum(d["value"] for d in second_half) / max(len(second_half), 1)

        if first_avg == 0:
            if second_avg == 0:
                return ("stable", 0.0)
            return ("increasing", 100.0)

        pct = round((second_avg - first_avg) / first_avg * 100, 1)
        if pct > 1:
            trend = "increasing"
        elif pct < -1:
            trend = "decreasing"
        else:
            trend = "stable"

        return trend, pct

    # -- Logs -----------------------------------------------------------------

    async def get_logs(
        self,
        level: str | None = None,
        component: str | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
        limit: int = 100,
    ) -> dict:
        """Retrieve system logs with optional filters."""
        entries, total = await self.log_repo.get_logs(
            level=level,
            component=component,
            before=before,
            after=after,
            limit=limit,
        )
        return {"logs": entries, "total": total, "limit": limit}
