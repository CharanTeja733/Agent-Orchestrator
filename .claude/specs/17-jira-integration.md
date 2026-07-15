# Feature 17: IT Agent Jira Ticket Tool

## 1. Overview

Add Jira API integration to the IT Agent using the tool-use pattern established in Feature 16. The IT Agent can now fetch an employee's open tickets from Jira in real-time, combining ticket data with IT documentation when answering queries. This makes the IT Agent capable of personalized responses about ticket status, open tickets, and IT issue tracking.

This establishes the **external API integration pattern** — a foundation for adding more third-party service tools (ServiceNow, Zendesk, Confluence) in the future.

---

## 2. Depends on

- **Feature 16: HR Agent Tool-Use** — ToolRegistry, ToolSelectorService, BaseTool pattern exist
- **Feature 13: IT Agent** — IT Agent extends BaseAgent
- **Feature 14: Agent Orchestrator** — orchestrator routes to IT Agent
- **Feature 6: Gemini Service Layer** — shared LLM for tool selection
- **Feature 3: User Authentication** — user email available from JWT

---

## 3. Routes

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `GET` | `/api/v1/tickets` | Yes (JWT) | Get current user's open Jira tickets |
| `POST` | `/api/v1/query` | Yes (JWT) | Existing — IT Agent now uses Jira tool when relevant |

---

## 4. Jira Integration Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    IT AGENT — JIRA TOOL FLOW                                          │
│                                                                                      │
│  USER: "How many open tickets do I have?"                                            │
│       │                                                                              │
│       ▼                                                                              │
│  Orchestrator: domain = "it" → routes to IT Agent                                    │
│       │                                                                              │
│       ▼                                                                              │
│  IT Agent: ToolSelectorService.select_tools(query, user_context)                     │
│       │                                                                              │
│       ▼                                                                              │
│  LLM Decision: [{"tool": "get_my_tickets", "params": {"user_email": "..."}}]        │
│       │                                                                              │
│       ▼                                                                              │
│  GetMyTicketsTool.execute(user_email="john@company.com")                             │
│       │                                                                              │
│       ▼                                                                              │
│  JiraService.get_open_tickets(email="john@company.com")                              │
│       │                                                                              │
│       ▼                                                                              │
│  Jira API: GET /rest/api/3/search?jql=reporter="john@company.com"...                │
│       │                                                                              │
│       ▼                                                                              │
│  Tool Result: {total_open: 3, tickets: [...]}                                        │
│       │                                                                              │
│       ▼                                                                              │
│  Build prompt with ticket data + optional IT doc search                              │
│       │                                                                              │
│       ▼                                                                              │
│  Generate personalized streaming response                                            │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Jira Configuration

### Environment Variables (`.env`)

```
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_API_TOKEN=your-api-token-here
JIRA_BOT_EMAIL=hr-bot@company.com
JIRA_REQUEST_TIMEOUT_SECONDS=10
JIRA_MAX_RESULTS=20
```

### Config Settings (`app/config.py`)

```python
JIRA_BASE_URL: str = ""
JIRA_API_TOKEN: str = ""
JIRA_BOT_EMAIL: str = ""
JIRA_REQUEST_TIMEOUT_SECONDS: int = 10
JIRA_MAX_RESULTS: int = 20
```

---

## 6. Jira API Integration

### API Details

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    JIRA REST API V3                                                   │
│                                                                                      │
│  Endpoint: GET /rest/api/3/search                                                    │
│                                                                                      │
│  Authentication: Basic Auth                                                            │
│  • Username: JIRA_BOT_EMAIL                                                          │
│  • Password: JIRA_API_TOKEN                                                           │
│                                                                                      │
│  Query Parameters:                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  jql          │ reporter = "{user_email}"                                    │    │
│  │               │ AND status NOT IN ("Done", "Closed", "Resolved", "Cancelled")│    │
│  │               │ ORDER BY created DESC                                         │    │
│  │  maxResults   │ 20 (configurable)                                            │    │
│  │  fields       │ summary,status,priority,created,assignee,description         │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  Response Fields Used:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  Field              │ Jira Path                       │ Example              │    │
│  ├─────────────────────┼─────────────────────────────────┼──────────────────────┤    │
│  │  key                 │ issue.key                        │ "IT-1234"            │    │
│  │  summary             │ issue.fields.summary             │ "VPN not connecting" │    │
│  │  status              │ issue.fields.status.name         │ "In Progress"        │    │
│  │  priority            │ issue.fields.priority.name       │ "Medium"             │    │
│  │  created_date        │ issue.fields.created             │ "2026-07-10T14:30..."│    │
│  │  assignee            │ issue.fields.assignee.displayName│ "IT Support Team"    │    │
│  │  description         │ issue.fields.description         │ "Full description..."│    │
│  │  url                 │ self (base URL + key)            │ "https://..."        │    │
│  └─────────────────────────────────────────────────────────┴──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. JQL Query Template

