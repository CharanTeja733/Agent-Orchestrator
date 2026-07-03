"""Analytics repository — raw SQL aggregations for admin dashboard (Feature 11).

Uses ``sqlalchemy.text()`` for complex aggregation queries across messages,
feedback, users, and sessions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class AnalyticsRepository:
    """Data-access layer for analytics and monitoring queries."""

    COST_PER_1K_TOKENS = 0.0003  # Simplified Gemini Flash cost estimate

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Period helper
    # ------------------------------------------------------------------

    @staticmethod
    def _period_since(period: str) -> datetime | None:
        """Convert a period string to a ``since`` datetime (or ``None`` for
        'all')."""
        mapping = {
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
            "90d": timedelta(days=90),
        }
        delta = mapping.get(period)
        if delta is None:
            return None
        return datetime.now(timezone.utc) - delta

    def _since_clause(self, since: datetime | None, table_alias: str) -> str:
        """Build a SQL ``WHERE`` fragment for period filtering."""
        if since is None:
            return "TRUE"
        return f"{table_alias}.created_at >= '{since.isoformat()}'"

    # ------------------------------------------------------------------
    # Overview stats
    # ------------------------------------------------------------------

    async def get_overview_stats(self, since: datetime | None) -> dict:
        """Aggregate counts for the admin overview dashboard."""
        since_clause = self._since_clause(since, "m")

        result = await self.db.execute(
            text(f"""
                SELECT
                    COALESCE(SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END), 0)
                        AS total_queries,
                    COALESCE(COUNT(DISTINCT m.session_id), 0)
                        AS total_sessions,
                    COALESCE(COUNT(DISTINCT m.user_id), 0)
                        AS total_users,
                    COALESCE(SUM(CASE WHEN m.role = 'assistant'
                                     THEN COALESCE(m.tokens_used, 0)
                                     ELSE 0 END), 0)
                        AS total_tokens_used
                FROM messages m
                WHERE {since_clause}
            """)
        )
        row = result.one()

        # Active users: distinct users from sessions active in last 7 days
        active_result = await self.db.execute(
            text("""
                SELECT COUNT(DISTINCT user_id)
                FROM sessions
                WHERE last_active >= NOW() - INTERVAL '7 days'
                  AND is_active = TRUE
            """)
        )
        active_users = active_result.scalar_one()

        total_queries = row.total_queries
        total_sessions = row.total_sessions
        total_users = row.total_users
        total_tokens = row.total_tokens_used

        return {
            "total_queries": total_queries,
            "total_sessions": total_sessions,
            "total_users": total_users,
            "active_users": active_users,
            "avg_queries_per_user": (
                round(total_queries / total_users, 1) if total_users else 0.0
            ),
            "avg_queries_per_session": (
                round(total_queries / total_sessions, 1)
                if total_sessions
                else 0.0
            ),
            "total_tokens_used": total_tokens,
            "estimated_cost": round(
                total_tokens * self.COST_PER_1K_TOKENS / 1000, 2
            ),
        }

    # ------------------------------------------------------------------
    # Feedback stats
    # ------------------------------------------------------------------

    async def get_feedback_stats(self, since: datetime | None) -> dict:
        """Aggregate feedback for the feedback analytics dashboard."""
        since_clause = self._since_clause(since, "f")

        # Rating counts
        rating_result = await self.db.execute(
            text(f"""
                SELECT
                    COALESCE(SUM(CASE WHEN f.rating = 'positive'
                                     THEN 1 ELSE 0 END), 0) AS positive_count,
                    COALESCE(SUM(CASE WHEN f.rating = 'negative'
                                     THEN 1 ELSE 0 END), 0) AS negative_count,
                    COUNT(*) AS total_feedback
                FROM feedback f
                WHERE {since_clause}
            """)
        )
        row = rating_result.one()

        # Negative reasons breakdown
        reason_result = await self.db.execute(
            text(f"""
                SELECT reason, COUNT(*) AS cnt
                FROM feedback
                WHERE rating = 'negative'
                  AND reason IS NOT NULL
                  AND {self._since_clause(since, 'feedback')}
                GROUP BY reason
                ORDER BY cnt DESC
            """)
        )
        negative_by_reason = {
            r.reason: r.cnt for r in reason_result.all()
        }

        # Negative top sources — join feedback → messages, extract sources
        top_sources_result = await self.db.execute(
            text(f"""
                SELECT
                    msg.sources AS sources_json,
                    COUNT(*) AS cnt
                FROM feedback f
                JOIN messages msg ON f.message_id = msg.id
                WHERE f.rating = 'negative'
                  AND msg.sources IS NOT NULL
                  AND {self._since_clause(since, 'f')}
                GROUP BY msg.sources
                ORDER BY cnt DESC
                LIMIT 10
            """)
        )
        top_negative_sources: list[dict] = []
        for r in top_sources_result.all():
            sources = r.sources_json or []
            if isinstance(sources, list):
                for source in sources:
                    if isinstance(source, dict):
                        doc = source.get("document", source.get("source", ""))
                        if doc:
                            top_negative_sources.append(
                                {"source": doc, "negative_count": r.cnt}
                            )

        # Deduplicate and limit
        seen: set[str] = set()
        deduped: list[dict] = []
        for s in top_negative_sources:
            if s["source"] not in seen:
                seen.add(s["source"])
                deduped.append(s)
            if len(deduped) >= 10:
                break
        top_negative_sources = deduped

        # Satisfaction by confidence — join feedback → messages
        conf_result = await self.db.execute(
            text(f"""
                SELECT
                    msg.confidence,
                    COUNT(*) AS total,
                    SUM(CASE WHEN f.rating = 'positive'
                             THEN 1 ELSE 0 END) AS positive
                FROM feedback f
                JOIN messages msg ON f.message_id = msg.id
                WHERE msg.confidence IS NOT NULL
                  AND {self._since_clause(since, 'f')}
                GROUP BY msg.confidence
            """)
        )
        avg_satisfaction_by_confidence: dict[str, float] = {}
        for r in conf_result.all():
            if r.total > 0:
                avg_satisfaction_by_confidence[r.confidence or "unknown"] = (
                    round(r.positive / r.total * 100, 1)
                )

        total = row.total_feedback
        positive = row.positive_count
        negative = row.negative_count

        return {
            "total_feedback": total,
            "positive_count": positive,
            "negative_count": negative,
            "satisfaction_rate": (
                round(positive / total * 100, 2) if total else 0.0
            ),
            "negative_by_reason": negative_by_reason,
            "top_negative_sources": top_negative_sources,
            "avg_satisfaction_by_confidence": avg_satisfaction_by_confidence,
        }

    # ------------------------------------------------------------------
    # Query stats
    # ------------------------------------------------------------------

    async def get_query_stats(
        self, since: datetime | None, limit: int = 20
    ) -> dict:
        """Top queries, classification distribution, no-match queries."""
        since_clause = self._since_clause(since, "m")

        # Classification distribution for user messages
        class_result = await self.db.execute(
            text(f"""
                SELECT
                    COALESCE(classification, 'unknown') AS cls,
                    COUNT(*) AS cnt
                FROM messages m
                WHERE role = 'user' AND {since_clause}
                GROUP BY classification
                ORDER BY cnt DESC
            """)
        )
        classification_distribution = {
            r.cls: r.cnt for r in class_result.all()
        }

        # Top queries (deduplicated by content)
        top_result = await self.db.execute(
            text(f"""
                SELECT content, COUNT(*) AS cnt
                FROM messages
                WHERE role = 'user' AND {since_clause}
                GROUP BY content
                ORDER BY cnt DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        top_queries = [
            {"query": r.content, "count": r.cnt, "avg_confidence": "high"}
            for r in top_result.all()
        ]

        # Top no-match queries — user queries whose assistant response had
        # confidence='none' or 'low'
        no_match_result = await self.db.execute(
            text(f"""
                SELECT m_user.content, COUNT(*) AS cnt
                FROM messages m_user
                JOIN messages m_asst
                  ON m_asst.session_id = m_user.session_id
                 AND m_asst.role = 'assistant'
                 AND m_asst.created_at > m_user.created_at
                WHERE m_user.role = 'user'
                  AND (m_asst.confidence = 'none' OR m_asst.confidence = 'low')
                  AND {self._since_clause(since, 'm_user')}
                GROUP BY m_user.content
                ORDER BY cnt DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
        top_no_match_queries = [
            {"query": r.content, "count": r.cnt}
            for r in no_match_result.all()
        ]

        # Total user queries
        total_result = await self.db.execute(
            text(f"""
                SELECT COUNT(*) FROM messages
                WHERE role = 'user' AND {since_clause}
            """)
        )
        total_queries = total_result.scalar_one()

        return {
            "total_queries": total_queries,
            "classification_distribution": classification_distribution,
            "top_queries": top_queries,
            "top_no_match_queries": top_no_match_queries,
        }

    # ------------------------------------------------------------------
    # Performance stats
    # ------------------------------------------------------------------

    async def get_performance_stats(self, since: datetime | None) -> dict:
        """Latency, tokens, and error-rate metrics."""
        since_clause = self._since_clause(since, "m")

        # Per-step timings from system_logs
        step_result = await self.db.execute(
            text(f"""
                SELECT
                    event,
                    AVG((details->>'classification_ms')::float) AS avg_classification_ms,
                    AVG((details->>'retrieval_ms')::float) AS avg_retrieval_ms,
                    AVG((details->>'generation_ms')::float) AS avg_generation_ms
                FROM system_logs
                WHERE event = 'query_processed'
                  AND {self._since_clause(since, 'system_logs')}
                GROUP BY event
            """)
        )
        step_row = step_result.one_or_none()

        # Latency and token stats from messages
        perf_result = await self.db.execute(
            text(f"""
                SELECT
                    AVG(processing_time_ms) AS avg_total_time_ms,
                    AVG(tokens_used) AS avg_tokens,
                    SUM(COALESCE(tokens_used, 0)) AS total_tokens,
                    COUNT(*) AS total_responses
                FROM messages m
                WHERE role = 'assistant' AND {since_clause}
            """)
        )
        perf = perf_result.one()

        # p95 / p99 from messages
        p_result = await self.db.execute(
            text(f"""
                SELECT
                    PERCENTILE_CONT(0.95) WITHIN GROUP
                        (ORDER BY processing_time_ms) AS p95,
                    PERCENTILE_CONT(0.99) WITHIN GROUP
                        (ORDER BY processing_time_ms) AS p99
                FROM messages
                WHERE role = 'assistant'
                  AND processing_time_ms IS NOT NULL
                  AND {since_clause}
            """)
        )
        p_row = p_result.one()

        # Error rate: assistant messages that contain 'error' or 'sorry'
        error_result = await self.db.execute(
            text(f"""
                SELECT COUNT(*) AS errors
                FROM messages
                WHERE role = 'assistant'
                  AND (content ILIKE '%error%'
                       OR content ILIKE '%sorry%unable%')
                  AND {since_clause}
            """)
        )
        error_count = error_result.scalar_one()
        total_responses = perf.total_responses or 1

        total_tokens = perf.total_tokens or 0

        return {
            "avg_total_time_ms": round(perf.avg_total_time_ms or 0, 2),
            "avg_classification_time_ms": round(
                step_row.avg_classification_ms if step_row else 0, 2
            ),
            "avg_retrieval_time_ms": round(
                step_row.avg_retrieval_ms if step_row else 0, 2
            ),
            "avg_generation_time_ms": round(
                step_row.avg_generation_ms if step_row else 0, 2
            ),
            "p95_total_time_ms": round(p_row.p95 or 0, 2),
            "p99_total_time_ms": round(p_row.p99 or 0, 2),
            "avg_tokens_per_query": round(perf.avg_tokens or 0, 1),
            "total_tokens": total_tokens,
            "estimated_cost": round(
                total_tokens * self.COST_PER_1K_TOKENS / 1000, 2
            ),
            "cache_hit_rate": 0,  # always 0 — no caching implemented
            "error_rate": round(error_count / total_responses * 100, 1),
        }

    # ------------------------------------------------------------------
    # Daily stats
    # ------------------------------------------------------------------

    async def get_daily_metric(
        self, since: datetime | None, metric: str
    ) -> list[dict]:
        """Return daily data points for the chosen metric."""
        if metric == "feedback":
            table = "feedback"
            since_clause = self._since_clause(since, "feedback")
            value_expr = "COUNT(*)"
        elif metric == "tokens":
            table = "messages"
            since_clause = self._since_clause(
                since, "messages"
            )
            value_expr = "COALESCE(SUM(tokens_used), 0)"
        elif metric == "users":
            table = "messages"
            since_clause = self._since_clause(since, "messages")
            value_expr = "COUNT(DISTINCT user_id)"
        else:  # queries (default)
            table = "messages"
            since_clause = self._since_clause(since, "messages")
            value_expr = "COUNT(*)"

        result = await self.db.execute(
            text(f"""
                SELECT
                    DATE(created_at)::text AS day,
                    {value_expr} AS value
                FROM {table}
                WHERE {since_clause}
                GROUP BY DATE(created_at)
                ORDER BY day ASC
            """)
        )
        return [{"date": r.day, "value": r.value} for r in result.all()]

    # ------------------------------------------------------------------
    # Feedback listing
    # ------------------------------------------------------------------

    async def get_all_feedback_with_details(
        self,
        rating: str | None = None,
        reason: str | None = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict], int]:
        """Paginated feedback list joined with message and user details."""
        # Validate sort column
        valid_sort = {"created_at": "f.created_at", "rating": "f.rating"}
        sort_col = valid_sort.get(sort_by, "f.created_at")
        sort_dir = "DESC" if sort_order == "desc" else "ASC"

        conditions = ["1=1"]
        params: dict = {"limit": limit, "offset": offset}

        if rating:
            conditions.append("f.rating = :rating")
            params["rating"] = rating
        if reason:
            conditions.append("f.reason = :reason")
            params["reason"] = reason

        where = " AND ".join(conditions)

        # Total count
        count_result = await self.db.execute(
            text(f"""
                SELECT COUNT(*)
                FROM feedback f
                WHERE {where}
            """),
            params,
        )
        total = count_result.scalar_one()

        # Paginated results
        result = await self.db.execute(
            text(f"""
                SELECT
                    f.id,
                    f.message_id,
                    u.email AS user_email,
                    u.full_name AS user_name,
                    f.rating,
                    f.reason,
                    f.comment,
                    f.created_at,
                    m_user.content AS query,
                    LEFT(m_asst.content, 200) AS response_preview,
                    m_asst.sources AS sources_used,
                    m_asst.confidence
                FROM feedback f
                JOIN users u ON f.user_id = u.id
                JOIN messages m_asst ON f.message_id = m_asst.id
                JOIN messages m_user
                  ON m_user.session_id = m_asst.session_id
                 AND m_user.role = 'user'
                 AND m_user.created_at < m_asst.created_at
                 AND m_user.id = (
                     SELECT m2.id FROM messages m2
                     WHERE m2.session_id = m_asst.session_id
                       AND m2.role = 'user'
                       AND m2.created_at < m_asst.created_at
                     ORDER BY m2.created_at DESC
                     LIMIT 1
                 )
                WHERE {where}
                ORDER BY {sort_col} {sort_dir}
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        items = []
        for r in result.all():
            sources_list: list[str] = []
            if r.sources_used and isinstance(r.sources_used, list):
                for s in r.sources_used:
                    if isinstance(s, dict):
                        sources_list.append(
                            s.get("document", s.get("source", ""))
                        )

            items.append(
                {
                    "id": str(r.id),
                    "message_id": str(r.message_id),
                    "user_email": r.user_email,
                    "user_name": r.user_name,
                    "query": r.query or "",
                    "response_preview": r.response_preview or "",
                    "rating": r.rating,
                    "reason": r.reason,
                    "comment": r.comment,
                    "sources_used": sources_list,
                    "confidence": r.confidence,
                    "created_at": (
                        r.created_at.isoformat()
                        if r.created_at
                        else None
                    ),
                }
            )

        return items, total

    # ------------------------------------------------------------------
    # Negative feedback
    # ------------------------------------------------------------------

    async def get_negative_feedback(
        self, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int, int]:
        """Return negative feedback that needs attention.

        Returns:
            ``(items, total_negative, needs_attention)`` tuple.
        """
        # Total negative
        total_result = await self.db.execute(
            text("SELECT COUNT(*) FROM feedback WHERE rating = 'negative'")
        )
        total_negative = total_result.scalar_one()

        # Needs attention: negative + high-confidence
        attn_result = await self.db.execute(
            text("""
                SELECT COUNT(*)
                FROM feedback f
                JOIN messages m ON f.message_id = m.id
                WHERE f.rating = 'negative'
                  AND m.confidence = 'high'
            """)
        )
        needs_attention = attn_result.scalar_one()

        # Paginated list
        result = await self.db.execute(
            text("""
                SELECT
                    f.id,
                    f.message_id,
                    u.email AS user_email,
                    u.full_name AS user_name,
                    f.rating,
                    f.reason,
                    f.comment,
                    f.created_at,
                    m_user.content AS query,
                    LEFT(m_asst.content, 200) AS response_preview,
                    m_asst.sources AS sources_used,
                    m_asst.confidence
                FROM feedback f
                JOIN users u ON f.user_id = u.id
                JOIN messages m_asst ON f.message_id = m_asst.id
                JOIN messages m_user
                  ON m_user.session_id = m_asst.session_id
                 AND m_user.role = 'user'
                 AND m_user.created_at < m_asst.created_at
                 AND m_user.id = (
                     SELECT m2.id FROM messages m2
                     WHERE m2.session_id = m_asst.session_id
                       AND m2.role = 'user'
                       AND m2.created_at < m_asst.created_at
                     ORDER BY m2.created_at DESC
                     LIMIT 1
                 )
                WHERE f.rating = 'negative'
                ORDER BY f.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        )
        items = []
        for r in result.all():
            sources_list: list[str] = []
            if r.sources_used and isinstance(r.sources_used, list):
                for s in r.sources_used:
                    if isinstance(s, dict):
                        sources_list.append(
                            s.get("document", s.get("source", ""))
                        )

            items.append(
                {
                    "id": str(r.id),
                    "message_id": str(r.message_id),
                    "user_email": r.user_email,
                    "user_name": r.user_name,
                    "query": r.query or "",
                    "response_preview": r.response_preview or "",
                    "reason": r.reason or "",
                    "comment": r.comment,
                    "sources_used": sources_list,
                    "confidence": r.confidence,
                    "created_at": (
                        r.created_at.isoformat()
                        if r.created_at
                        else None
                    ),
                }
            )

        return items, total_negative, needs_attention
