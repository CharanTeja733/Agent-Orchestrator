# Feature 12: Refactor HR Agent into Reusable BaseAgent Pattern

## 1. Overview

Refactor the existing HR RAG pipeline into a generic, reusable `BaseAgent` class. The HR agent becomes one instance of this pattern. This establishes the **agent abstraction layer** — every future domain agent (IT, Finance, Facilities) will extend `BaseAgent` and only override agent-specific configurations (prompts, collection name, responses).

No new functionality is added. The `/api/v1/query` endpoint must work exactly as before after this refactor.

---

## 2. Depends on

- **Features 1-11** — Complete HR Q&A Agent with all features working
- All existing tests must pass after refactor

---

## 3. Routes

No new routes. No route changes. Existing routes must work identically.

| Method | Path | Status |
|--------|------|--------|
| `POST` | `/api/v1/query` | Unchanged — delegates to HR agent |
| `POST` | `/api/v1/query/test` | Unchanged |
| `GET` | `/api/v1/query/health` | Unchanged |

---

## 4. What Gets Refactored

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    REFACTOR MAP: BEFORE → AFTER                                       │
│                                                                                      │
│  BEFORE                                 AFTER                                         │
│  ──────                                 ─────                                         │
│  app/services/rag.py                    app/agents/base.py (NEW)                      │
│  (RAGService class with                 (BaseAgent abstract class with all            │
│   all pipeline logic)                    shared pipeline logic)                        │
│                                         │                                            │
│                                         └── app/agents/hr_agent.py (NEW)             │
│                                              (HRAgent extends BaseAgent,             │
│                                               overrides prompts & config)            │
│                                                                                      │
│  app/prompts/rag.py                     app/prompts/hr_agent.py (RENAMED)            │
│  (HR-specific prompts)                  (HR prompts, same content)                    │
│                                                                                      │
│  app/services/rag.py                    app/services/rag.py (THIN WRAPPER)            │
│  (all logic)                            (imports HRAgent, delegates calls)            │
│                                                                                      │
│  app/api/v1/query.py                    app/api/v1/query.py (MINIMAL CHANGE)          │
│  (uses RAGService)                      (uses HRAgent via thin wrapper)              │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. BaseAgent Design

### What Goes Into BaseAgent (Shared Logic)

These are identical for every domain agent:

| Method | Description |
|--------|-------------|
| `process_query(query, user, session_id)` | Full streaming pipeline entry point |
| `process_query_test(query, user, session_id)` | Non-streaming debug version |
| `classify_intent(message, history)` | Calls ClassifierService (Feature 7) |
| `retrieve_context(query, user_role)` | Calls SearchService with agent's collection |
| `apply_confidence_gate(search_results)` | Same thresholds for all agents |
| `build_prompt(query, context, history, confidence)` | Uses agent's system_prompt |
| `format_context_for_prompt(chunks)` | Formats chunks with source citations |
| `format_history_for_prompt(messages)` | Formats conversation history |
| `get_fallback_response(confidence_tier, chunks)` | "I don't know" responses |
| `get_direct_response(classification, user_name)` | Uses agent's response templates |
| `store_messages(user_id, session_id, ...)` | Database persistence |
| `build_sources_from_chunks(chunks)` | Source extraction for response |

### What Each Agent Overrides (Agent-Specific)

| Attribute | Type | Description |
|-----------|------|-------------|
| `agent_name` | `str` | Machine identifier: "hr", "it", "finance" |
| `display_name` | `str` | Human-readable: "HR Agent", "IT Support" |
| `collection_name` | `str` | pgvector table: "hr_documents", "it_documents" |
| `system_prompt` | `str` | Full system prompt for answer generation |
| `greeting_response` | `str` | Template for greeting_only classification |
| `bot_intro_response` | `str` | Template for bot_question classification |
| `out_of_domain_response` | `str` | Template for out_of_domain classification |
| `confidence_thresholds` | `dict` | Optional override for confidence gates |

---

## 6. BaseAgent Abstract Structure

