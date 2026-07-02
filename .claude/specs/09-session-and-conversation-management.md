# Feature 9: Session & Conversation Management

## 1. Overview

Build the session and conversation management system that enables multi-turn conversations. Users can have persistent chat sessions that survive page refreshes, maintain full conversation history, support multiple sessions per user, and automatically expire after 24 hours of inactivity.

This transforms the agent from **one-shot Q&A** into a **conversational assistant** that remembers context across messages.

---

## 2. Depends on

- **Feature 1: Project Setup & Docker Environment** — services running
- **Feature 2: Database Schema & Migrations** — sessions and messages tables exist
- **Feature 3: User Authentication** — JWT auth, user identity available
- **Feature 8: RAG Pipeline** — query endpoint stores messages in sessions

---

## 3. Routes

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `POST` | `/api/v1/sessions` | Yes (JWT) | Create a new conversation session |
| `GET` | `/api/v1/sessions` | Yes (JWT) | List all sessions for current user |
| `GET` | `/api/v1/sessions/{session_id}` | Yes (JWT) | Get session details with message history |
| `PATCH` | `/api/v1/sessions/{session_id}` | Yes (JWT) | Update session (rename, deactivate) |
| `DELETE` | `/api/v1/sessions/{session_id}` | Yes (JWT) | Delete a session and its messages |
| `GET` | `/api/v1/sessions/{session_id}/messages` | Yes (JWT) | Get paginated messages for a session |
| `DELETE` | `/api/v1/sessions/{session_id}/messages` | Yes (JWT) | Clear all messages in a session |

---

## 4. Route Specifications

### A. `POST /api/v1/sessions`

**Request Body:**
```json
{
  "title": "Remote Work Questions",
  "device_info": {
    "browser": "Chrome",
    "os": "MacOS",
    "platform": "desktop"
  }
}
```

**Validation:**
- `title`: Optional string, max 100 characters. If not provided, auto-generated from first message.
- `device_info`: Optional JSON object, stored as-is.

**Success Response (201):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Remote Work Questions",
  "is_active": true,
  "device_info": {
    "browser": "Chrome",
    "os": "MacOS",
    "platform": "desktop"
  },
  "message_count": 0,
  "created_at": "2026-07-01T10:00:00Z",
  "last_active": "2026-07-01T10:00:00Z",
  "expires_at": "2026-07-02T10:00:00Z"
}
```

---

### B. `GET /api/v1/sessions`

**Query Parameters:**
- `is_active` (optional, boolean): Filter by active/inactive sessions. Default: all.
- `limit` (optional, integer, default 20, max 50): Number of sessions to return.
- `offset` (optional, integer, default 0): Pagination offset.
- `sort_by` (optional, string, default "last_active"): Sort field. Options: `last_active`, `created_at`, `title`.
- `sort_order` (optional, string, default "desc"): `asc` or `desc`.

**Success Response (200):**
```json
{
  "sessions": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "title": "Remote Work Questions",
      "is_active": true,
      "message_count": 14,
      "last_message_preview": "Can I combine annual leave with remote work days?",
      "created_at": "2026-07-01T10:00:00Z",
      "last_active": "2026-07-01T14:30:00Z",
      "expires_at": "2026-07-02T10:00:00Z"
    },
    {
      "id": "770e8400-e29b-41d4-a716-446655440002",
      "title": "Leave Policy Questions",
      "is_active": true,
      "message_count": 8,
      "last_message_preview": "How many sick days do I get?",
      "created_at": "2026-06-30T09:00:00Z",
      "last_active": "2026-06-30T16:00:00Z",
      "expires_at": "2026-07-01T09:00:00Z"
    }
  ],
  "total": 5,
  "limit": 20,
  "offset": 0,
  "active_count": 3,
  "expired_count": 2
}
```

---

### C. `GET /api/v1/sessions/{session_id}`

**Path Parameter:** `session_id` — UUID of the session

**Success Response (200):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Remote Work Questions",
  "is_active": true,
  "device_info": {
    "browser": "Chrome",
    "os": "MacOS",
    "platform": "desktop"
  },
  "message_count": 14,
  "first_message_at": "2026-07-01T10:00:00Z",
  "last_active": "2026-07-01T14:30:00Z",
  "expires_at": "2026-07-02T10:00:00Z",
  "created_at": "2026-07-01T10:00:00Z",
  "updated_at": "2026-07-01T14:30:00Z"
}
```

**Error Responses:**
- `404` — Session not found
- `403` — Session belongs to different user

---

### D. `PATCH /api/v1/sessions/{session_id}`

