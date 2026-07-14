# Feature 16: HR Agent Tool-Use with Leave Balance Querying

## 1. Overview

Add tool-use capability to the HR Agent so it can dynamically decide whether to query the database for personal leave data, search policy documents via RAG, or both — based on the user's query. The LLM itself decides which tool(s) to call, making the agent more flexible and intelligent without hardcoded routing rules.

This establishes the **agent tool-use pattern** — a foundation for adding more personal data tools (payroll, benefits enrollment, performance data) in the future.

---

## 2. Depends on

- **Feature 12: BaseAgent Pattern** — HR Agent extends BaseAgent
- **Feature 14: Agent Orchestrator** — orchestrator routes to HR Agent
- **Feature 6: Gemini Service Layer** — LLM for tool-use decisions
- **Feature 2: Database Schema** — database access patterns exist
- **Feature 3: User Authentication** — JWT user_id available

---

## 3. Routes

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `POST` | `/api/v1/query` | Yes (JWT) | Existing — HR Agent now uses tools internally |
| `GET` | `/api/v1/leave/balance` | Yes (JWT) | Get current user's leave balance |
| `POST` | `/api/v1/admin/seed/leaves` | Yes (JWT, admin) | Seed leave balances for demo users |

---

## 4. Tool-Use Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    HR AGENT — TOOL-USE FLOW                                           │
│                                                                                      │
│  USER QUERY: "How many leaves do I have left?"                                       │
│       │                                                                              │
│       ▼                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  HR AGENT receives query + user context                                       │    │
│  └───────────────────────────────────────┬─────────────────────────────────────┘    │
│                                          │                                           │
│                                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  STEP 1: TOOL-SELECTION LLM CALL                                              │    │
│  │                                                                              │    │
│  │  Prompt: "You have access to these tools. Which tool(s) should be used       │    │
│  │           to answer this query? Reply with tool names and parameters."       │    │
│  │                                                                              │    │
│  │  Available tools:                                                            │    │
│  │  • search_policy(query: str) — Search HR policy documents                    │    │
│  │  • get_leave_balance(user_id: str) — Get employee leave balances             │    │
│  │                                                                              │    │
│  │  Output: [{"tool": "get_leave_balance", "params": {"user_id": "..."}}]      │    │
│  └───────────────────────────────────────┬─────────────────────────────────────┘    │
│                                          │                                           │
│                     ┌────────────────────┼────────────────────┐                      │
│                     │                    │                    │                      │
│                     ▼                    ▼                    ▼                      │
│              ┌────────────┐      ┌────────────┐      ┌────────────┐                 │
│              │ RAG ONLY   │      │ DB ONLY    │      │ BOTH       │                 │
│              │            │      │            │      │ (RAG + DB) │                 │
│              └─────┬──────┘      └─────┬──────┘      └─────┬──────┘                 │
│                    │                   │                    │                         │
│                    ▼                   ▼                    ▼                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  STEP 2: EXECUTE TOOLS                                                       │    │
│  │  • search_policy → pgvector similarity search                                │    │
│  │  • get_leave_balance → PostgreSQL query                                      │    │
│  │  • Both → execute in parallel, merge results                                 │    │
│  └───────────────────────────────────────┬─────────────────────────────────────┘    │
│                                          │                                           │
│                                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  STEP 3: BUILD PROMPT WITH TOOL RESULTS                                       │    │
│  │                                                                              │    │
│  │  System prompt + Tool results + Conversation history + User query            │    │
│  │                                                                              │    │
│  │  Tool results formatted as:                                                   │    │
│  │  ---                                                                          │    │
│  │  POLICY SEARCH RESULTS:                                                       │    │
│  │  [Source: leave_policy.pdf, Page 2]                                           │    │
│  │  Employees receive 20 days annual leave per year...                           │    │
│  │  ---                                                                          │    │
│  │  LEAVE BALANCE:                                                                │    │
│  │  Annual Leave: 12 remaining (20 allocated, 8 used)                            │    │
│  │  Sick Leave: 8 remaining (10 allocated, 2 used)                               │    │
│  │  Personal Leave: 3 remaining (3 allocated, 0 used)                            │    │
│  │  ---                                                                          │    │
│  └───────────────────────────────────────┬─────────────────────────────────────┘    │
│                                          │                                           │
│                                          ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  STEP 4: GENERATE RESPONSE (streaming)                                        │    │
│  │  Normal LLM generation with tool results as context                           │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Tool Definitions

### Tool 1: `search_policy`

