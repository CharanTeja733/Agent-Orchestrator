# Feature 11: Feedback & Monitoring

## 1. Overview

Build the feedback collection system and monitoring dashboard that enables continuous improvement of the HR Q&A Agent. Users can rate responses (thumbs up/down), provide reasons for negative feedback, and admins can view analytics on agent performance, usage patterns, and identify areas for knowledge base improvement.

This establishes the **improvement loop** — without feedback, you cannot know if the agent is providing accurate, helpful answers.

---

## 2. Depends on

- **Feature 1: Project Setup & Docker Environment** — services running
- **Feature 2: Database Schema & Migrations** — feedback table exists
- **Feature 3: User Authentication** — JWT auth, user identity, role-based access
- **Feature 8: RAG Pipeline** — messages have IDs for feedback association
- **Feature 9: Session & Conversation Management** — session context for feedback
- **Feature 10: Streaming & Frontend** — feedback UI components (thumbs up/down buttons)

---

## 3. Routes

| Method | Path | Auth Required | Role Required | Description |
|--------|------|---------------|---------------|-------------|
| `POST` | `/api/v1/feedback` | Yes (JWT) | Any | Submit feedback on a message |
| `GET` | `/api/v1/feedback/{message_id}` | Yes (JWT) | Any | Get feedback for a specific message |
| `GET` | `/api/v1/admin/stats/overview` | Yes (JWT) | `hr_admin` | Overall usage statistics |
| `GET` | `/api/v1/admin/stats/feedback` | Yes (JWT) | `hr_admin` | Feedback analytics summary |
| `GET` | `/api/v1/admin/stats/queries` | Yes (JWT) | `hr_admin` | Query analytics (top queries, classifications) |
| `GET` | `/api/v1/admin/stats/performance` | Yes (JWT) | `hr_admin` | Performance metrics (latency, tokens) |
| `GET` | `/api/v1/admin/stats/daily` | Yes (JWT) | `hr_admin` | Daily usage trends |
| `GET` | `/api/v1/admin/feedback` | Yes (JWT) | `hr_admin` | Paginated list of all feedback |
| `GET` | `/api/v1/admin/feedback/negative` | Yes (JWT) | `hr_admin` | All negative feedback for review |
| `GET` | `/api/v1/admin/logs` | Yes (JWT) | `hr_admin` | System logs for debugging |

---

## 4. Route Specifications

### A. `POST /api/v1/feedback`

**Request Body:**
```json
{
  "message_id": "880e8400-e29b-41d4-a716-446655440004",
  "rating": "negative",
  "reason": "incorrect_information",
  "comment": "The policy says 2 days but our actual policy is 3 days per week"
}
```

**Validation:**
- `message_id`: Required UUID, must reference existing assistant message
- `rating`: Required string, must be `positive` or `negative`
- `reason`: Optional string if rating is `negative`. Must be one of:
  - `incorrect_information` — answer was factually wrong
  - `incomplete_answer` — answer didn't fully address question
  - `unclear_response` — answer was confusing or hard to understand
  - `irrelevant_sources` — sources didn't match the question
  - `outdated_information` — policy has changed since document was indexed
  - `other` — catch-all
- `comment`: Optional string, max 500 characters

**Business Rules:**
- Can only submit feedback for assistant messages (role = 'assistant')
- One feedback per user per message (upsert: update if exists, create if new)
- Can change rating from positive to negative and vice versa

**Success Response (201):**
```json
{
  "message": "Feedback submitted successfully",
  "feedback": {
    "id": "990e8400-e29b-41d4-a716-446655440005",
    "message_id": "880e8400-e29b-41d4-a716-446655440004",
    "rating": "negative",
    "reason": "incorrect_information",
    "comment": "The policy says 2 days but our actual policy is 3 days per week",
    "created_at": "2026-07-01T14:35:00Z"
  }
}
```

**Error Responses:**
- `400` — Invalid rating or reason
- `404` — Message not found
- `400` — Cannot submit feedback for user messages (only assistant)
- `400` — Feedback already exists (if upsert not desired)

---

### B. `GET /api/v1/feedback/{message_id}`

