# Feature 14: Agent Orchestrator

## 1. Overview

Build the **Agent Orchestrator** — a single unified entry point that automatically routes user queries to the appropriate domain agent (HR, IT, and future agents). Currently, users must know which endpoint to use (`/api/v1/query` for HR, `/api/v1/it/query` for IT). The orchestrator eliminates this friction by pre-classifying each query and delegating to the right agent.

The orchestrator uses the existing `ClassifierService` (Feature 7) for intent detection, the existing `BaseAgent` pattern (Feature 12) for delegation, and session-based message history for follow-up routing.

Existing endpoints (`/query`, `/it/query`) remain fully functional — the orchestrator is an **additional** layer, not a replacement.

---

## 2. Depends on

- **Feature 12: BaseAgent Pattern** — `BaseAgent`, `HRAgent` exist with `agent_name` attribute
- **Feature 13: IT Agent** — `ITAgent` exists with `agent_name="it"`
- **Feature 7: Query Classifier** — `ClassifierService` classifies into 6 categories including `it_question`
- **Feature 8: RAG Pipeline** — Full streaming/non-streaming pipeline via agents
- **Feature 9: Session Management** — Sessions with conversation history for follow-up routing

---

## 3. Routes

### New Endpoints

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `POST` | `/api/v1/orchestrator/query` | Yes (JWT) | Unified streaming query — auto-routes to best agent |
| `POST` | `/api/v1/orchestrator/query/test` | Yes (JWT) | Unified non-streaming test — returns complete pipeline result |
| `GET` | `/api/v1/orchestrator/agents` | No | List all registered agents with capabilities |
| `GET` | `/api/v1/orchestrator/query/health` | No | Aggregate health of all agents |

### Unchanged Endpoints (Backward Compatible)

| Method | Path | Status |
|--------|------|--------|
| `POST` | `/api/v1/query` | Unchanged — direct HR agent access |
| `POST` | `/api/v1/query/test` | Unchanged |
| `GET` | `/api/v1/query/health` | Unchanged |
| `POST` | `/api/v1/it/query` | Unchanged — direct IT agent access |
| `POST` | `/api/v1/it/query/test` | Unchanged |
| `GET` | `/api/v1/it/query/health` | Unchanged |

---

## 4. Route Specifications

### A. `POST /api/v1/orchestrator/query` (Streaming)

**Request Body:**
```json
{
  "query": "How do I reset my password?",
  "session_id": null,
  "agent_name": null
}
```

- `query` (required): string, 1-2000 chars
- `session_id` (optional): UUID for conversation continuity
- `agent_name` (optional): string — forces routing to a specific agent (`"hr"` or `"it"`)

**Response:** SSE stream with an additional `route` event before the agent's token stream:

```
event: route
data: {"agent_name": "it", "display_name": "IT Support"}

event: token
data: {"token": "To"}

event: token
data: {"token": " reset"}

... (continues) ...

event: sources
data: {"sources": [{"document": "Password Reset Guide", ...}]}

event: done
data: {"message_id": "uuid", "session_id": "uuid", "agent_name": "it", "confidence": "high", "tokens_used": 180, "processing_time_ms": 980}
```

**Error events:**
```
event: error
data: {"error": "Unknown agent 'finance'. Valid agents: ['hr', 'it']", "detail": "...", "error_type": "routing_failed"}
```

### B. `POST /api/v1/orchestrator/query/test` (Non-streaming)

**Request Body:** Same as streaming

**Success Response (200):**
```json
{
  "query": "How do I reset my password?",
  "agent_name": "it",
  "rewritten_query": null,
  "classification": "it_question",
  "classification_confidence": 0.95,
  "retrieved_chunks": [...],
  "retrieval_count": 3,
  "overall_confidence": "high",
  "answer": "To reset your password...",
  "sources": [...],
  "tokens_used": 180,
  "processing_time_ms": 980,
  "pipeline_steps": {...}
}
```

### C. `GET /api/v1/orchestrator/agents`

**Response (200):**
```json
{
  "agents": [
    {
      "name": "hr",
      "display_name": "HR Agent",
      "description": "Answers HR-related questions about company policies, leave, benefits, and more",
      "collection_name": "hr_documents"
    },
    {
      "name": "it",
      "display_name": "IT Support",
      "description": "Helps with technical issues including VPN, laptops, software, passwords, and network",
      "collection_name": "it_documents"
    }
  ],
  "default_agent": "hr"
}
```

### D. `GET /api/v1/orchestrator/query/health`

**Success Response (200):**
```json
{
  "status": "healthy",
  "agents": {
    "hr": {
      "status": "healthy",
      "components": {"database": "connected", ...},
      "documents_indexed": 120,
      "active_sessions": 5
    },
    "it": {
      "status": "healthy",
      "components": {"database": "connected", ...},
      "documents_indexed": 45,
      "active_sessions": 3
    }
  },
  "default_agent": "hr"
}
```

---

## 5. Architecture