```
reporter = "{user_email}" 
AND status NOT IN ("Done", "Closed", "Resolved", "Cancelled") 
ORDER BY created DESC
```

**Rules:**
- `user_email` is the authenticated user's email from the users table
- Only open/active tickets (exclude completed/cancelled)
- Most recent first
- Max 20 results (configurable)
- If more than max results exist, include a link to view all in Jira

---

## 8. Files to Create

### `app/services/jira.py`

**Purpose:** Jira API client — handles all communication with Jira REST API.

**Class: `JiraService`**

**Constructor:**
- Takes `base_url`, `email`, `api_token`, `timeout` from config
- Creates `httpx.AsyncClient` with Basic Auth headers
- Validates config on init (raises `ValueError` if missing required fields)

**Methods:**

- `async get_open_tickets(user_email: str, max_results: int = 20) -> dict`
  - Builds JQL query with user's email
  - Makes GET request to `/rest/api/3/search`
  - Parses response and extracts relevant fields
  - Returns structured ticket data: `{total_open: int, tickets: list[dict]}`
  - Handles HTTP errors, timeouts, auth failures
  - Raises `JiraAPIError` on failure

- `async get_ticket_details(issue_key: str) -> dict`
  - Gets single ticket with comments
  - Not required for this feature — placeholder for future
  - Raises `NotImplementedError`

- `_parse_ticket_response(response: dict) -> list[dict]`
  - Extracts only the 7 relevant fields from Jira response
  - Formats dates to readable strings
  - Builds ticket URL from base URL + key
  - Strips internal Jira metadata

- `_build_jql(user_email: str) -> str`
  - Constructs JQL query from template
  - URL-encodes special characters in email

- `_handle_api_error(response: httpx.Response) -> None`
  - Maps HTTP status codes to meaningful error messages
  - 401 → "Jira authentication failed. Check API token."
  - 403 → "Jira access denied. Check permissions."
  - 404 → "User not found in Jira"
  - 429 → "Jira rate limit exceeded"
  - 5xx → "Jira service unavailable"

### `app/tools/get_my_tickets.py`

**Purpose:** Tool wrapping the Jira service for the IT Agent's tool-use system.

**Class: `GetMyTicketsTool(BaseTool)`**

**Attributes:**
- `name = "get_my_tickets"`
- `description = "Get open Jira tickets for the current user. Returns total count and ticket details including key, summary, status, priority, created date, assignee, and URL."`
- `parameters = {"user_email": {"type": "string", "description": "The user's email address to query tickets for"}}`

**Methods:**
- `async execute(user_email: str, jira_service: JiraService) -> ToolResult`
  - Calls `jira_service.get_open_tickets(user_email)`
  - On success: returns `ToolResult` with ticket data
  - On `JiraAPIError`: returns `ToolResult` with error message (never raises)
  - On timeout: returns `ToolResult` with timeout message
  - Always succeeds from tool perspective — errors are in result, not exceptions

### `app/core/exceptions.py` — Add Jira exceptions

```python
class JiraAPIError(Exception):
    """Base exception for Jira API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class JiraAuthError(JiraAPIError):
    """Raised when Jira authentication fails."""
    pass

class JiraNotFoundError(JiraAPIError):
    """Raised when user or resource not found in Jira."""
    pass

class JiraRateLimitError(JiraAPIError):
    """Raised when Jira rate limit is exceeded."""
    pass

class JiraTimeoutError(JiraAPIError):
    """Raised when Jira request times out."""
    pass
```