**Success Response (200):**
```json
{
  "message_id": "880e8400-e29b-41d4-a716-446655440004",
  "has_feedback": true,
  "feedback": {
    "id": "990e8400-e29b-41d4-a716-446655440005",
    "rating": "negative",
    "reason": "incorrect_information",
    "comment": "The policy says 2 days but our actual policy is 3 days per week",
    "submitted_by": "john@company.com",
    "created_at": "2026-07-01T14:35:00Z"
  }
}
```

**When no feedback exists:**
```json
{
  "message_id": "880e8400-e29b-41d4-a716-446655440004",
  "has_feedback": false,
  "feedback": null
}
```

---

### C. `GET /api/v1/admin/stats/overview`

**Query Parameters:**
- `period` (optional, string, default "30d"): `7d`, `30d`, `90d`, `all`

**Success Response (200):**
```json
{
  "period": "30d",
  "total_queries": 1250,
  "total_sessions": 87,
  "total_users": 45,
  "active_users": 32,
  "avg_queries_per_user": 27.8,
  "avg_queries_per_session": 14.4,
  "total_tokens_used": 450000,
  "estimated_cost": 0.34,
  "generated_at": "2026-07-01T15:00:00Z"
}
```

---

### D. `GET /api/v1/admin/stats/feedback`

**Query Parameters:**
- `period` (optional, string, default "30d"): `7d`, `30d`, `90d`, `all`

**Success Response (200):**
```json
{
  "period": "30d",
  "total_feedback": 320,
  "positive_count": 268,
  "negative_count": 52,
  "satisfaction_rate": 83.75,
  "negative_by_reason": {
    "incorrect_information": 18,
    "incomplete_answer": 15,
    "unclear_response": 8,
    "irrelevant_sources": 6,
    "outdated_information": 3,
    "other": 2
  },
  "top_negative_sources": [
    {"source": "remote_work_policy_2024.pdf", "negative_count": 8},
    {"source": "leave_policy_2024.pdf", "negative_count": 5},
    {"source": "benefits_guide_2024.pdf", "negative_count": 3}
  ],
  "avg_satisfaction_by_confidence": {
    "high": 92.5,
    "medium": 68.3,
    "low": 25.0
  },
  "generated_at": "2026-07-01T15:00:00Z"
}
```

---

### E. `GET /api/v1/admin/stats/queries`

**Query Parameters:**
- `period` (optional, string, default "30d"): `7d`, `30d`, `90d`, `all`
- `limit` (optional, integer, default 20): Top N queries

**Success Response (200):**
```json
{
  "period": "30d",
  "total_queries": 1250,
  "classification_distribution": {
    "hr_question": 980,
    "follow_up": 180,
    "greeting_only": 55,
    "out_of_domain": 25,
    "bot_question": 10
  },
  "top_queries": [
    {"query": "What is remote work policy?", "count": 45, "avg_confidence": "high"},
    {"query": "How many leave days do I get?", "count": 38, "avg_confidence": "high"},
    {"query": "What are the core hours?", "count": 22, "avg_confidence": "medium"}
  ],
  "top_no_match_queries": [
    {"query": "What is the stock option plan?", "count": 12},
    {"query": "How do I transfer departments?", "count": 8}
  ],
  "generated_at": "2026-07-01T15:00:00Z"
}
```

---

### F. `GET /api/v1/admin/stats/performance`

**Query Parameters:**
- `period` (optional, string, default "30d"): `7d`, `30d`, `90d`, `all`

**Success Response (200):**
```json
{
  "period": "30d",
  "avg_total_time_ms": 1200,
  "avg_classification_time_ms": 180,
  "avg_retrieval_time_ms": 65,
  "avg_generation_time_ms": 920,
  "p95_total_time_ms": 2800,
  "p99_total_time_ms": 4500,
  "avg_tokens_per_query": 320,
  "total_tokens": 450000,
  "estimated_cost": 0.34,
  "cache_hit_rate": 0,
  "error_rate": 1.2,
  "generated_at": "2026-07-01T15:00:00Z"
}
```

---