**Request Body (all fields optional):**
```json
{
  "title": "Remote Work & Leave Questions",
  "is_active": false
}
```

**Success Response (200):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "title": "Remote Work & Leave Questions",
  "is_active": false,
  "updated_at": "2026-07-01T15:00:00Z",
  "message": "Session updated successfully"
}
```

---

### E. `DELETE /api/v1/sessions/{session_id}`

**Success Response (200):**
```json
{
  "message": "Session deleted successfully",
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "messages_deleted": 14
}
```

---

### F. `GET /api/v1/sessions/{session_id}/messages`

**Query Parameters:**
- `limit` (optional, integer, default 50, max 100): Messages per page.
- `offset` (optional, integer, default 0): Pagination offset.
- `before` (optional, ISO datetime): Get messages before this timestamp.
- `after` (optional, ISO datetime): Get messages after this timestamp.

**Success Response (200):**
```json
{
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "messages": [
    {
      "id": "880e8400-e29b-41d4-a716-446655440003",
      "role": "user",
      "content": "What is remote work policy?",
      "classification": "hr_question",
      "created_at": "2026-07-01T10:00:00Z"
    },
    {
      "id": "880e8400-e29b-41d4-a716-446655440004",
      "role": "assistant",
      "content": "Based on our remote work policy, employees may work remotely up to 2 days per week...",
      "sources": [
        {
          "document": "Remote Work Policy 2024",
          "page": 3,
          "section": "Eligibility",
          "excerpt": "Employees may work remotely..."
        }
      ],
      "confidence": "high",
      "tokens_used": 156,
      "created_at": "2026-07-01T10:00:01Z"
    }
  ],
  "total": 14,
  "limit": 50,
  "offset": 0
}
```

---

### G. `DELETE /api/v1/sessions/{session_id}/messages`

**Success Response (200):**
```json
{
  "message": "All messages cleared",
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "messages_deleted": 14
}
```

---

## 5. Session Lifecycle

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    SESSION LIFECYCLE                                                  │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                              │    │
│  │   CREATE ─────────────────────────────────────────────────────────────────► │    │
│  │   • User sends first message without session_id                              │    │
│  │   • POST /api/v1/sessions (manual creation)                                  │    │
│  │   • Status: is_active = true                                                │    │
│  │   • expires_at = now + 24 hours                                             │    │
│  │                                                                              │    │
│  │   ACTIVE ──────────────────────────────────────────────────────────────────► │    │
│  │   • User sends messages with session_id                                      │    │
│  │   • last_active updated on each message                                      │    │
│  │   • expires_at extended to now + 24 hours on each activity                   │    │
│  │   • Messages stored with session_id                                          │    │
│  │                                                                              │    │
│  │   EXPIRED ─────────────────────────────────────────────────────────────────► │    │
│  │   • No activity for 24 hours                                                 │    │
│  │   • Session still exists in database                                         │    │
│  │   • is_active automatically set to false                                     │    │
│  │   • Messages retained for audit                                             │    │
│  │   • User can view history but not add new messages                           │    │
│  │                                                                              │    │
│  │   DELETED ─────────────────────────────────────────────────────────────────► │    │
│  │   • User explicitly deletes session                                          │    │
│  │   • All messages in session deleted (CASCADE)                                │    │
│  │   • Feedback records for those messages deleted (CASCADE)                    │    │
│  │   • Irreversible                                                             │    │
│  │                                                                              │    │
│  │   CLEANED ─────────────────────────────────────────────────────────────────► │    │
│  │   • Background task runs periodically                                        │    │
│  │   • Hard deletes sessions expired > 7 days ago                               │    │
│  │   • Frees database storage                                                   │    │
│  │                                                                              │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Auto-Title Generation

When a session is created without a title (or on first message), generate a title from the first user message:

**Logic:**
1. Take the first user message (max 100 chars)
2. If message ≤ 50 chars, use it as-is
3. If message > 50 chars, truncate to 50 chars and append "..."
4. Clean the title: strip extra whitespace, capitalize first letter
5. If first message is a greeting ("hi", "hello"), use "New Conversation" until a substantive message arrives
6. Update title only if current title is "New Conversation" or null

**Examples:**
- "What is remote work policy?" → "What is remote work policy?"
- "Can you explain the complete leave policy including sick days and annual leave?" → "Can you explain the complete leave policy including..."
- "hi" → "New Conversation" (then updated on next message)
- "hello, I want to know about benefits" → "I want to know about benefits"

---

## 7. Session Expiry Logic

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    SESSION EXPIRY RULES                                               │
│                                                                                      │
│  1. ON CREATION:                                                                     │
│     expires_at = created_at + 24 hours                                                │
│                                                                                      │
│  2. ON ACTIVITY (each new message):                                                   │
│     last_active = NOW()                                                               │
│     expires_at = NOW() + 24 hours                                                     │
│     if is_active = false, set is_active = true (re-activate)                         │
│                                                                                      │
│  3. ON ACCESS CHECK:                                                                  │
│     if expires_at < NOW():                                                            │
│         set is_active = false                                                         │
│         return "Session expired"                                                      │
│         do NOT allow new messages                                                     │
│         DO allow viewing history                                                      │
│                                                                                      │
│  4. BACKGROUND CLEANUP (runs every 6 hours):                                          │
│     Hard delete sessions WHERE expires_at < NOW() - INTERVAL '7 days'                │
│     CASCADE deletes all messages and feedback                                         │
│                                                                                      │
│  5. MANUAL DEACTIVATION:                                                              │
│     User can PATCH /sessions/{id} with is_active=false                                │
│     Does NOT delete messages                                                          │
│     Preserves for audit                                                               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Session Auto-Creation in RAG Pipeline

Update the RAG pipeline (Feature 8) to auto-create sessions:

**When `session_id` is null in `/api/v1/query`:**
1. Create new session with:
   - `user_id`: from authenticated user
   - `title`: null (will be set from first substantive message)
   - `is_active`: true
   - `expires_at`: NOW() + 24 hours
2. Return `session_id` in the SSE `done` event
3. Frontend stores `session_id` for subsequent messages

**When `session_id` is provided:**
1. Load session from database
2. Verify session.user_id == authenticated user.id (403 if not)
3. Check if session is expired (update is_active if needed)
4. If expired, return error in SSE error event: "Session expired. Please start a new conversation."
5. If active, use session for this message
6. Update last_active and extends expires_at

---

## 9. Conversation History Loading

For the RAG pipeline's prompt building:

**Rules:**
- Load last N messages from the session (N = configurable, default 6)
- Only load messages where role IN ('user', 'assistant')
- Order by created_at DESC, then reverse for chronological order
- Limit total character count to prevent token overflow (max ~2000 chars for history)
- If total chars exceed limit, truncate oldest messages with "[Earlier conversation omitted]"

**Format for prompt:**
```
User: {content}
Assistant: {content}
User: {content}
Assistant: {content}
```

---

## 10. New Folder Structure (This Feature Only)

```
backend/app/
├── api/v1/
│   └── sessions.py              # Session CRUD endpoints
├── services/
│   └── session.py               # Session business logic
├── repositories/
│   ├── session.py               # Session data access
│   └── message.py               # Message data access (update if needed)
├── schemas/
│   └── session.py               # Session request/response schemas
├── core/
│   └── cleanup.py               # Background session cleanup task
```

---

## 11. Files to Create

### `app/api/v1/sessions.py`
- Router with prefix="" (full path in main.py), tags=["Sessions"]
- 7 endpoint handlers (POST, GET list, GET detail, PATCH, DELETE session, GET messages, DELETE messages)
- All endpoints protected by `get_current_user` dependency
- Session ownership validation on all session-specific endpoints
- Thin controllers — parse request, call service, return response

### `app/services/session.py`
- `SessionService` class
  - `__init__(db)` — store async session
  - `create_session(user_id, title, device_info) -> dict` — create new session
  - `get_session(session_id, user_id) -> dict` — get with ownership check
  - `list_sessions(user_id, filters) -> dict` — list with pagination
  - `update_session(session_id, user_id, updates) -> dict` — update title or active status
  - `delete_session(session_id, user_id) -> dict` — delete and return count
  - `get_messages(session_id, user_id, pagination) -> dict` — paginated messages
  - `clear_messages(session_id, user_id) -> dict` — delete all messages
  - `get_or_create_session(user_id, session_id) -> dict` — for RAG pipeline
  - `update_activity(session_id) -> None` — update last_active, extend expiry
  - `generate_title(first_message) -> str` — auto-title from first message
  - `extend_session(session_id) -> None` — extend expiry by 24 hours

### `app/repositories/session.py`
- `SessionRepository` class
  - `create(session_data) -> Session` — insert new session
  - `get_by_id(session_id) -> Optional[Session]` — get by ID
  - `get_by_user(user_id, filters, limit, offset) -> tuple[list[Session], int]` — paginated list
  - `update(session_id, updates) -> Session` — partial update
  - `delete(session_id) -> int` — delete with cascade count
  - `get_active_count(user_id) -> int` — count active sessions
  - `get_expired_sessions(cutoff_date) -> list[Session]` — for cleanup
  - `delete_expired_sessions(cutoff_date) -> int` — bulk delete for cleanup

### `app/repositories/message.py`
- `MessageRepository` class (new or extend existing)
  - `get_by_session(session_id, limit, offset, before, after) -> tuple[list[Message], int]`
  - `delete_by_session(session_id) -> int` — delete all messages in session
  - `count_by_session(session_id) -> int` — message count
  - `get_last_message(session_id) -> Optional[Message]` — for preview

### `app/schemas/session.py`
- `SessionCreate` — title (optional), device_info (optional)
- `SessionUpdate` — title (optional), is_active (optional)
- `SessionResponse` — id, user_id, title, is_active, device_info, message_count, first_message_at, last_active, expires_at, created_at, updated_at
- `SessionListItem` — id, title, is_active, message_count, last_message_preview, last_active, expires_at, created_at
- `SessionListResponse` — sessions (list), total, limit, offset, active_count, expired_count
- `MessageResponse` — id, role, content, sources, confidence, classification, tokens_used, created_at
- `MessageListResponse` — session_id, messages (list), total, limit, offset
- `SessionDeleteResponse` — message, session_id, messages_deleted
- `SessionClearResponse` — message, session_id, messages_deleted

### `app/core/cleanup.py`
- `SessionCleanup` class
  - `__init__(db_session_factory)` — store session factory
  - `async run_cleanup()` — delete sessions expired > 7 days
  - `async start_background_task()` — asyncio task that runs every 6 hours
  - `async stop_background_task()` — cancel the running task

---

## 12. Files to Change

### `app/main.py`
```python
from app.api.v1 import sessions
from app.core.cleanup import SessionCleanup
from app.database import AsyncSessionLocal