---

## 9. Files to Change

### `app/agents/it_agent.py`

**Update constructor:**
```python
def __init__(self, db, gemini_service, search_service, classifier_service, tool_registry):
    super().__init__(db, gemini_service, search_service, classifier_service)
    self.tool_registry = tool_registry
    self.tool_selector = ToolSelectorService(gemini_service, tool_registry)
```

**Update tool registry setup (in dependency injection):**
- IT Agent's `tool_registry` now includes:
  - `SearchITDocsTool` (existing RAG tool for IT documents)
  - `GetMyTicketsTool` (new Jira tool)

### `app/agents/base.py`

**Verify tool-use is supported:**
- `_build_prompt()` must accept `tool_results` parameter (from Feature 16)
- `_format_tool_results()` must handle ticket data formatting
- If these don't exist yet, this feature adds them

### `app/tools/registry.py`

**Update IT Agent tool registration (in dependency injection):**
```python
def get_it_agent_tool_registry(jira_service: JiraService, search_service: SearchService):
    registry = ToolRegistry()
    registry.register(SearchITDocsTool(search_service))
    registry.register(GetMyTicketsTool(jira_service))
    return registry
```

### `app/core/deps.py`

**Add new dependencies:**
```python
async def get_jira_service() -> JiraService:
    """Create Jira service from config settings."""
    return JiraService(
        base_url=settings.JIRA_BASE_URL,
        email=settings.JIRA_BOT_EMAIL,
        api_token=settings.JIRA_API_TOKEN,
        timeout=settings.JIRA_REQUEST_TIMEOUT_SECONDS,
    )

async def get_it_agent_tool_registry(
    jira_service: JiraService = Depends(get_jira_service),
    search_service: SearchService = Depends(get_search_service),
) -> ToolRegistry:
    """Create tool registry for IT Agent."""
    registry = ToolRegistry()
    registry.register(SearchITDocsTool(search_service))
    registry.register(GetMyTicketsTool(jira_service))
    return registry
```

### `app/core/config.py`

**Add Jira settings (from section 5).**

### `app/prompts/it_agent.py`

**Update system prompt** to inform LLM about available tools:

Add to system prompt:
```
ADDITIONAL INFORMATION:
You may be provided with tool execution results below. This data comes from:
- IT DOCUMENTATION: Information retrieved from IT troubleshooting guides and documentation
- JIRA TICKETS: The user's personal Jira ticket data (open tickets, status, assignee)

When presenting ticket information:
- Show ticket key, summary, status, priority, and created date
- Include clickable Jira links
- If no tickets found, reassure the user
- Combine with documentation when the user asks both about tickets AND troubleshooting
```

### `app/prompts/tool_selector.py`

**Update tool descriptions for IT Agent context:**

Add to the tool selection prompt (when used by IT Agent):
```
3. get_my_tickets
   - Use for: questions about the user's own Jira tickets, open ticket count, 
              ticket status, or specific ticket updates
   - Example queries: "How many open tickets do I have?", "What's my ticket status?", 
                      "Any update on IT-1234?"
   - Parameters: user_email (the user's email address)
```

### `app/api/v1/tickets.py` — NEW

**Router:** prefix="" (full path in main.py), tags=["Tickets"]

**Endpoints:**
- `GET /` — get current user's open Jira tickets (direct access, for testing)

### `app/main.py`

```python
from app.api.v1 import tickets

app.include_router(tickets.router, prefix="/api/v1/tickets", tags=["Tickets"])
```

---

## 10. Files to Create

```
app/services/jira.py               (JiraService — API client)
app/tools/get_my_tickets.py        (GetMyTicketsTool — wraps JiraService)
app/api/v1/tickets.py              (Direct ticket endpoint for testing)
```

---

## 11. Files to Change

```
app/agents/it_agent.py             (Inject Jira tool into IT agent)
app/agents/base.py                 (Verify tool_results in prompt builder)
app/tools/registry.py              (IT agent tool registration)
app/core/deps.py                   (Jira service + IT tool registry dependencies)
app/core/config.py                 (Jira configuration)
app/core/exceptions.py             (Jira-specific exceptions)
app/prompts/it_agent.py            (Update system prompt for Jira data)
app/prompts/tool_selector.py       (Add get_my_tickets to tool descriptions)
app/main.py                        (Add tickets router)
.env.example                       (Add Jira variables)
requirements.txt                   (Add httpx)
```