### G. `GET /api/v1/admin/stats/daily`

**Query Parameters:**
- `period` (optional, string, default "30d"): `7d`, `30d`, `90d`
- `metric` (optional, string, default "queries"): `queries`, `feedback`, `tokens`, `users`

**Success Response (200):**
```json
{
  "period": "30d",
  "metric": "queries",
  "data": [
    {"date": "2026-06-01", "value": 42},
    {"date": "2026-06-02", "value": 55},
    {"date": "2026-06-03", "value": 38},
    "..."
  ],
  "trend": "increasing",
  "trend_percentage": 12.5,
  "generated_at": "2026-07-01T15:00:00Z"
}
```

---

### H. `GET /api/v1/admin/feedback`

**Query Parameters:**
- `rating` (optional, string): Filter by `positive` or `negative`
- `reason` (optional, string): Filter by reason (for negative feedback)
- `limit` (optional, integer, default 50, max 100)
- `offset` (optional, integer, default 0)
- `sort_by` (optional, string, default "created_at"): `created_at`, `rating`
- `sort_order` (optional, string, default "desc")

**Success Response (200):**
```json
{
  "feedback": [
    {
      "id": "uuid",
      "message_id": "uuid",
      "user_email": "john@company.com",
      "user_name": "John Doe",
      "query": "What is remote work policy?",
      "response_preview": "Based on our remote work policy, employees may...",
      "rating": "negative",
      "reason": "incorrect_information",
      "comment": "The policy says 2 days but actual is 3",
      "sources_used": ["remote_work_policy_2024.pdf"],
      "confidence": "high",
      "created_at": "2026-07-01T14:35:00Z"
    }
  ],
  "total": 320,
  "limit": 50,
  "offset": 0
}
```

---

### I. `GET /api/v1/admin/feedback/negative`

**Query Parameters:**
- `limit` (optional, integer, default 20, max 50)
- `offset` (optional, integer, default 0)

**Success Response (200):**
```json
{
  "negative_feedback": [
    {
      "id": "uuid",
      "message_id": "uuid",
      "user_email": "john@company.com",
      "user_name": "John Doe",
      "query": "What is remote work policy?",
      "response_preview": "Based on our remote work policy, employees may...",
      "reason": "incorrect_information",
      "comment": "The policy says 2 days but actual is 3",
      "sources_used": ["remote_work_policy_2024.pdf"],
      "confidence": "high",
      "created_at": "2026-07-01T14:35:00Z"
    }
  ],
  "total_negative": 52,
  "needs_attention": 18,
  "limit": 20,
  "offset": 0
}
```

**`needs_attention` count:** Negative feedback where the original response had `confidence: "high"` — these are most critical as the agent was confident but wrong.

---

### J. `GET /api/v1/admin/logs`

**Query Parameters:**
- `level` (optional, string): `ERROR`, `WARNING`, `INFO` (default: all)
- `component` (optional, string): `classifier`, `search`, `gemini`, `rag`, `session`
- `limit` (optional, integer, default 100, max 500)
- `before` (optional, ISO datetime)
- `after` (optional, ISO datetime)

**Success Response (200):**
```json
{
  "logs": [
    {
      "timestamp": "2026-07-01T14:35:00Z",
      "level": "ERROR",
      "component": "gemini",
      "message": "Gemini API call failed after 3 retries",
      "details": {
        "error": "503 Service Unavailable",
        "model": "gemini-2.5-flash",
        "attempts": 3
      }
    }
  ],
  "total": 15,
  "limit": 100
}
```

---

