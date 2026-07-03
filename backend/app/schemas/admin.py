"""Admin analytics and monitoring response schemas (Feature 11)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


class OverviewStats(BaseModel):
    period: str
    total_queries: int
    total_sessions: int
    total_users: int
    active_users: int
    avg_queries_per_user: float
    avg_queries_per_session: float
    total_tokens_used: int
    estimated_cost: float
    generated_at: datetime


# ---------------------------------------------------------------------------
# Feedback stats
# ---------------------------------------------------------------------------


class FeedbackStats(BaseModel):
    period: str
    total_feedback: int
    positive_count: int
    negative_count: int
    satisfaction_rate: float
    negative_by_reason: dict[str, int]
    top_negative_sources: list[dict]
    avg_satisfaction_by_confidence: dict[str, float]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Query stats
# ---------------------------------------------------------------------------


class QueryStats(BaseModel):
    period: str
    total_queries: int
    classification_distribution: dict[str, int]
    top_queries: list[dict]
    top_no_match_queries: list[dict]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Performance stats
# ---------------------------------------------------------------------------


class PerformanceStats(BaseModel):
    period: str
    avg_total_time_ms: float
    avg_classification_time_ms: float
    avg_retrieval_time_ms: float
    avg_generation_time_ms: float
    p95_total_time_ms: float
    p99_total_time_ms: float
    avg_tokens_per_query: float
    total_tokens: int
    estimated_cost: float
    cache_hit_rate: int
    error_rate: float
    generated_at: datetime


# ---------------------------------------------------------------------------
# Daily stats
# ---------------------------------------------------------------------------


class DailyStats(BaseModel):
    period: str
    metric: str
    data: list[dict]
    trend: str
    trend_percentage: float
    generated_at: datetime


# ---------------------------------------------------------------------------
# Feedback listing
# ---------------------------------------------------------------------------


class FeedbackDetail(BaseModel):
    id: UUID
    message_id: UUID
    user_email: str
    user_name: str
    query: str
    response_preview: str
    rating: str
    reason: Optional[str] = None
    comment: Optional[str] = None
    sources_used: list[str]
    confidence: Optional[str] = None
    created_at: datetime


class FeedbackListResponse(BaseModel):
    feedback: list[FeedbackDetail]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Negative feedback
# ---------------------------------------------------------------------------


class NegativeFeedbackItem(BaseModel):
    id: UUID
    message_id: UUID
    user_email: str
    user_name: str
    query: str
    response_preview: str
    reason: str
    comment: Optional[str] = None
    sources_used: list[str]
    confidence: Optional[str] = None
    created_at: datetime


class NegativeFeedbackResponse(BaseModel):
    negative_feedback: list[NegativeFeedbackItem]
    total_negative: int
    needs_attention: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# System logs
# ---------------------------------------------------------------------------


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    component: str
    event: str
    details: Optional[dict] = None
    error_trace: Optional[str] = None


class LogListResponse(BaseModel):
    logs: list[LogEntry]
    total: int
    limit: int