```text
Name: search_policy
Description: Search the HR policy knowledge base for information about company policies, 
             benefits, leave rules, remote work guidelines, and other HR topics.
             Use this when the user asks about general policies or procedures.

Parameters:
  - query (string, required): The search query to find relevant policy documents

Returns:
  - List of relevant document chunks with source citations and similarity scores
```

### Tool 2: `get_leave_balance`

```text
Name: get_leave_balance
Description: Get the current leave balance for a specific employee. 
             Returns allocated, used, and remaining days for each leave type.
             Use this when the user asks about their personal leave balance,
             remaining vacation days, or how many leaves they have left.

Parameters:
  - user_id (string, required): The employee's user ID

Returns:
  - Object with leave balances by type (annual, sick, personal)
  - Each type includes: allocated, used, remaining
  - Current year used automatically
```

---

## 6. Tool-Selection Prompt

```
You are a tool-selection assistant for an HR agent. Your job is to decide which tools to use based on the user's query.

AVAILABLE TOOLS:

1. search_policy
   - Use for: questions about company policies, benefits rules, leave eligibility, remote work guidelines, payroll procedures
   - Example queries: "What is the leave policy?", "How does remote work work?", "What are the health benefits?"

2. get_leave_balance
   - Use for: questions about personal leave counts, remaining vacation days, how many leaves the user has left
   - Example queries: "How many leaves do I have?", "What's my leave balance?", "How many vacation days left?"

RULES:
1. If the query asks about the USER'S OWN leave count → use get_leave_balance
2. If the query asks about leave POLICY in general → use search_policy
3. If the query asks both (e.g., "Can I take leave next week?") → use BOTH tools
4. If the query contains "I", "me", "my" AND leave-related terms → always include get_leave_balance
5. If unsure between policy and personal → use BOTH (safe default)
6. For non-leave HR questions → use only search_policy

USER QUERY: {user_query}

Reply with a JSON array of tools to use:
[{"tool": "tool_name", "params": {"param": "value"}}]

Example responses:
- "What is leave policy?" → [{"tool": "search_policy", "params": {"query": "leave policy"}}]
- "How many leaves do I have?" → [{"tool": "get_leave_balance", "params": {"user_id": "..."}}]
- "Can I take leave next Friday?" → [{"tool": "get_leave_balance", "params": {"user_id": "..."}}, {"tool": "search_policy", "params": {"query": "leave application process"}}]
```

---

## 7. Database Schema

### New Table: `leave_balances`

```sql
CREATE TABLE IF NOT EXISTS leave_balances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    leave_type VARCHAR(50) NOT NULL CHECK (leave_type IN ('annual', 'sick', 'personal')),
    total_allocated INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0,
    year INTEGER NOT NULL DEFAULT EXTRACT(YEAR FROM NOW())::INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- One row per user per leave type per year
    UNIQUE(user_id, leave_type, year)
);

CREATE INDEX IF NOT EXISTS idx_leave_balances_user_id ON leave_balances(user_id);
CREATE INDEX IF NOT EXISTS idx_leave_balances_year ON leave_balances(year);
```

---

## 8. Seed Data

```sql
-- Admin User (admin@company.com) — hr_admin
INSERT INTO leave_balances (user_id, leave_type, total_allocated, used, year) VALUES
    ((SELECT id FROM users WHERE email = 'admin@company.com'), 'annual', 25, 5, 2026),
    ((SELECT id FROM users WHERE email = 'admin@company.com'), 'sick', 15, 1, 2026),
    ((SELECT id FROM users WHERE email = 'admin@company.com'), 'personal', 5, 2, 2026);

-- John Doe (john@company.com) — employee, engineering
INSERT INTO leave_balances (user_id, leave_type, total_allocated, used, year) VALUES
    ((SELECT id FROM users WHERE email = 'john@company.com'), 'annual', 20, 8, 2026),
    ((SELECT id FROM users WHERE email = 'john@company.com'), 'sick', 10, 2, 2026),
    ((SELECT id FROM users WHERE email = 'john@company.com'), 'personal', 3, 0, 2026);

-- Sarah Smith (sarah@company.com) — manager, sales
INSERT INTO leave_balances (user_id, leave_type, total_allocated, used, year) VALUES
    ((SELECT id FROM users WHERE email = 'sarah@company.com'), 'annual', 22, 15, 2026),
    ((SELECT id FROM users WHERE email = 'sarah@company.com'), 'sick', 10, 3, 2026),
    ((SELECT id FROM users WHERE email = 'sarah@company.com'), 'personal', 3, 3, 2026);

-- Priya Sharma (priya@company.com) — employee, hr
INSERT INTO leave_balances (user_id, leave_type, total_allocated, used, year) VALUES
    ((SELECT id FROM users WHERE email = 'priya@company.com'), 'annual', 20, 2, 2026),
    ((SELECT id FROM users WHERE email = 'priya@company.com'), 'sick', 10, 0, 2026),
    ((SELECT id FROM users WHERE email = 'priya@company.com'), 'personal', 3, 1, 2026);
```