## 5. Feedback Flow

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    FEEDBACK COLLECTION FLOW                                           │
│                                                                                      │
│  1. USER RECEIVES BOT RESPONSE                                                       │
│     • Message displayed with sources and confidence badge                            │
│     • Feedback buttons appear below message: 👍 👎                                   │
│                                                                                      │
│  2. USER CLICKS 👍 (POSITIVE)                                                        │
│     • Button highlights green                                                        │
│     • POST /api/v1/feedback with rating="positive"                                   │
│     • No reason or comment required                                                  │
│     • Toast: "Thank you for your feedback!"                                          │
│                                                                                      │
│  3. USER CLICKS 👎 (NEGATIVE)                                                        │
│     • Button highlights red                                                          │
│     • Modal/dropdown appears asking for reason:                                      │
│       ○ Incorrect information                                                        │
│       ○ Incomplete answer                                                            │
│       ○ Unclear response                                                             │
│       ○ Irrelevant sources                                                           │
│       ○ Outdated information                                                         │
│       ○ Other                                                                        │
│     • Optional comment field                                                         │
│     • Submit button                                                                  │
│     • POST /api/v1/feedback with rating="negative", reason, comment                  │
│     • Toast: "Thank you! Your feedback helps us improve."                            │
│                                                                                      │
│  4. USER CAN CHANGE FEEDBACK                                                         │
│     • Clicking already-selected button toggles it off (delete feedback)              │
│     • Clicking opposite rating switches (upsert)                                     │
│     • New modal for reason if switching to negative                                  │
│                                                                                      │
│  5. BACKEND PROCESSING                                                               │
│     • Feedback stored in feedbacks table                                             │
│     • Links to message_id, user_id, session_id                                       │
│     • Stored with full context for analysis                                          │
│                                                                                      │
│  6. ADMIN REVIEW                                                                     │
│     • Admins can view all feedback in dashboard                                      │
│     • Negative feedback with high confidence = priority review                       │
│     • Identify documents needing updates                                             │
│     • Track satisfaction trends over time                                            │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Logging System

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    STRUCTURED LOGGING                                                 │
│                                                                                      │
│  Log Format (JSON):                                                                   │
│  {                                                                                    │
│    "timestamp": "2026-07-01T14:35:00.123Z",                                           │
│    "level": "INFO",                                                                   │
│    "component": "rag",                                                                │
│    "event": "query_processed",                                                        │
│    "user_id": "uuid",                                                                 │
│    "session_id": "uuid",                                                              │
│    "message_id": "uuid",                                                              │
│    "details": {                                                                       │
│      "query": "What is remote work?",                                                 │
│      "classification": "hr_question",                                                 │
│      "retrieved_chunks": 3,                                                           │
│      "top_score": 0.92,                                                               │
│      "confidence": "high",                                                            │
│      "tokens_used": 156,                                                              │
│      "total_time_ms": 1200,                                                           │
│      "classification_time_ms": 180,                                                   │
│      "retrieval_time_ms": 65,                                                         │
│      "generation_time_ms": 920                                                        │
│    }                                                                                  │
│  }                                                                                    │
│                                                                                      │
│  Log Levels:                                                                          │
│  • DEBUG: Detailed debugging (disabled in production)                                 │
│  • INFO: Normal operations (queries, feedback, sessions)                              │
│  • WARNING: Degraded but functional (retry succeeded, fallback used)                  │
│  • ERROR: Operation failed (API error, DB error, generation failed)                   │
│  • CRITICAL: System cannot function (DB down, all APIs failing)                       │
│                                                                                      │
│  Log Storage:                                                                         │
│  • Console (stdout): All logs for Docker logs                                        │
│  • File: ERROR and above to app/logs/error.log                                       │
│  • Database: INFO and above to system_logs table (for admin dashboard)               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. New Database Table

### `system_logs`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | Primary key, DEFAULT gen_random_uuid() | Unique log entry |
| timestamp | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | When event occurred |
| level | VARCHAR(20) | NOT NULL | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| component | VARCHAR(50) | NOT NULL | classifier, search, gemini, rag, session, auth |
| event | VARCHAR(100) | NOT NULL | Event type identifier |
| user_id | UUID | NULLABLE, FK → users.id | Related user |
| session_id | UUID | NULLABLE, FK → sessions.id | Related session |
| message_id | UUID | NULLABLE, FK → messages.id | Related message |
| details | JSONB | NULLABLE | Structured event data |
| error_trace | TEXT | NULLABLE | Stack trace for errors |

**Indexes:**
- `INDEX idx_logs_timestamp ON system_logs(timestamp)`
- `INDEX idx_logs_level ON system_logs(level)`
- `INDEX idx_logs_component ON system_logs(component)`