```
BaseAgent (ABC)
├── __init__(db, gemini_service, search_service, classifier_service)
│   • Stores shared services
│   • Validates that subclass defined required attributes
│
├── process_query(query, user, session_id) → AsyncIterator[str]
│   • Full pipeline: classify → route → retrieve → gate → generate → store
│   • Identical for all agents
│
├── process_query_test(query, user, session_id) → dict
│   • Non-streaming version for debugging
│   • Identical for all agents
│
├── _classify_intent(message, history) → dict
│   • Delegates to ClassifierService
│   • Identical for all agents
│
├── _retrieve_context(query, user_role) → list[dict]
│   • Calls SearchService with self.collection_name
│   • Collection name is the only difference between agents
│
├── _apply_confidence_gate(results) → tuple[str, list]
│   • Uses self.confidence_thresholds or defaults
│   • Identical logic, configurable thresholds
│
├── _build_prompt(query, context, history, confidence) → str
│   • Uses self.system_prompt
│   • Identical structure, different prompt content
│
├── _get_fallback_response(tier, chunks) → str
│   • Uses agent-specific fallback text
│
├── _get_direct_response(classification, user_name) → str
│   • Returns self.greeting_response / self.bot_intro_response / self.out_of_domain_response
│
├── _format_context_for_prompt(chunks) → str
│   • Static method — identical for all agents
│
├── _format_history_for_prompt(messages) → str
│   • Static method — identical for all agents
│
├── _store_messages(...) → dict
│   • Static method — identical for all agents
│
└── _build_sources_from_chunks(chunks) → list
    • Static method — identical for all agents
```

---

## 7. Files to Create

### `app/agents/__init__.py`
- Empty file, makes `agents` a package

### `app/agents/base.py`

**Purpose:** Abstract base class for all domain agents.

**Class: `BaseAgent(ABC)`**

**Constructor:**
- Takes `db: AsyncSession`, `gemini_service: GeminiService`, `search_service: SearchService`, `classifier_service: ClassifierService`
- Validates that subclass has defined: `agent_name`, `display_name`, `collection_name`, `system_prompt`, `greeting_response`, `bot_intro_response`, `out_of_domain_response`
- Raises `ValueError` if any required attribute is missing

**Abstract Attributes (must be set by subclass):**
- `agent_name: str` — e.g., "hr"
- `display_name: str` — e.g., "HR Agent"
- `collection_name: str` — e.g., "hr_documents"
- `system_prompt: str`
- `greeting_response: str`
- `bot_intro_response: str`
- `out_of_domain_response: str`

**Optional Attributes (with defaults):**
- `confidence_thresholds: dict` — `{"high": 0.75, "medium": 0.50, "low": 0.30}`
- `top_k_retrieval: int` — default 5
- `max_history_messages: int` — default 6
- `max_completion_tokens: int` — default 1024
- `response_temperature: float` — default 0.3

**Methods (all moved from `app/services/rag.py`):**
- `async process_query(query, user, session_id) -> AsyncIterator[str]`
- `async process_query_test(query, user, session_id) -> dict`
- `async _classify_intent(message, history) -> dict`
- `async _retrieve_context(query, user_role) -> list[dict]`
- `_apply_confidence_gate(results) -> tuple[str, list]`
- `_build_prompt(query, context, history, confidence) -> str`
- `_get_fallback_response(tier, chunks) -> str`
- `_get_direct_response(classification, user_name) -> str`
- `_format_context_for_prompt(chunks) -> str` (static)
- `_format_history_for_prompt(messages) -> str` (static)
- `async _store_messages(user_id, session_id, query, response, sources, confidence, classification, tokens) -> dict` (static)
- `_build_sources_from_chunks(chunks) -> list` (static)

---

### `app/agents/hr_agent.py`

**Purpose:** HR domain agent — minimal code, mostly configuration.

**Class: `HRAgent(BaseAgent)`**

Only defines the abstract attributes:

```python
class HRAgent(BaseAgent):
    agent_name = "hr"
    display_name = "HR Agent"
    collection_name = "hr_documents"
    
    system_prompt = # HR system prompt (moved from app/prompts/rag.py)
    greeting_response = # HR greeting (moved from app/prompts/rag.py)
    bot_intro_response = # HR bot intro (moved from app/prompts/rag.py)
    out_of_domain_response = # HR out of domain (moved from app/prompts/rag.py)
```

No other methods. All logic is inherited from `BaseAgent`.

---

### `app/prompts/hr_agent.py`

**Purpose:** HR-specific prompt templates (renamed from `app/prompts/rag.py`).

Contains the exact same content as the current `app/prompts/rag.py`:
- `SYSTEM_PROMPT`
- `USER_PROMPT_TEMPLATE`
- `HARD_FALLBACK_RESPONSE`
- `SOFT_FALLBACK_RESPONSE`
- `GREETING_RESPONSE`
- `BOT_QUESTION_RESPONSE`
- `OUT_OF_DOMAIN_RESPONSE`
- `LOW_CONFIDENCE_DISCLAIMER`