---

## 9. Files to Create

### `app/tools/__init__.py`
- Empty file, makes `tools` a package

### `app/tools/base.py`

**Purpose:** Base tool interface and tool registry.

**Contents:**
- `ToolResult` dataclass — `tool_name: str`, `data: dict`, `error: Optional[str]`
- `BaseTool` abstract class:
  - `name: str` — tool identifier
  - `description: str` — what the tool does
  - `parameters: dict` — JSON Schema for parameters
  - `async execute(**params) -> ToolResult` — abstract method

### `app/tools/search_policy.py`

**Purpose:** RAG search tool for policy documents.

**Class: `SearchPolicyTool(BaseTool)`**
- `name = "search_policy"`
- `description = "Search HR policy documents for relevant information"`
- `parameters = {"query": {"type": "string", "description": "Search query"}}`
- `async execute(query: str, user_role: str, db: AsyncSession) -> ToolResult`
  - Calls existing SearchService with `collection_name="hr_documents"`
  - Returns top 5 chunks with source citations
  - Formats results as list of dicts

### `app/tools/get_leave_balance.py`

**Purpose:** Database query tool for personal leave data.

**Class: `GetLeaveBalanceTool(BaseTool)`**
- `name = "get_leave_balance"`
- `description = "Get current leave balance for an employee"`
- `parameters = {"user_id": {"type": "string", "description": "Employee user ID"}}`
- `async execute(user_id: str, db: AsyncSession) -> ToolResult`
  - Queries `leave_balances` table for current year
  - Filters by `user_id`
  - Returns structured leave data: `{leave_type: {allocated, used, remaining}}`
  - If no data found, returns empty balances (not error)

### `app/tools/registry.py`

**Purpose:** Tool registry that maps tool names to tool instances.

