# Multi-Agent Q&A Orchestrator

An AI-powered multi-agent Q&A system built with **FastAPI**, **PostgreSQL/pgvector**, **LangGraph**, and **Google Gemini**. Users ask questions in natural language and are automatically routed to the right domain agent (HR or IT) via a LangGraph-powered orchestrator — with streaming responses, conversation history, and an admin analytics dashboard.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│ Orchestrator │────▶│  HR Agent    │──▶ Gemini
│  (nginx +    │     │  (classify + │     │  (policies,  │    (LLM API)
│  vanilla JS) │     │   route)     │     │   benefits)  │
└──────────────┘     │              │     ├──────────────┤
                     │              │────▶│  IT Agent    │──▶ Gemini
                     └──────┬───────┘     │  (tech help, │    (LLM API)
                            │             │   passwords) │
                     ┌──────▼───────┐     └──────────────┘
                     │  PostgreSQL  │
                     │  + pgvector  │
                     └──────┬───────┘
                     ┌──────▼───────┐
                     │   Adminer    │
                     │  (DB Admin)  │
                     └──────────────┘
```

Two **LangGraph StateGraphs** power the system — an **Orchestrator Graph** (classify → route → load agent config) followed by an **Agent Graph** (RAG pipeline: classify → retrieve → confidence gate → generate/fallback → store). The orchestrator caches its classification result in the agent's state, avoiding redundant LLM calls. Each agent runs its own RAG pipeline with domain-specific prompts, document collections, and fallback responses. Follow-up questions are automatically routed to the same agent as the previous message.

**4 Docker services:**
| Service | Technology | Port | Purpose |
|---------|-----------|------|---------|
| `db` | pgvector/pgvector:pg16 | 5432 | Vector database with cosine similarity search |
| `backend` | FastAPI + Uvicorn | 8000 | REST API, orchestrator, RAG pipeline, SSE streaming |
| `frontend` | nginx:alpine | 80 | Static file serving + API proxy with SSE support |
| `adminer` | Adminer 4.8.1 | 8080 | Database management UI (Dracula theme) |

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- A [Google Gemini API key](https://aistudio.google.com/apikey)

### Setup

1. **Clone and configure environment:**

```bash
git clone <repo-url>
cd agent-orchestrator
cp .env.example .env
```

2. **Edit `.env` — set your Gemini API key and a strong secret key:**

```env
GEMINI_API_KEY=your_actual_gemini_api_key
SECRET_KEY=a_strong_random_secret_key_at_least_32_characters
```

3. **Start all services:**

```bash
docker compose up
```

4. **Access the application:**

| URL | Description |
|-----|-------------|
| http://localhost | Chat interface (login → ask questions) |
| http://localhost:8000/docs | Swagger API documentation |
| http://localhost:8000/health | Health check endpoint |
| http://localhost:8080 | Adminer (DB management) |

### Demo Users

Four users are seeded on first startup:

| Email | Password | Role | Department |
|-------|----------|------|-------------|
| `admin@company.com` | `password123` | hr_admin | HR |
| `john@company.com` | `password123` | employee | Engineering |
| `sarah@company.com` | `password123` | manager | Sales |
| `priya@company.com` | `password123` | employee | HR |

## Features

### LangGraph-Powered Orchestration
- **Two StateGraphs** — an Orchestrator Graph routes queries; per-agent Agent Graphs run the full RAG pipeline with typed state flowing through nodes
- **Automatic routing** — queries are classified and routed to the right domain agent (HR or IT) via conditional edges
- **Agent discovery API** — frontend can list available agents and their capabilities
- **Pluggable agents** — adding a new agent requires only a new agent class + one registry entry; the config extractor auto-discovers attributes
- **Session-aware follow-ups** — follow-up questions route to the same agent as the previous message via state-based edge conditions
- **Explicit agent override** — users (or the frontend) can target a specific agent directly, bypassing classification
- **Classification caching** — the orchestrator classifies once and passes the result through state, saving an LLM call

### Chat & Q&A
- **Streaming responses** — answers stream token-by-token via Server-Sent Events (SSE)
- **Source citations** — every answer includes the documents it drew from
- **Confidence scoring** — answers rated high/medium/low/none with visual badges
- **Context-aware follow-ups** — the system rewrites follow-up questions against conversation history (e.g., "What about vacation?" → "What is the company's vacation policy?")
- **Fallback handling** — gracefully responds when no relevant documents are found

### Domain Agents
| Agent | Handles | Document Collection |
|-------|---------|-------------------|
| **HR Agent** | Policies, leave, benefits, remote work, payroll | `hr_documents` |
| **IT Agent** | VPN, laptops, software, passwords, email, network | `it_documents` |

### Document Management
- Upload policy/technical documents (PDF, DOCX, TXT) via API
- Automatic chunking, embedding (Gemini `text-embedding-001`, 768-dim), and pgvector storage
- Access-level controls (`all`, `manager`, `hr_admin`)
- Separate document collections per agent domain

### Session & Conversation Management
- Persistent chat sessions with auto-generated titles
- Session sidebar with create/rename/delete/clear
- 24-hour session expiry with background cleanup

### Feedback & Monitoring
- Thumbs-up/down feedback on every answer with reason capture
- Admin analytics dashboard with overview, feedback, query, and performance stats
- Structured JSON logging with X-Request-ID request tracing

### Security
- JWT-based authentication (access tokens 1h, refresh tokens 7d)
- bcrypt password hashing
- Role-based access control (employee, manager, hr_admin)

## API Endpoints

| Prefix | Key Endpoints |
|--------|--------------|
| `/api/v1/auth` | register, login, me, refresh |
| `/api/v1/documents` | upload, upload-bulk, list, stats, detail, delete |
| `/api/v1/search` | vector search, search health |
| `/api/v1/classify` | LLM-powered message classification |
| `/api/v1/query` | SSE streaming Q&A, test query, query health (legacy — direct HR agent) |
| `/api/v1/orchestrator` | SSE streaming Q&A (auto-routed), test query, agent discovery, aggregated health |
| `/api/v1/sessions` | CRUD, messages, clear-messages |
| `/api/v1/feedback` | submit feedback, get by message |
| `/api/v1/admin` | overview, feedback, query, performance, daily stats, logs |

Full interactive docs at http://localhost:8000/docs.

## Backend Architecture

The backend follows a **Graph → Service → Repository** layered pattern with **LangGraph StateGraphs**:

```
API Route (orchestrator.py)
  │
  ├─ Orchestrator Graph (StateGraph — 4 nodes)
  │     check_override → quick_classify → map_to_agent → load_agent_config
  │
  ├─ "route" SSE event
  │
  └─ Agent Graph (StateGraph — 9 nodes, per-agent RAG pipeline)
        load_context → classify_message
          → [direct]   respond_directly → END
          → [retrieval] rewrite_query? → retrieve → confidence_gate
              → [fallback]  generate_fallback → END
              → [generate]  generate_response → store_and_finish → END