---

## 8. Files to Change

### `app/services/rag.py` — Convert to Thin Wrapper

**Before:** Contains all RAG pipeline logic (~300+ lines)

**After:** Thin compatibility wrapper

```python
"""
Thin compatibility wrapper.
Delegates to HRAgent for backward compatibility.
"""

from app.agents.hr_agent import HRAgent

# Re-export for any code that imports from here
# All actual logic now lives in app/agents/base.py and app/agents/hr_agent.py
```

### `app/api/v1/query.py` — Minimal Change

Update imports:
```python
# Before
from app.services.rag import RAGService

# After
from app.agents.hr_agent import HRAgent
```

Update usage:
```python
# Before
rag_service = RAGService(db, gemini_service, search_service, classifier_service)
result = await rag_service.process_query(...)

# After
hr_agent = HRAgent(db, gemini_service, search_service, classifier_service)
result = await hr_agent.process_query(...)
```

Route paths, request/response schemas, and behavior remain identical.

### `app/prompts/rag.py` — Rename to `app/prompts/hr_agent.py`

Content unchanged. Just the file moves to reflect it's HR-specific.

---

## 9. Files to Create

```
app/agents/__init__.py
app/agents/base.py              # BaseAgent abstract class
app/agents/hr_agent.py          # HRAgent (extends BaseAgent)
app/prompts/hr_agent.py         # HR prompts (renamed from rag.py)
```

---

## 10. Files to Change

```
app/services/rag.py             # Convert to thin wrapper
app/api/v1/query.py             # Update imports, use HRAgent
```

---

## 11. Files to Remove

```
app/prompts/rag.py              # Renamed to hr_agent.py
```

---

## 12. Dependencies

No new packages. All existing dependencies remain.

---

## 13. Rules for Implementation

- **No functionality changes**: Every existing API must work identically
- **BaseAgent is the single source of pipeline logic**: No duplication between agents
- **Agent classes are configuration, not logic**: They only define prompts and names
- **Thin wrapper preserves backward compatibility**: `app/services/rag.py` still importable
- **Static methods where possible**: Formatting, source building are agent-agnostic
- **Abstract attributes validated**: Constructor checks subclass defined everything
- **No hardcoded "hr" in BaseAgent**: Use `self.collection_name`, `self.agent_name`
- **Database operations unchanged**: Same tables, same queries
- **Streaming unchanged**: SSE event format identical

---

## 14. Verification Steps

```bash
# 1. Run all existing tests — must pass unchanged

# 2. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}' | jq -r '.access_token')

# 3. Test greeting (must work exactly as before)
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "hi"}'

# 4. Test HR question
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is the remote work policy?"}'

# 5. Test follow-up
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "explain that more", "session_id": "SESSION_ID_FROM_STEP_4"}'

# 6. Test streaming
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  -d '{"query": "What is leave policy?"}' \
  --no-buffer

# 7. Test health endpoint
curl http://localhost:8000/api/v1/query/health

# 8. Verify backward compatibility — import from old path
python -c "from app.services.rag import RAGService; print('Import works')"
```

---

## 15. Definition of Done

### Architecture:
- [ ] `BaseAgent` abstract class exists in `app/agents/base.py`
- [ ] `HRAgent` extends `BaseAgent` in `app/agents/hr_agent.py`
- [ ] `HRAgent` only defines attributes, no method overrides needed
- [ ] `app/services/rag.py` is a thin wrapper preserving backward compatibility

### Functionality:
- [ ] `/api/v1/query` (streaming) works exactly as before
- [ ] `/api/v1/query/test` (non-streaming) works exactly as before
- [ ] `/api/v1/query/health` works exactly as before
- [ ] All 5 intent classifications handled correctly
- [ ] Follow-ups work with conversation history
- [ ] Sources returned correctly
- [ ] Confidence gating unchanged
- [ ] Direct responses unchanged

### Code Quality:
- [ ] No HR-specific strings in `BaseAgent`
- [ ] No pipeline logic in `HRAgent` (only configuration)
- [ ] BaseAgent validates subclass attributes on init
- [ ] Static methods are actually static
- [ ] No circular imports
- [ ] All existing imports from `app.services.rag` still work

### Agent Pattern Validation:
- [ ] Creating a new agent requires only defining 7 string attributes
- [ ] Can instantiate `HRAgent` with constructor injection
- [ ] `HRAgent` can be used without knowing it's HR-specific (polymorphism)