---

## 12. Dependencies

### Add to `requirements.txt`:
```
httpx>=0.27.0
```

---

## 13. Rules for Implementation

- **Real-time API calls only**: No syncing, no caching — fetch from Jira on every query
- **Read-only access**: Never create, update, or delete Jira tickets
- **User isolation**: JQL always filters by `reporter = current_user.email`
- **Never accept raw JQL**: JQL is built server-side from template, never from user input
- **Graceful failures**: Jira errors return ToolResult with error message, never crash
- **Timeout handling**: Default 10 seconds, configurable
- **Response sanitization**: Only expose 7 fields (key, summary, status, priority, created, assignee, url)
- **Rate limit awareness**: Check Jira response headers for rate limit info
- **Service account**: Bot uses its own Jira account, not impersonating users
- **No ticket creation**: This is Phase 1 — read-only queries only

---

## 14. Error Handling

| Scenario | Tool Result | Agent Response |
|----------|-------------|---------------|
| Jira API down (5xx) | `error: "Jira is temporarily unavailable"` | "I couldn't fetch your tickets right now. Please try again or check Jira directly." |
| Auth failure (401) | `error: "Jira authentication failed"` | Log critical error. "I'm having trouble accessing Jira. Please contact IT support." |
| User not found (404) | `error: "User not found in Jira"` | "I couldn't find your account in Jira. Contact IT support to verify your account setup." |
| Rate limit (429) | `error: "Rate limit exceeded"` | "I'm receiving too many requests. Please wait a moment and try again." |
| Timeout (>10s) | `error: "Request timed out"` | "Jira is taking too long to respond. Check your tickets at [Jira URL]." |
| No tickets found | `data: {total_open: 0, tickets: []}` | "You have no open tickets. Everything looks good! 🎉" |
| 100+ tickets | `data: {total_open: 127, tickets: [5 most recent]}` | "You have 127 open tickets. Here are the 5 most recent. View all at [Jira URL]." |
| Network error | `error: "Network error"` | "I couldn't connect to Jira. Please check your connection and try again." |

---

## 15. Tool Selection Examples

| User Query | Tools Selected | Reasoning |
|------------|---------------|-----------|
| "How many open tickets do I have?" | `get_my_tickets` | Personal ticket count |
| "What's the status of my VPN ticket?" | `get_my_tickets` | Personal ticket status |
| "Any update on IT-1234?" | `get_my_tickets` | Specific ticket inquiry |
| "How do I set up VPN?" | `search_it_docs` | Documentation/how-to |
| "My laptop won't turn on" | `search_it_docs` | Troubleshooting |
| "IT-1234 is about VPN, I tried the steps but still broken" | `get_my_tickets` + `search_it_docs` | Ticket status + more troubleshooting |
| "I filed a ticket yesterday, any progress?" | `get_my_tickets` | Recent ticket status |
| "How do I reset my password?" | `search_it_docs` | Documentation |
| "Do I have any high priority tickets?" | `get_my_tickets` | Personal ticket query |
| "What's the IT support email?" | `search_it_docs` | Documentation lookup |

---

## 16. Tool Result Format

```json
{
  "tool_name": "get_my_tickets",
  "success": true,
  "data": {
    "total_open": 3,
    "tickets": [
      {
        "key": "IT-1234",
        "summary": "VPN not connecting from home",
        "status": "In Progress",
        "priority": "Medium",
        "created_date": "2026-07-10",
        "assignee": "IT Support Team",
        "url": "https://company.atlassian.net/browse/IT-1234"
      },
      {
        "key": "IT-1189",
        "summary": "Laptop battery draining quickly",
        "status": "Waiting for Customer",
        "priority": "Low",
        "created_date": "2026-06-28",
        "assignee": "Hardware Team",
        "url": "https://company.atlassian.net/browse/IT-1189"
      }
    ]
  },
  "error": null
}
```