**Contents:**
- `ToolRegistry` class:
  - `__init__()` — initializes empty registry
  - `register(tool: BaseTool) -> None` — adds tool
  - `get_tool(name: str) -> BaseTool` — retrieves by name
  - `list_tools() -> list[dict]` — returns tool descriptions for LLM prompt
  - `async execute_tools(tool_calls: list[dict], context: dict) -> list[ToolResult]`
    - Executes multiple tools from LLM's selection
    - Handles errors per-tool (one failure doesn't block others)

---

### `app/services/tool_selector.py`

**Purpose:** LLM-powered tool selection service.

**Class: `ToolSelectorService`**

**Methods:**
- `__init__(gemini_service: GeminiService, tool_registry: ToolRegistry)`
- `async select_tools(query: str, user_context: dict) -> list[dict]`
  - Builds tool selection prompt with available tools
  - Calls Gemini 2.5 Flash (temp=0.1, max_tokens=200)
  - Parses JSON response
  - Validates tool names exist in registry
  - Returns list of tool calls: `[{"tool": "name", "params": {...}}]`

### `app/prompts/tool_selector.py`

**Purpose:** Tool selection prompt templates.

**Contents:**
- `TOOL_SELECTION_SYSTEM_PROMPT` — defines available tools and rules
- `TOOL_SELECTION_USER_PROMPT` — template with `{user_query}`

---

### `app/repositories/leave.py`

**Purpose:** Data access for leave_balances table.

**Class: `LeaveRepository`**

**Methods:**
- `__init__(db: AsyncSession)`
- `async get_balance(user_id: str, year: int = None) -> list[dict]`
  - If year is None, uses current year
  - Returns list of leave type balances
- `async get_balance_by_type(user_id: str, leave_type: str) -> Optional[dict]`
- `async seed_leave_data(seed_data: list[dict]) -> int`
  - Bulk inserts if not exists (by unique constraint)
  - Returns count inserted

### `app/schemas/leave.py`

**Purpose:** Leave-related Pydantic schemas.

**Contents:**
- `LeaveBalanceItem` — leave_type, total_allocated, used, remaining
- `LeaveBalanceResponse` — user_id, year, balances (list of LeaveBalanceItem), total_used, total_remaining
- `SeedLeaveRequest` — list of user leave data

### `app/api/v1/leave.py`

**Purpose:** Leave balance endpoint (for direct access and testing).

**Router:** prefix="" (full path in main.py), tags=["Leave"]

**Endpoints:**
- `GET /` — get current user's leave balance
- `POST /seed` — admin only, seed leave data

---

## 10. Files to Change

### `app/agents/hr_agent.py`

**Major update:** Add tool-use to the HR Agent's `process_query()` method.

**New flow:**
1. Receive query + user context
2. Call `ToolSelectorService.select_tools(query, user_context)`
3. Execute selected tools via `ToolRegistry.execute_tools()`
4. Format tool results for prompt
5. Build prompt with tool results (instead of just RAG context)
6. Generate streaming response

**New attribute:**
```python
tool_registry: ToolRegistry  # Injected via constructor
tool_selector: ToolSelectorService  # Injected via constructor
```

**Constructor update:**
```python
def __init__(self, db, gemini_service, search_service, classifier_service, tool_registry):
    super().__init__(db, gemini_service, search_service, classifier_service)
    self.tool_registry = tool_registry
    self.tool_selector = ToolSelectorService(gemini_service, tool_registry)
```

### `app/agents/base.py`

**Minor update:** Update `_build_prompt()` to accept optional tool results.

**New parameter:**
```python
def _build_prompt(self, query, context_chunks, history, confidence, tool_results=None) -> str:
```

If `tool_results` is provided, include it in the prompt before RAG context.

**New method:**
```python
def _format_tool_results(tool_results: list[ToolResult]) -> str:
    """Format tool execution results for the prompt."""
```

### `app/database.py`

**Update `init_db()`:**
- Add `leave_balances` table creation
- Add indexes

### `app/seed.py`

**Update `seed_db()`:**
- Add leave balance seed data after user seeding
- Check if leave data exists before inserting
- Use ON CONFLICT DO NOTHING for idempotency

### `app/core/deps.py`

**Add dependency:**
```python
async def get_tool_registry(
    db: AsyncSession = Depends(get_db),
    search_service: SearchService = Depends(get_search_service),
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(SearchPolicyTool(search_service))
    registry.register(GetLeaveBalanceTool(db))
    return registry
```

### `app/main.py`

```python
from app.api.v1 import leave

app.include_router(leave.router, prefix="/api/v1/leave", tags=["Leave"])
```

### `app/prompts/hr_agent.py`

**Update system prompt** to inform LLM it may have tool results available:

Add to system prompt:
```
ADDITIONAL INFORMATION:
You may be provided with tool execution results below. This data comes from:
- POLICY SEARCH RESULTS: Information retrieved from HR policy documents
- LEAVE BALANCE: The user's personal leave data (allocated, used, remaining)

Use this data to provide accurate, personalized answers. Always cite policy sources when using POLICY SEARCH RESULTS.
```

---

## 11. Files to Create

```
app/tools/__init__.py
app/tools/base.py                   (BaseTool, ToolResult, ToolRegistry)
app/tools/search_policy.py          (SearchPolicyTool)
app/tools/get_leave_balance.py      (GetLeaveBalanceTool)
app/tools/registry.py               (ToolRegistry)
app/services/tool_selector.py       (ToolSelectorService)
app/prompts/tool_selector.py        (Tool selection prompts)
app/repositories/leave.py           (LeaveRepository)
app/schemas/leave.py                (Leave schemas)
app/api/v1/leave.py                 (Leave endpoints)
```

---

## 12. Files to Change

```
app/agents/hr_agent.py              (add tool-use to pipeline)
app/agents/base.py                  (accept tool_results in prompt builder)
app/database.py                     (add leave_balances table)
app/seed.py                         (add leave seed data)
app/core/deps.py                    (add tool registry dependency)
app/main.py                         (add leave router)
app/prompts/hr_agent.py             (update system prompt)
```

---

## 13. Dependencies

No new packages. All existing dependencies sufficient.

---

## 14. Rules for Implementation

- **LLM decides tools**: No hardcoded rules for which tool to use
- **Tools are idempotent**: Same query + same params = same results
- **Tool failures are graceful**: One tool failing doesn't crash the pipeline
- **User_id from JWT**: `get_leave_balance` uses `user_id` from authenticated user context — users can only query their own data
- **Current year default**: Leave queries default to current year
- **Parallel execution**: When multiple tools selected, execute in parallel
- **Tool results in prompt**: Always formatted clearly so LLM knows what's policy vs personal
- **Backward compatible**: Queries without leave intent still work via RAG-only path
- **Privacy**: Never expose other users' leave data
- **No tool state**: Tools are stateless — each call is independent

---

## 15. Tool Selection Examples

| User Query | Tools Selected | Reasoning |
|------------|---------------|-----------|
| "How many leaves do I have?" | `get_leave_balance` | Personal, specific count |
| "What is the leave policy?" | `search_policy` | General policy question |
| "Can I take leave next Friday?" | `get_leave_balance` + `search_policy` | Needs balance + policy rules |
| "How many sick days do I have left?" | `get_leave_balance` | Personal, specific type |
| "What are the rules for carrying forward leave?" | `search_policy` | Policy rule, not personal |
| "I need time off for surgery" | `search_policy` + `get_leave_balance` | Policy for medical leave + balance |
| "How does remote work work?" | `search_policy` | Policy question, no personal data |
| "How many leaves does John have?" | `search_policy` | Cannot access others' data (LLM should NOT call get_leave_balance for other users) |

---

## 16. Security: Preventing Cross-User Data Access

The `get_leave_balance` tool must enforce that users can only query their own data:

```text
In ToolSelector prompt: "get_leave_balance can ONLY be called with the current user's ID. 
Never call it for other users. The user_id parameter should always be the authenticated user."

In get_leave_balance.execute(): 
  - Accept user_id parameter
  - In production: compare against authenticated user from context
  - For now: trust the LLM + validate in tool execution
```

---

## 17. Verification Steps

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}' | jq -r '.access_token')

ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"admin123"}' | jq -r '.access_token')