---

## 8. New Folder Structure (This Feature Only)

```
backend/app/
├── api/v1/
│   ├── feedback.py               # Feedback submission/retrieval endpoints
│   └── admin.py                  # Admin stats and logs endpoints
├── services/
│   ├── feedback.py               # Feedback business logic
│   └── analytics.py              # Stats computation logic
├── repositories/
│   ├── feedback.py               # Feedback data access
│   ├── analytics.py              # Analytics queries
│   └── logs.py                   # System logs data access
├── schemas/
│   ├── feedback.py               # Feedback request/response schemas
│   └── admin.py                  # Admin stats response schemas
├── middleware/
│   └── logging.py                # Request logging middleware
└── core/
    └── logger.py                 # Structured logging setup
```

---

## 9. Files to Create

### `app/api/v1/feedback.py`
- Router with prefix="" (full path in main.py), tags=["Feedback"]
- `POST /` — submit feedback (upsert)
- `GET /{message_id}` — get feedback for message
- Protected by `get_current_user`

### `app/api/v1/admin.py`
- Router with prefix="" (full path in main.py), tags=["Admin"]
- All endpoints protected by `get_current_admin_user`
- `GET /stats/overview` — overall usage statistics
- `GET /stats/feedback` — feedback analytics
- `GET /stats/queries` — query analytics
- `GET /stats/performance` — performance metrics
- `GET /stats/daily` — daily trends
- `GET /feedback` — paginated feedback list
- `GET /feedback/negative` — negative feedback for review
- `GET /logs` — system logs

### `app/services/feedback.py`
- `FeedbackService` class
  - `submit_feedback(user_id, message_id, rating, reason, comment) -> dict`
  - `get_feedback(message_id, user_id) -> dict`
  - `_validate_message(message_id) -> Message` — verify it's an assistant message
  - `_upsert_feedback(...)` — create or update

### `app/services/analytics.py`
- `AnalyticsService` class
  - `get_overview_stats(period) -> dict`
  - `get_feedback_stats(period) -> dict`
  - `get_query_stats(period, limit) -> dict`
  - `get_performance_stats(period) -> dict`
  - `get_daily_stats(period, metric) -> dict`

### `app/repositories/feedback.py`
- `FeedbackRepository` class
  - `create(feedback_data) -> Feedback`
  - `get_by_message_and_user(message_id, user_id) -> Optional[Feedback]`
  - `update(feedback_id, data) -> Feedback`
  - `delete(feedback_id) -> None`
  - `get_stats(period) -> dict` — aggregation queries
  - `get_negative_feedback(limit, offset) -> tuple[list, int]`
  - `get_all_with_details(filters, limit, offset) -> tuple[list, int]`

### `app/repositories/analytics.py`
- `AnalyticsRepository` class
  - `get_query_counts(period) -> dict`
  - `get_user_stats(period) -> dict`
  - `get_token_usage(period) -> dict`
  - `get_classification_distribution(period) -> dict`
  - `get_top_queries(period, limit) -> list`
  - `get_top_no_match_queries(period, limit) -> list`
  - `get_daily_metric(period, metric) -> list`
  - `get_performance_stats(period) -> dict`
  - `get_confidence_distribution(period) -> dict`

### `app/repositories/logs.py`
- `LogRepository` class
  - `create(log_data) -> SystemLog`
  - `get_logs(filters, limit, offset) -> tuple[list, int]`
  - `cleanup_old_logs(retention_days) -> int`

### `app/schemas/feedback.py`
- `FeedbackCreate` — message_id, rating, reason (optional), comment (optional)
- `FeedbackResponse` — id, message_id, rating, reason, comment, created_at
- `FeedbackDetail` — includes user_email, user_name, query, response_preview, sources_used
- `MessageFeedbackResponse` — message_id, has_feedback, feedback (nullable)