---

## 17. Prompt Formatting for Tool Results

When ticket data is included in the LLM prompt:

```
JIRA TICKETS:
---
Total Open Tickets: 3

1. IT-1234 — VPN not connecting from home
   Status: In Progress | Priority: Medium | Opened: July 10, 2026
   Assigned to: IT Support Team
   URL: https://company.atlassian.net/browse/IT-1234

2. IT-1189 — Laptop battery draining quickly
   Status: Waiting for Customer | Priority: Low | Opened: June 28, 2026
   Assigned to: Hardware Team
   URL: https://company.atlassian.net/browse/IT-1189
---
```

---

## 18. Verification Steps

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}' | jq -r '.access_token')

# 1. Check Jira health/config
curl -X GET http://localhost:8000/api/v1/it/query/health \
  -H "Authorization: Bearer $TOKEN"
# Expected: shows jira_api status

# 2. Get tickets directly (test endpoint)
curl -X GET http://localhost:8000/api/v1/tickets \
  -H "Authorization: Bearer $TOKEN"
# Expected: John's open tickets from Jira

# 3. Ask IT Agent about tickets
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "How many open tickets do I have?"}'
# Expected: Personalized response with ticket count and list

# 4. Ask about specific ticket status
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "Any update on my VPN ticket?"}'
# Expected: Status of the most relevant ticket

# 5. IT documentation query (should NOT trigger Jira)
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "How do I reset my password?"}'
# Expected: RAG-only response, no ticket data

# 6. Mixed query (ticket + troubleshooting)
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "My VPN ticket IT-1234 is still open, any other steps I can try?"}'
# Expected: Ticket status + troubleshooting steps from docs

# 7. User with no tickets (try with priya@company.com)
PRIYA_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"priya@company.com","password":"priya123"}' | jq -r '.access_token')

curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PRIYA_TOKEN" \
  -d '{"query": "How many open tickets do I have?"}'
# Expected: "You have no open tickets"

# 8. Verify Jira failures don't crash
# (Temporarily change JIRA_BASE_URL to invalid URL)
# Expected: Graceful error message, agent still works for non-Jira queries
```

---

## 19. Definition of Done

### Jira Service:
- [ ] `JiraService` class exists with async HTTP client
- [ ] `get_open_tickets()` queries Jira API with correct JQL
- [ ] JQL filters by reporter email and open status
- [ ] Response parsed to extract only relevant 7 fields
- [ ] Ticket URLs constructed correctly
- [ ] Timeout handling works (configurable)
- [ ] Rate limit detection from response headers
- [ ] All Jira error scenarios handled gracefully

### Tool Integration:
- [ ] `GetMyTicketsTool` wraps `JiraService`
- [ ] Tool registered in IT Agent's `ToolRegistry`
- [ ] `ToolSelectorService` correctly selects Jira tool for ticket queries
- [ ] `ToolSelectorService` does NOT select Jira tool for documentation queries
- [ ] Tool results formatted correctly in LLM prompt
- [ ] Tool errors don't crash the agent pipeline

### IT Agent:
- [ ] IT Agent uses tool registry with both tools (search_it_docs + get_my_tickets)
- [ ] Personalized ticket responses with clear formatting
- [ ] Backward compatible — existing IT queries unchanged
- [ ] System prompt updated to handle ticket data

### Configuration:
- [ ] Jira config in `.env` and `app/core/config.py`
- [ ] `.env.example` updated with Jira variables
- [ ] Missing config raises clear error on startup

### API:
- [ ] `GET /api/v1/tickets` returns user's open tickets
- [ ] Orchestrator responses include ticket data when relevant
- [ ] Health check includes Jira status

### Error Handling:
- [ ] Jira API down → graceful message
- [ ] Auth failure → logged, graceful message
- [ ] User not found → clear guidance
- [ ] Rate limit → wait suggestion
- [ ] Timeout → direct to Jira URL
- [ ] No tickets → positive message

### Security:
- [ ] Jira API token never exposed to frontend
- [ ] Users can only see their own tickets
- [ ] JQL built server-side, never from user input
- [ ] Read-only access to Jira
- [ ] Response data sanitized (only 7 fields exposed)