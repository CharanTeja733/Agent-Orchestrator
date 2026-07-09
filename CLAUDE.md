# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Start the full stack (all 4 services)
docker compose up

# Rebuild and restart a single service after code changes
docker compose up --build backend
docker compose up --build frontend

# Access services
# Frontend (nginx):            http://localhost
# Backend API (Swagger):       http://localhost:8000/docs
# Database admin (Adminer):    http://localhost:8080
# Health endpoint:             http://localhost:8000/health
# Admin dashboard:             http://localhost:8000/api/v1/admin/stats/overview
```

There are no test runners, linters, or build scripts. The backend uses `uvicorn --reload` for hot-reload in development.

## Architecture

This is a **FastAPI + PostgreSQL/pgvector + vanilla HTML/JS** multi-agent Q&A orchestrator, deployed with Docker Compose. It routes user queries to domain-specific agents (HR, IT) via an intelligent orchestrator that pre-classifies intent and delegates to the appropriate agent's RAG pipeline.

**4 services** defined in `docker-compose.yml`:
- `db` — `pgvector/pgvector:pg16`, port 5432
- `backend` — FastAPI on Uvicorn, port 8000, depends on db healthy
- `frontend` — `nginx:alpine` serving static files on port 80, proxies `/api/*` to backend with SSE-compatible buffering
- `adminer` — DB management UI on port 8080 (Dracula theme), auto-connects to `db`

### Backend layered architecture

The backend follows **Orchestrator → Agent → Controller → Service → Repository** layering:

```
orchestrator ──► agents/ ──► api/v1/ (routes) ──► services/ ──► repositories/ ──► models/ + PostgreSQL
 classify+route    RAG pipeline   thin — parse only   business logic    data access         persistence
```

| Layer | Directory | Responsibility |
|-------|-----------|---------------|
| Orchestration | `app/services/orchestrator.py` | Pre-classify queries, route to the right domain agent, maintain agent registry. Session-aware follow-up routing. |
| Agents | `app/agents/` | `BaseAgent` — abstract base class with the full RAG pipeline (classify → rewrite → retrieve → confidence gate → generate → store). Domain agents (HR, IT) only define prompts/metadata as class-level attributes — no pipeline logic in subclasses. |
| Presentation | `app/api/v1/` | Thin route handlers — parse requests, call services/orchestrator, return responses. No business logic. |
| Business logic | `app/services/` | Stateless service classes orchestrating repositories, enforcing rules, calling external APIs (Gemini). |
| Data access | `app/repositories/` | `BaseRepository[T]` with CRUD + entity-specific repos. Centralizes all SQL (including raw asyncpg for analytics). |
| ORM models | `app/models/` | SQLAlchemy `DeclarativeBase` models — for querying only, not DDL. |
| Schemas | `app/schemas/` | Pydantic request/response models, split per domain. Separate from ORM models. |
| Cross-cutting | `app/core/` | Security (JWT/bcrypt), FastAPI dependencies, custom exceptions (~15 exception classes), structured logging, background cleanup tasks, classification constants. |
| Middleware | `app/middleware/` | `RequestLoggingMiddleware` — X-Request-ID tracing, request duration, structured log emission. |
| Prompts | `app/prompts/` | LLM prompt templates per agent (hr_agent, it_agent, classifier), separated from service logic. |
| Utilities | `app/utils/` | Seed data, document parsing (PDF/DOCX/TXT), text chunking, embedding wrapper. |

**Startup sequence** (`backend/app/main.py` lifespan): `init_db()` → `run_migrations()` → `seed_users()` → start background cleanup tasks → serve requests. The `init_db()` function enables the `vector` extension, then runs raw SQL `CREATE TABLE IF NOT EXISTS` statements — there is no migration framework. `_run_migrations()` applies schema alterations (new columns, FK constraint fixes) for idempotent upgrades. `seed_users()` inserts 4 demo users and is idempotent (skips if users already exist).

**Database** (`backend/app/database.py`): Dual connection approach — SQLAlchemy 2.0 async (`AsyncSessionLocal` for ORM operations via `get_db()`) and raw `asyncpg` connections (for DDL and direct queries via `get_db_connection()`). The ORM models in `app/models/models.py` mirror the raw DDL tables.

**6 tables** (all UUID PKs, TIMESTAMPTZ):
- `users` — email, hashed_password, full_name, role (employee/manager/hr_admin), department, is_active
- `sessions` — user_id FK, is_active, device_info (JSONB), title, expires_at (24h TTL)
- `messages` — session_id FK (CASCADE), user_id FK, role (user/assistant), content, sources (JSONB), confidence (high/medium/low/none), tokens_used, classification, processing_time_ms
- `feedback` — message_id FK (CASCADE), user_id FK, rating (positive/negative), reason, comment
- `system_logs` — timestamp, level, component, event, user_id/session_id/message_id FKs (nullable), details (JSONB), error_trace
- `hr_documents` — content, embedding (VECTOR(768)), source, page, section, chunk_index, access_level (all/manager/hr_admin), IVFFlat cosine index

### API routes (9 routers)

| Prefix | File | Key endpoints |
|--------|------|---------------|
| `/auth` | `api/v1/auth.py` | register, login, me, refresh |
| `/documents` | `api/v1/documents.py` | upload, upload-bulk, list, stats, detail, delete |
| `/search` | `api/v1/search.py` | vector search, search health |
| `/classify` | `api/v1/classify.py` | LLM-powered message classification |
| `/query` | `api/v1/query.py` | SSE streaming Q&A, test query, query health (legacy — direct HR agent) |
| `/orchestrator` | `api/v1/orchestrator.py` | SSE streaming Q&A (auto-routed), test query, agent discovery, aggregated health |
| `/sessions` | `api/v1/sessions.py` | CRUD + messages + clear-messages |
| `/feedback` | `api/v1/feedback.py` | submit feedback, get by message |
| `/admin` | `api/v1/admin.py` | overview, feedback, query, performance, daily stats + logs |

All routers are aggregated in `app/api/v1/__init__.py` into a single `v1_router` mounted at `/api/v1`.

**Auth**: JWT-based with access tokens (1h, HS256) and refresh tokens (7d) via `python-jose`. Password hashing with passlib/bcrypt. The dependency `get_current_user()` in `app/core/deps.py` decodes the token, verifies `type=access`, and checks `is_active` on the user record. Also provides `get_current_admin_user()` for admin-only routes.

**Configuration** (`backend/app/config.py`): `pydantic-settings.BaseSettings` reads from `.env`. ~40 settings including Gemini model params (temperature, top_p, max_tokens), RAG thresholds (confidence gate, retrieval top_k), and cleanup intervals. Requires `SECRET_KEY` ≥ 32 chars. The `.env` file is gitignored; `.env.example` is the template.

**RAG Pipeline** (`app/agents/base.py`): The `BaseAgent` class provides the full pipeline: classify → rewrite (context-dependent follow-ups) → vector retrieval → confidence gate → Gemini generation (or fallback) → store message pair. The orchestrator pre-classifies for routing and caches the result on the agent, so the agent skips redundant re-classification. SSE streaming via `sse-starlette`, emitting `route` (from orchestrator), `token`, `sources`, `confidence`, `classification`, and `done` events.

**Frontend** (`frontend/`): Single-page app with two views (login, chat). 7 vanilla JS modules loaded as IIFEs (utils, api, auth, streaming, sessions, chat, app). Features: SSE token streaming, session sidebar with CRUD, feedback thumbs-up/down with reason panel, confidence badges, source citations, auto token refresh, responsive CSS. Served via nginx with `proxy_buffering off` for SSE passthrough. The nginx config proxies `/api/*` to `backend:8000` with 3600s timeouts.

## Important patterns

- **Layered architecture**: All new features must follow the Orchestrator → Agent → Controller → Service → Repository pattern. Routes in `api/v1/` are thin (parse → call service/orchestrator → return). Business logic goes in `services/`. Database queries go in `repositories/` (extend `BaseRepository[T]` from `app/repositories/base.py`). Services accept `AsyncSession` directly, not via FastAPI `Depends` — this keeps them usable from scripts/tasks.
- **Agent abstraction**: All domain agents extend `BaseAgent` (`app/agents/base.py`) — an abstract base class providing the complete RAG pipeline. Subclasses only define class-level attributes (prompts, response templates, metadata). **Never override pipeline methods in subclasses** — the base class handles classify → rewrite → retrieve → confidence gate → generate → store. Adding a new agent requires: (1) a `BaseAgent` subclass with prompts, (2) a prompt module in `app/prompts/`, and (3) one entry in `OrchestratorService.AGENT_REGISTRY`.
- **Orchestrator routing**: The `OrchestratorService` pre-classifies every query (using `ClassifierService`) and routes to the appropriate agent. It caches the classification result on the agent to avoid redundant LLM calls. Session-aware follow-ups automatically route to the same agent as the previous message. The `requested_agent` parameter allows explicit agent override.
- **No migration framework**: Tables are created at startup via raw SQL in `database.py`. New tables go in `create_tables()` (use `IF NOT EXISTS` for idempotency). Schema changes to existing tables go in `_run_migrations()` using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` or equivalent guards.
- **No ORM DDL**: The SQLAlchemy models in `app/models/models.py` are for querying only — they don't drive table creation.
- **Async everywhere**: All database access is async (`asyncpg` + SQLAlchemy async). Use `await` on all DB calls; sync code will block the event loop.
- **Spec-driven development**: Feature specs live in `.claude/specs/` (14 specs, features 1–14) and describe what to build before coding. The git history follows these specs sequentially.
- **SSE streaming**: The `/orchestrator/query` and `/query` endpoints stream responses via Server-Sent Events. Tokens arrive as `data: {"type":"token","content":"..."}` events, plus a `route` event from the orchestrator indicating which agent is responding. The nginx config must have `proxy_buffering off` for this to work. The frontend uses `ReadableStream` to consume SSE in real time.
- **Structured logging**: JSON-formatted logs via `app/core/logger.py`. The `RequestLoggingMiddleware` emits a log on every request with duration, status, and X-Request-ID. A `DBLogHandler` persists high-severity logs to the `system_logs` table.
- **Background cleanup**: `SessionCleanup` and `LogCleanup` run as asyncio tasks in the FastAPI lifespan, periodically deactivating expired sessions and purging old logs.
- **Prompt management**: LLM prompts live in `app/prompts/` as separate modules (one per agent), not inline in services. This keeps them versionable and easy to tune.
- **Adminer Dracula theme**: `ADMINER_DESIGN=dracula` is set — don't change it without asking.

## Current state (what's wired vs. planned)

| Done | Not yet built |
|------|---------------|
| Docker environment (4 services) | Tests, linting, CI/CD |
| Database schema (6 tables + migrations) | |
| JWT auth (register/login/me/refresh + admin guard) | |
| Document ingestion (PDF/DOCX/TXT → parse → chunk → embed → store) | |
| Vector search (pgvector cosine similarity with confidence scoring) | |
| Gemini service layer (embeddings, generation, streaming, classification, rewriting) | |
| Query classifier (LLM-powered with heuristic fallback) | |
| RAG pipeline (classify → rewrite → retrieve → confidence gate → generate/fallback) | |
| Session & conversation management (CRUD, auto-title, expiry) | |
| SSE streaming + vanilla JS frontend (nginx, 7 JS modules, responsive CSS) | |
| Feedback & monitoring (thumbs up/down, reason capture, admin analytics dashboard) | |
| Structured logging (JSON format, DB persistence, request tracing) | |
| Admin dashboard (overview, feedback, query, performance, daily stats, logs) | |
| BaseAgent abstraction (reusable RAG pipeline ABC with domain agent subclasses) | |
| HR Agent (policies, benefits, leave — `hr_documents` collection) | |
| IT Agent (VPN, passwords, laptops, software — `it_documents` collection) | |
| Agent Orchestrator (auto-classify → route → delegate, session-aware follow-ups, agent discovery API) | |