# 1. Seed leave data
curl -X POST http://localhost:8000/api/v1/leave/seed \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Check own leave balance (direct endpoint)
curl -X GET http://localhost:8000/api/v1/leave \
  -H "Authorization: Bearer $TOKEN"

# 3. Personal leave query (through orchestrator)
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "How many leaves do I have left?"}'
# Expected: Personalized response with John's leave balance (12 annual, 8 sick, 3 personal)

# 4. Policy-only query
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is the leave policy?"}'
# Expected: Policy answer from RAG, no personal data

# 5. Hybrid query
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "Can I take leave next week? I need 3 days off"}'
# Expected: Balance check (12 remaining) + policy on leave application

# 6. Specific leave type
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "How many sick days do I have?"}'
# Expected: Sick leave balance (8 remaining)

# 7. Non-leave HR query (should not trigger tool)
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is the remote work policy?"}'
# Expected: RAG-only response, no leave data

# 8. Different user (Priya)
PRIYA_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"priya@company.com","password":"priya123"}' | jq -r '.access_token')

curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PRIYA_TOKEN" \
  -d '{"query": "How many leaves do I have?"}'
# Expected: Priya's balance (18 annual, 10 sick, 2 personal)
```

---

## 18. Definition of Done

### Database:
- [ ] `leave_balances` table exists with correct schema
- [ ] Unique constraint on (user_id, leave_type, year)
- [ ] Seed data inserted for all 4 demo users
- [ ] Seed data is idempotent (no duplicates on re-run)

### Tools:
- [ ] `SearchPolicyTool` works with existing SearchService
- [ ] `GetLeaveBalanceTool` queries database correctly
- [ ] `ToolRegistry` registers and retrieves tools
- [ ] Multiple tools can execute in parallel
- [ ] Tool failures don't crash the pipeline

### Tool Selection:
- [ ] `ToolSelectorService` uses LLM to select tools
- [ ] Personal queries select `get_leave_balance`
- [ ] Policy queries select `search_policy`
- [ ] Hybrid queries select both tools
- [ ] Non-leave queries don't trigger leave tool

### HR Agent Integration:
- [ ] HR Agent pipeline includes tool-use step
- [ ] Tool results formatted in prompt
- [ ] Streaming response includes personalized data
- [ ] Backward compatible — existing queries work unchanged
- [ ] Privacy enforced — users can only see their own data

### API:
- [ ] `GET /api/v1/leave` returns authenticated user's balance
- [ ] `POST /api/v1/leave/seed` seeds data (admin only)
- [ ] Leave data included in orchestrator responses when relevant

### User Experience:
- [ ] "How many leaves do I have?" returns personalized numbers
- [ ] Policy questions still return policy answers
- [ ] Responses cite both personal data source and policy sources
- [ ] Response format is clear and readable