### `app/schemas/admin.py`
- `OverviewStats` — period, total_queries, total_sessions, total_users, active_users, etc.
- `FeedbackStats` — period, total_feedback, positive_count, negative_count, satisfaction_rate, etc.
- `QueryStats` — period, total_queries, classification_distribution, top_queries, etc.
- `PerformanceStats` — period, avg times, p95/p99, tokens, error_rate
- `DailyStats` — period, metric, data points, trend
- `FeedbackListResponse` — feedback list, total, limit, offset
- `NegativeFeedbackResponse` — negative_feedback list, total_negative, needs_attention
- `LogEntry` — timestamp, level, component, message, details
- `LogListResponse` — logs list, total, limit

### `app/middleware/logging.py`
- `RequestLoggingMiddleware` — Starlette middleware
  - Logs every request: method, path, user_id, status_code, duration_ms
  - Logs errors with full traceback
  - Generates request_id (UUID) for tracing
  - Attaches request_id to response headers (X-Request-ID)

### `app/core/logger.py`
- `setup_logging()` — configure structured JSON logging
- `get_logger(name)` — get configured logger instance
- `StructuredFormatter` — JSON log formatter
- `DBLogHandler` — custom handler that writes to system_logs table

---

## 10. Files to Change

### `app/main.py`
```python
from app.api.v1 import feedback, admin
from app.middleware.logging import RequestLoggingMiddleware

# Add routers
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Feedback"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])

# Add middleware
app.add_middleware(RequestLoggingMiddleware)

# On startup: setup logging
@app.on_event("startup")
async def startup():
    setup_logging()
```

### `app/services/rag.py`
- Add structured logging calls at each pipeline step
- Log query, classification, retrieval results, confidence, tokens, timing

### `app/config.py`
Add monitoring settings:
```python
# Logging
LOG_LEVEL: str = "INFO"
LOG_RETENTION_DAYS: int = 30

# Analytics
DEFAULT_STATS_PERIOD: str = "30d"

# Feedback
FEEDBACK_REASONS: list = [
    "incorrect_information",
    "incomplete_answer",
    "unclear_response",
    "irrelevant_sources",
    "outdated_information",
    "other"
]
```

### `frontend/js/chat.js`
- Wire up feedback buttons to API calls
- Handle feedback submission states (submitted, changed)
- Show feedback reason modal for negative ratings
- Persist feedback state in message data

### `frontend/css/style.css`
- Style feedback buttons (default, selected-positive, selected-negative)
- Style feedback reason modal/dropdown
- Style admin dashboard components (if building admin UI)

---

## 11. SQL Migration

Add `system_logs` table creation to database initialization:

```sql
CREATE TABLE IF NOT EXISTS system_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level VARCHAR(20) NOT NULL,
    component VARCHAR(50) NOT NULL,
    event VARCHAR(100) NOT NULL,
    user_id UUID REFERENCES users(id),
    session_id UUID REFERENCES sessions(id),
    message_id UUID REFERENCES messages(id),
    details JSONB,
    error_trace TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON system_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_level ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_component ON system_logs(component);
```

---

## 12. Dependencies

All already in `requirements.txt` — no new packages required.

---

## 13. Rules for Implementation

- **One feedback per user per message**: Upsert pattern (create or update)
- **Only on assistant messages**: Cannot submit feedback for user messages
- **Reason required for negative**: Validation enforces this
- **Feedback is mutable**: Users can change rating and reason
- **Admin-only stats**: All admin endpoints require hr_admin role
- **Structured logging**: JSON format for machine readability
- **Request ID propagation**: Every request gets unique ID for tracing
- **Log to multiple outputs**: Console (Docker), file (errors), database (queryable)
- **Performance impact**: Logging and feedback should add < 5ms overhead
- **Privacy**: Logs exclude full message content in details (store message_id reference)
- **Retention**: Auto-cleanup logs older than 30 days
- **Service returns dicts**: Framework-agnostic
- **Thin controllers**: Routes only parse, validate, call service

---

## 14. Admin Dashboard (Frontend)

If building admin UI (optional — can use API-only for now):

### Admin Page (`#admin`)
- Accessible only to users with `hr_admin` role
- Navigation tabs:
  - **Overview**: Key metrics cards (total queries, users, satisfaction rate)
  - **Feedback**: Table of all feedback with filters
  - **Queries**: Top queries, no-match queries
  - **Performance**: Latency charts, token usage
  - **Logs**: System logs with level/component filters