```text
                    ┌─────────────────────────────────────────┐
                    │           Frontend / Client              │
                    │   POST /api/v1/orchestrator/query        │
                    └────────────────┬────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │      Orchestrator Router (api/v1/)       │
                    │  POST /orchestrator/query                │
                    │  POST /orchestrator/query/test           │
                    │  GET  /orchestrator/agents               │
                    │  GET  /orchestrator/query/health         │
                    └────────────────┬────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────────────┐
                    │         OrchestratorService              │
                    │                                         │
                    │  route_query(query, user, session,       │
                    │              override)                    │
                    │    │                                    │
                    │    ├── 1. Override check                 │
                    │    ├── 2. ClassifierService.classify()   │
                    │    ├── 3. Follow-up session lookup       │
                    │    └── 4. Create agent & delegate        │
                    │        ┌──────┬──────┐                  │
                    │        │  hr  │  it  │                  │
                    │        └──┬───┴──┬───┘                  │
                    │           │      │                       │
                    │           ▼      ▼                       │
                    │     ┌────────┐ ┌────────┐               │
                    │     │HRAgent │ │ITAgent │               │
                    │     └───┬────┘ └───┬────┘               │
                    └─────────┼──────────┼────────────────────┘
                              │          │
                              ▼          ▼
              (Each agent runs its full pipeline:
               classify → rewrite → retrieve → gate → generate/fallback → store)
                              │          │
                              ▼          ▼
                    ┌─────────────────────────────────────────┐
                    │       SSE Stream → Client               │
                    │  route → token* → sources → done        │
                    └─────────────────────────────────────────┘
```

---

## 6. Routing Logic

### Classification-to-Agent Mapping

| Classification | Route To |
|---|---|
| `hr_question` | HRAgent |
| `it_question` | ITAgent |
| `follow_up` | Same agent as last assistant message in session (fallback: default agent) |
| `greeting_only` | Default agent (configurable, default: `"hr"`) |
| `bot_question` | Default agent |
| `out_of_domain` | Default agent |
| `agent_name` in request | Specified agent (bypasses auto-routing) |

### Resolution Order

```
1. agent_name override in request body  → specified agent (skip classification)
2. ClassifierService.classify(query)
   3a. hr_question                      → HRAgent
   3b. it_question                      → ITAgent
   3c. follow_up                        → last session agent (or default)
   3d. greeting_only / bot_question / out_of_domain → default agent
```

### Follow-Up Session Lookup

When classification is `follow_up`:
1. If `session_id` is provided, query the `messages` table for the most recent message with `role='assistant'` and a non-null `agent_name`
2. Return that message's `agent_name`
3. If no session_id or no matching message, fall back to `default_agent`

---

## 7. OrchestratorService Design

### Class: `OrchestratorService`

**Agent Registry** (class-level dict):
```python
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "hr": HRAgent,
    "it": ITAgent,
}
```

**Classification → Agent mapping** (class-level dict):
```python
CLASSIFICATION_AGENT_MAP: dict[str, str] = {
    "hr_question": "hr",
    "it_question": "it",
}
```

**Default agent**: `"hr"`

**Agent descriptions** (class-level dict):
```python
AGENT_DESCRIPTIONS: dict[str, str] = {
    "hr": "Answers HR-related questions about company policies, leave, benefits, and more",
    "it": "Helps with technical issues including VPN, laptops, software, passwords, and network",
}
```

**Public methods:**
- `route_query(query, user, session_id, requested_agent) → tuple[BaseAgent, str]` — determine which agent to use
- `get_available_agents() → list[dict]` — return metadata for all registered agents
- `health_check() → dict` — aggregate health of all agents

**Private methods:**
- `_quick_classify(query, session_id) → str` — run ClassifierService to classify
- `_classification_to_agent(classification, session_id) → str` — map classification to agent name
- `_get_session_agent(session_id) → str` — find last agent from session history
- `_create_agent(agent_name) → BaseAgent` — factory to instantiate an agent

---

## 8. Database Changes

### Migration: `agent_name` column on `messages`

```sql
ALTER TABLE messages ADD COLUMN IF NOT EXISTS agent_name VARCHAR(50);
```

### ORM Model: `Message.agent_name`

```python
class Message(Base):
    # ... existing columns ...
    agent_name = Column(String(50))  # NEW
```

### `BaseAgent._store_messages()` update

Pass `agent_name=self.agent_name` when creating messages:

```python
msg = await self.message_repo.create_message(
    ...,
    agent_name=self.agent_name,  # NEW — enables session-based routing
)
```

### `MessageRepository` updates

- `create_message()` — accept optional `agent_name` parameter
- `get_last_agent_name(session_id) → Optional[str]` — new method for follow-up routing

---

## 9. Files to Create

```
backend/app/schemas/orchestrator.py    # Orchestrator-specific Pydantic schemas
backend/app/services/orchestrator.py   # OrchestratorService — routing + delegation
backend/app/api/v1/orchestrator.py     # 4 API endpoints
.claude/specs/14-agent-orchestrator.md # This spec
```