```

| Layer | Directory | Responsibility |
|-------|-----------|---------------|
| Graphs | `backend/app/graph/` | Two compiled LangGraph StateGraphs — Orchestrator Graph (routing) and Agent Graph (RAG pipeline). Node functions, conditional edges, streaming bridge, agent config registry. |
| Agents | `backend/app/agents/` | `BaseAgent` (ABC) + domain agents (HR, IT) — now used as config holders; their class attributes are introspected by the graph's config extractor. |
| Presentation | `backend/app/api/v1/` | Thin route handlers — build state, invoke graphs, yield SSE events. No business logic. |
| Business Logic | `backend/app/services/` | Stateless services orchestrating repositories, calling Gemini. Called by graph node functions. |
| Data Access | `backend/app/repositories/` | `BaseRepository[T]` with CRUD + entity-specific queries. Centralizes all SQL. |
| ORM Models | `backend/app/models/` | SQLAlchemy models (querying only, not DDL) |
| Schemas | `backend/app/schemas/` | Pydantic request/response models |
| Cross-cutting | `backend/app/core/` | Security, dependencies, exceptions, logging, cleanup |
| Prompts | `backend/app/prompts/` | LLM prompt templates per agent (versionable, separate from logic) |

### LangGraph Pipeline (replaces BaseAgent.process_query)

The RAG pipeline is now a compiled LangGraph `StateGraph` with typed state flowing through 9 nodes. Node functions (`backend/app/graph/nodes.py`) call existing services (`GeminiService`, `SearchService`, `ClassifierService`, `SessionService`) directly — no new wrappers.

SSE streaming is preserved via an **asyncio.Queue producer/consumer pattern**: the agent graph runs as a background `asyncio.Task` while node functions push `token` events to the queue in real time. The API route yields events from the queue, producing the exact same `route → token* → sources → done` contract the frontend expects.

### Agent Configuration (BaseAgent subclasses as config holders)

Domain agents extend `BaseAgent` and define only **class-level attributes** (prompts, response templates, metadata). The `_extract_agent_config()` function in `backend/app/graph/agent_registry.py` introspects these classes at import time to produce flat config dicts consumed by `AgentState`.

```
class HRAgent(BaseAgent):
    agent_name = "hr"
    display_name = "HR Assistant"
    collection_name = "hr_documents"
    system_prompt = "..."
    # ... prompts, templates, fallback responses ...
```

Adding a new agent requires: (1) a new `BaseAgent` subclass with prompts, (2) a prompt module in `prompts/`, and (3) one entry in `agent_registry.py`.

### RAG Pipeline (Agent StateGraph)

The Agent Graph executes the full RAG pipeline with conditional branching:

```
START
  │
  ▼
load_context ──► Get/create session, load conversation history
  │
  ▼
classify_message ──► Use cached classification from orchestrator, or classify fresh
  │
  ├─ [requires_retrieval=False] → respond_directly → END
  │     (greetings, bot questions, out-of-domain)
  │
  ├─ [requires_rewriting=True] → rewrite_query → retrieve_context
  └─ [no rewriting needed] → retrieve_context
        │
        ▼
      apply_confidence_gate
        │
        ├─ [generate] → generate_response (Gemini streaming) → store_and_finish → END
        └─ [fallback] → generate_fallback (template-based) → END