### Overview Cards:
- Total Queries (with trend indicator)
- Active Users (with percentage)
- Satisfaction Rate (with gauge)
- Avg Response Time (with sparkline)
- Total Tokens Used (with cost estimate)

---

## 15. Verification Steps

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}' | jq -r '.access_token')

ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"admin123"}' | jq -r '.access_token')

# 1. Submit positive feedback (replace MESSAGE_ID)
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message_id": "MESSAGE_ID", "rating": "positive"}'

# 2. Submit negative feedback
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "message_id": "MESSAGE_ID",
    "rating": "negative",
    "reason": "incorrect_information",
    "comment": "Policy actually says 3 days"
  }'

# 3. Get feedback for message
curl -X GET http://localhost:8000/api/v1/feedback/MESSAGE_ID \
  -H "Authorization: Bearer $TOKEN"

# 4. Admin: overview stats
curl -X GET "http://localhost:8000/api/v1/admin/stats/overview?period=30d" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 5. Admin: feedback stats
curl -X GET "http://localhost:8000/api/v1/admin/stats/feedback?period=30d" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 6. Admin: query stats
curl -X GET "http://localhost:8000/api/v1/admin/stats/queries?period=30d&limit=10" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 7. Admin: performance stats
curl -X GET "http://localhost:8000/api/v1/admin/stats/performance?period=30d" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 8. Admin: daily trends
curl -X GET "http://localhost:8000/api/v1/admin/stats/daily?period=7d&metric=queries" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 9. Admin: negative feedback list
curl -X GET "http://localhost:8000/api/v1/admin/feedback/negative?limit=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 10. Admin: system logs
curl -X GET "http://localhost:8000/api/v1/admin/logs?level=ERROR&limit=50" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## 16. Definition of Done

### Feedback Collection:
- [ ] `POST /api/v1/feedback` accepts valid feedback
- [ ] Positive feedback requires only rating
- [ ] Negative feedback requires reason selection
- [ ] One feedback per user per message (upsert)
- [ ] Cannot submit feedback for user messages (only assistant)
- [ ] Users can change their feedback
- [ ] `GET /api/v1/feedback/{message_id}` returns feedback status
- [ ] Feedback UI wired up in frontend (👍/👎 buttons)

### Admin Stats:
- [ ] Overview stats endpoint returns correct counts
- [ ] Feedback stats shows satisfaction rate and breakdowns
- [ ] Query stats shows top queries and classification distribution
- [ ] Performance stats shows latency percentiles
- [ ] Daily stats shows trends over time
- [ ] Negative feedback list shows items needing attention
- [ ] All admin endpoints restricted to hr_admin role

### Logging:
- [ ] Request logging middleware captures all requests
- [ ] Structured JSON log format
- [ ] Logs stored in system_logs table
- [ ] Log retrieval endpoint works for admins
- [ ] Log cleanup removes entries older than 30 days
- [ ] Request IDs propagated for tracing

### Integration:
- [ ] RAG pipeline logs each step with structured data
- [ ] Errors logged with full context
- [ ] Performance timings logged per component

### Frontend:
- [ ] Feedback buttons functional on all bot messages
- [ ] Negative feedback modal with reason selection
- [ ] Visual feedback on submission (highlight, toast)
- [ ] Feedback state persists within session

---

## 17. Final Project Structure (All Features Complete)

```
hr-agent/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── sample_docs/
│   ├── remote_work_policy.txt
│   └── leave_policy.txt
├── database/
│   └── init.sql
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── api/v1/
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   ├── documents.py
│       │   ├── search.py
│       │   ├── classify.py
│       │   ├── query.py
│       │   ├── sessions.py
│       │   ├── feedback.py
│       │   └── admin.py
│       ├── services/
│       │   ├── __init__.py
│       │   ├── ingestion.py
│       │   ├── search.py
│       │   ├── gemini.py
│       │   ├── classifier.py
│       │   ├── rag.py
│       │   ├── session.py
│       │