app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["Sessions"])

# On startup:
@app.on_event("startup")
async def startup():
    # ... existing init ...
    cleanup = SessionCleanup(AsyncSessionLocal)
    asyncio.create_task(cleanup.start_background_task())
```

### `app/services/rag.py`
Update `process_query()`:
- Call `SessionService.get_or_create_session()` instead of handling sessions inline
- Auto-create session when `session_id` is null
- Pass session through pipeline
- Return `session_id` in done event

### `app/config.py`
Add session settings:
```python
SESSION_EXPIRY_HOURS: int = 24
SESSION_CLEANUP_AFTER_DAYS: int = 7
SESSION_CLEANUP_INTERVAL_HOURS: int = 6
MAX_CONVERSATION_HISTORY_MESSAGES: int = 6
MAX_CONVERSATION_HISTORY_CHARS: int = 2000
AUTO_TITLE_MAX_LENGTH: int = 50
```

---

## 13. Dependencies

All already in `requirements.txt` — no new packages required.

---

## 14. Rules for Implementation

- **Session ownership**: Every session-specific endpoint must verify `session.user_id == current_user.id`
- **Auto-create on first message**: `/api/v1/query` with null session_id creates session automatically
- **Expiry extension**: Each new message extends expiry by 24 hours from current time
- **Expired sessions readonly**: Users can view history but cannot add messages
- **Re-activation**: Sending a message to an expired (but not hard-deleted) session re-activates it
- **Auto-title**: Generated from first substantive message (>5 chars, not just greeting)
- **Pagination**: All list endpoints support limit/offset
- **Soft delete via deactivation**: PATCH is_active=false preserves data
- **Hard delete via DELETE**: Removes session and all messages (CASCADE)
- **Background cleanup**: Only hard-deletes sessions expired > 7 days ago
- **Conversation history limit**: Max 6 messages or 2000 chars in prompts
- **Service returns dicts**: Framework-agnostic
- **Thin controllers**: Routes only parse request, call service, return response

---

## 15. Edge Cases

| Scenario | Handling |
|----------|----------|
| Session ID belongs to different user | 403 "You don't have access to this session" |
| Session not found | 404 "Session not found" |
| Message sent to expired session | 400 "Session has expired. Create a new session." |
| Message sent to deactivated session | 400 "Session is no longer active." |
| Title > 100 chars | 422 validation error |
| Empty title update | Keep existing title |
| Delete already deleted session | 404 |
| Concurrent messages in same session | Database handles via transactions (no special logic) |
| Session with no messages yet | title=null, message_count=0, first_message_at=null |
| User has 0 sessions | GET /sessions returns empty list with total=0 |

---

## 16. Database Operations

### Session auto-creation query:
```sql
INSERT INTO sessions (user_id, title, is_active, expires_at)
VALUES ($1, $2, true, NOW() + INTERVAL '24 hours')
RETURNING id, created_at
```

### Activity update query:
```sql
UPDATE sessions 
SET last_active = NOW(), 
    expires_at = NOW() + INTERVAL '24 hours',
    is_active = true