---

## 10. Files to Change

```
backend/app/database.py                # Add agent_name column migration
backend/app/models/models.py           # Add agent_name to Message model
backend/app/agents/base.py             # Pass agent_name in _store_messages()
backend/app/repositories/message.py    # Add get_last_agent_name() + update create_message()
backend/app/api/v1/__init__.py         # Register orchestrator router
```

---

## 11. Dependencies

No new packages. All existing dependencies sufficient.

---

## 12. Rules for Implementation

- **Separate endpoint**: The orchestrator is a NEW endpoint — existing `/query` and `/it/query` endpoints continue to work identically
- **Orchestrator pre-classifies for routing only**: Each agent still runs its full pipeline including its own classification
- **Agent registry is centralised**: Adding a new agent = one dict entry in `AGENT_REGISTRY`
- **`agent_name` on messages**: Required for follow-up routing; optional on creation (nullable)
- **Thin controllers**: Routes parse, create OrchestratorService, call method, return response
- **No cross-agent search**: Routes to exactly one agent per query
- **Route event**: Emit a `route` SSE event before the agent's token stream so the frontend can display which agent is responding
- **Agent override validation**: Invalid `agent_name` returns a clear 400 error with valid options

---

## 13. Verification Steps

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}' | jq -r '.access_token')

# 1. List available agents
curl http://localhost:8000/api/v1/orchestrator/agents | jq .

# 2. Orchestrator health
curl http://localhost:8000/api/v1/orchestrator/query/health | jq .

# 3. HR question auto-routed
curl -X POST http://localhost:8000/api/v1/orchestrator/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is the remote work policy?"}' | jq .
# Expected: agent_name="hr", meaningful HR answer

# 4. IT question auto-routed
curl -X POST http://localhost:8000/api/v1/orchestrator/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "My VPN is not connecting"}' | jq .
# Expected: agent_name="it", meaningful IT answer

# 5. Explicit agent override
curl -X POST http://localhost:8000/api/v1/orchestrator/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is remote work policy?", "agent_name": "it"}' | jq .

# 6. Invalid agent override
curl -X POST http://localhost:8000/api/v1/orchestrator/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "test", "agent_name": "finance"}'
# Expected: 400 error — "Unknown agent"

# 7. Follow-up routing — same agent as previous message
# Send IT question first, then follow-up in same session

# 8. Streaming via orchestrator
curl -X POST http://localhost:8000/api/v1/orchestrator/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  -d '{"query": "What is the leave policy?"}' \
  --no-buffer
# Expected: route event, then token stream

# 9. Backward compatibility
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is remote work policy?"}'
# Expected: works exactly as before

curl -X POST http://localhost:8000/api/v1/it/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "VPN not connecting"}'
# Expected: works exactly as before
```

---

## 14. Definition of Done

### Orchestrator Service:
- [ ] `OrchestratorService` exists in `backend/app/services/orchestrator.py`
- [ ] `route_query()` correctly maps classifications to agents (hr_question → hr, it_question → it)
- [ ] `route_query()` handles explicit `agent_name` override (skips classification)
- [ ] Invalid `agent_name` returns a clear 400 error
- [ ] Follow-up routing checks session history for last agent
- [ ] `get_available_agents()` returns all registered agents with metadata
- [ ] `health_check()` aggregates all agents' health
- [ ] Agent registry extensible (add new agent = one dict entry)

### API Endpoints:
- [ ] `POST /api/v1/orchestrator/query` — streaming SSE, emits `route` event first
- [ ] `POST /api/v1/orchestrator/query/test` — non-streaming, returns `agent_name` field
- [ ] `GET /api/v1/orchestrator/agents` — lists available agents with names, descriptions
- [ ] `GET /api/v1/orchestrator/query/health` — aggregated health check
- [ ] All endpoints follow thin-controller pattern

### Database:
- [ ] `agent_name VARCHAR(50)` column exists on `messages` table
- [ ] Migration is idempotent (`ADD COLUMN IF NOT EXISTS`)
- [ ] `Message` ORM model includes `agent_name` field
- [ ] `BaseAgent._store_messages()` writes `agent_name=self.agent_name`
- [ ] `MessageRepository.get_last_agent_name(session_id)` works correctly

### Backward Compatibility:
- [ ] `POST /api/v1/query` (HR) still works unchanged
- [ ] `POST /api/v1/it/query` (IT) still works unchanged
- [ ] `GET /api/v1/query/health` and `GET /api/v1/it/query/health` unchanged
- [ ] Frontend still functions with existing endpoints
- [ ] `HRAgent.create()` and `ITAgent.create()` still work

### Architecture:
- [ ] OrchestratorService follows existing service pattern (constructor takes db + api_key)
- [ ] API router is thin (no business logic)
- [ ] No circular imports
- [ ] No modification to BaseAgent pipeline logic (only `_store_messages` signature)
- [ ] Agents remain self-contained (run their own full pipeline including classification)
- [ ] No new dependencies required