```

Classification result is cached from the Orchestrator Graph via shared state — no redundant LLM calls.

## Project Structure

```
agent-orchestrator/
├── backend/
│   ├── app/
│   │   ├── graph/             # LangGraph StateGraphs (9 files)
│   │   │   ├── state.py              # TypedDict schemas: OrchestratorState, AgentState
│   │   │   ├── orchestrator_graph.py # Orchestrator Graph builder (4 nodes)
│   │   │   ├── agent_graph.py        # Agent Graph builder (9 nodes)
│   │   │   ├── nodes.py              # 13 node functions + extracted helpers
│   │   │   ├── conditional_edges.py   # Edge routing callables
│   │   │   ├── streaming.py          # asyncio.Queue SSE bridge
│   │   │   ├── agent_registry.py     # Config extractor from agent classes
│   │   │   └── test_handler.py       # Non-streaming test endpoint
│   │   ├── agents/            # Agent abstraction + domain agents (config holders)
│   │   │   ├── base.py        # BaseAgent ABC (pipeline methods deprecated)
│   │   │   ├── hr_agent.py    # HR domain agent (policies, benefits)
│   │   │   └── it_agent.py    # IT domain agent (tech support)
│   │   ├── api/v1/            # Route handlers (9 routers)
│   │   │   ├── orchestrator.py  # Graph invocation: orch graph → route event → agent graph
│   │   │   └── ...
│   │   ├── core/              # Security, deps, exceptions, logging, cleanup
│   │   ├── middleware/        # Request logging middleware
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── prompts/           # LLM prompt templates (hr_agent, it_agent, classifier)
│   │   ├── repositories/      # Data access layer
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # Business logic (OrchestratorService deprecated)
│   │   └── utils/             # Seed data, document parsing, chunking, embeddings
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── index.html             # Single-page app (login + chat views)
│   ├── css/style.css          # Responsive styles
│   ├── js/                    # 7 vanilla JS modules (IIFE pattern)
│   │   ├── app.js             # App initialization & routing
│   │   ├── api.js             # HTTP client wrapper
│   │   ├── auth.js            # Login/register/token management
│   │   ├── chat.js            # Chat UI & message rendering
│   │   ├── streaming.js       # SSE stream consumption
│   │   ├── sessions.js        # Session sidebar CRUD
│   │   └── utils.js           # Helpers (formatting, sanitization)
│   ├── nginx.conf             # Static serving + /api/* proxy (SSE-compatible)
│   └── Dockerfile
├── database/
│   └── init.sql               # Reference DDL (6 tables, indexes, seed data)
├── docker-compose.yml         # 4-service orchestration
├── .env.example               # Configuration template
└── CLAUDE.md                  # Developer guide
```

## Configuration

All settings are in `.env` (see `.env.example`). Key parameters:

| Setting | Default | Description |
|---------|---------|-------------|
| `CHUNK_SIZE` | 1000 | Document chunk size in characters |
| `CHUNK_OVERLAP` | 200 | Overlap between chunks |
| `TOP_K_RETRIEVAL` | 5 | Number of document chunks retrieved per query |
| `MIN_RETRIEVAL_SCORE` | 0.5 | Minimum cosine similarity threshold |
| `HIGH_CONFIDENCE_THRESHOLD` | 0.75 | Threshold for "high" confidence badge |
| `SESSION_EXPIRY_HOURS` | 24 | Session TTL |
| `LOG_RETENTION_DAYS` | 30 | System log retention period |

## Development

```bash
# Rebuild and restart a single service after code changes
docker compose up --build backend
docker compose up --build frontend

# The backend uses uvicorn --reload for hot-reload in development
# Frontend files are served directly by nginx — refresh the browser
```

The backend starts up with this sequence: `init_db()` → `run_migrations()` → `seed_users()` → background cleanup tasks → serve requests. Tables are created via raw SQL (`CREATE TABLE IF NOT EXISTS`) — there is no migration framework. Schema changes are applied idempotently in `_run_migrations()`.

## Database

6 tables (all UUID PKs, TIMESTAMPTZ):

| Table | Purpose |
|-------|---------|
| `users` | Employee accounts with roles (employee/manager/hr_admin) |
| `sessions` | Chat sessions with 24h expiry |
| `messages` | Conversation history with sources, confidence, classification, agent_name |
| `feedback` | Thumbs-up/down ratings with reasons |
| `system_logs` | Structured application logs (JSONB details) |
| `hr_documents` | Document chunks with pgvector embeddings (768-dim, IVFFlat index) |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend Framework | FastAPI (Python 3.12) |
| Orchestration | LangGraph StateGraphs (typed state, conditional edges) |
| Database | PostgreSQL 16 + pgvector |
| LLM | Google Gemini (embeddings + generation) |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Reverse Proxy | nginx (Alpine) |
| Containerization | Docker Compose |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Streaming | Server-Sent Events (sse-starlette + asyncio.Queue bridge) |
| Agent Pattern | ABC with pluggable domain agents (config holders) |

## License

MIT