WHERE id = $1
```

### Expiry check query:
```sql
UPDATE sessions 
SET is_active = false 
WHERE expires_at < NOW() AND is_active = true
```

### Cleanup query:
```sql
DELETE FROM sessions 
WHERE expires_at < NOW() - INTERVAL '7 days'
```

### Message count query:
```sql
SELECT COUNT(*) FROM messages WHERE session_id = $1
```

### Last message preview:
```sql
SELECT content FROM messages 
WHERE session_id = $1 AND role = 'user'
ORDER BY created_at DESC 
LIMIT 1
```

---

## 17. Expected Behavior

### New conversation flow:
1. User sends first message without session_id
2. System auto-creates session
3. System auto-generates title from message
4. Session_id returned in response
5. Frontend stores session_id
6. Subsequent messages use this session_id

### Session listing:
1. User requests GET /sessions
2. Returns active sessions first (sorted by last_active desc)
3. Shows message count and last message preview
4. Shows expiry time
5. Supports pagination

### Session expiry:
1. Session inactive for 24 hours
2. is_active set to false on next access check
3. User can view history but not send new messages
4. After 7 more days, session hard-deleted by cleanup task

### Multiple sessions:
1. User can have unlimited active sessions
2. Each session is independent
3. Frontend shows session list for switching

---

## 18. Verification Steps

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}' | jq -r '.access_token')

# 1. Create session manually
curl -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title": "Test Session"}'

# 2. List sessions
curl -X GET "http://localhost:8000/api/v1/sessions?limit=10&sort_by=last_active&sort_order=desc" \
  -H "Authorization: Bearer $TOKEN"

# 3. Get session detail (replace SESSION_ID)
curl -X GET http://localhost:8000/api/v1/sessions/SESSION_ID \
  -H "Authorization: Bearer $TOKEN"

# 4. Update session title
curl -X PATCH http://localhost:8000/api/v1/sessions/SESSION_ID \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title": "Updated Title"}'

# 5. Send query with session (auto-creates if new)
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is remote work policy?", "session_id": "SESSION_ID"}'

# 6. Get session messages
curl -X GET "http://localhost:8000/api/v1/sessions/SESSION_ID/messages?limit=50" \
  -H "Authorization: Bearer $TOKEN"

# 7. Deactivate session
curl -X PATCH http://localhost:8000/api/v1/sessions/SESSION_ID \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"is_active": false}'

# 8. Delete session
curl -X DELETE http://localhost:8000/api/v1/sessions/SESSION_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

## 19. Definition of Done

### Session CRUD:
- [ ] `POST /api/v1/sessions` creates session with auto-generated title
- [ ] `GET /api/v1/sessions` lists sessions with pagination and sorting
- [ ] `GET /api/v1/sessions/{id}` returns session detail
- [ ] `PATCH /api/v1/sessions/{id}` updates title and active status
- [ ] `DELETE /api/v1/sessions/{id}` deletes session and all messages
- [ ] `GET /api/v1/sessions/{id}/messages` returns paginated messages
- [ ] `DELETE /api/v1/sessions/{id}/messages` clears all messages

### Session Ownership:
- [ ] Users can only access their own sessions
- [ ] Cross-user session access returns 403
- [ ] Session ownership checked on every request

### Auto-Creation in RAG Pipeline:
- [ ] Null session_id in query auto-creates session
- [ ] Session_id returned in SSE done event
- [ ] Title auto-generated from first substantive message
- [ ] Greeting-only first message → "New Conversation" title

### Expiry:
- [ ] Sessions expire after 24 hours of inactivity
- [ ] Expired sessions are readonly (view history, no new messages)
- [ ] New message to expired session re-activates it
- [ ] Background cleanup hard-deletes sessions expired > 7 days
- [ ] Cleanup runs every 6 hours

### Conversation History:
- [ ] Last 6 messages loaded for RAG prompt
- [ ] History truncated at 2000 chars to prevent token overflow
- [ ] Messages stored with correct role and metadata

### Edge Cases:
- [ ] Concurrent session access handled correctly
- [ ] Session with no messages handled gracefully
- [ ] Empty session list returns empty array
- [ ] Deactivated sessions filterable
- [ ] Pagination works correctly at boundaries