# Feature 13: IT Agent (RAG-based)

## 1. Overview

Build the IT Support agent by extending the `BaseAgent` class from Feature 12. The IT agent follows the exact same RAG pattern as the HR agent but with its own knowledge base collection, system prompts, and response templates. It answers IT-related questions (VPN, laptops, software, passwords, email, printers, network) using the company's IT documentation.

After this feature, the system will have two independently functioning agents — HR and IT — ready for orchestration in Feature 14.

---

## 2. Depends on

- **Feature 12: BaseAgent Pattern** — `BaseAgent` class must exist
- **Feature 4: Document Ingestion Pipeline** — ingestion service must support multiple collections
- **Feature 5: Vector Search Service** — search service must support collection parameter
- **Feature 6: Gemini Service Layer** — shared AI service
- **Feature 7: Query Classifier** — shared intent classification

---

## 3. Routes

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `POST` | `/api/v1/it/query` | Yes (JWT) | IT agent streaming query |
| `POST` | `/api/v1/it/query/test` | Yes (JWT) | IT agent non-streaming test |
| `GET` | `/api/v1/it/query/health` | No | IT agent health check |
| `POST` | `/api/v1/documents/upload` | Yes (JWT, admin) | Extended to accept IT documents |

---

## 4. Route Specifications

### A. `POST /api/v1/it/query` (Streaming)

**Request Body:**
```json
{
  "query": "My laptop won't connect to VPN",
  "session_id": null
}
```

**Response:** SSE stream (identical format to HR agent)

```
event: token
data: {"token": "Let's"}

event: token
data: {"token": " troubleshoot"}

event: token
data: {"token": " your"}

event: token
data: {"token": " VPN"}

... (continues) ...

event: sources
data: {"sources": [{"document": "VPN Troubleshooting Guide", "page": 2, "section": "Connection Issues", "excerpt": "If VPN fails to connect..."}]}

event: done
data: {"message_id": "uuid", "session_id": "uuid", "agent_name": "it", "confidence": "high", "tokens_used": 210, "processing_time_ms": 1100}
```

### B. `POST /api/v1/it/query/test` (Non-streaming)

**Request Body:** Same as streaming

**Success Response (200):**
```json
{
  "query": "My laptop won't connect to VPN",
  "agent_name": "it",
  "classification": "hr_question",
  "retrieved_chunks": [...],
  "answer": "Let's troubleshoot your VPN connection...",
  "sources": [...],
  "confidence": "high",
  "tokens_used": 210,
  "processing_time_ms": 1100
}
```

### C. `GET /api/v1/it/query/health`

**Success Response (200):**
```json
{
  "status": "healthy",
  "agent": "it",
  "documents_indexed": 45,
  "vector_index_exists": true
}
```

### D. `POST /api/v1/documents/upload` (Extended)

**Additional field in multipart form:**
- `agent_type`: String — `"hr"` or `"it"` (default: `"hr"`)

**Behavior:**
- `agent_type = "hr"` → stores in `hr_documents` collection (existing behavior)
- `agent_type = "it"` → stores in `it_documents` collection (new)

---

## 5. IT Agent Configuration

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    IT AGENT vs HR AGENT                                               │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  ATTRIBUTE              │  HR AGENT              │  IT AGENT                 │    │
│  ├──────────────────────────┼────────────────────────┼──────────────────────────┤    │
│  │  agent_name              │  "hr"                  │  "it"                     │    │
│  │  display_name            │  "HR Agent"            │  "IT Support"             │    │
│  │  collection_name         │  "hr_documents"        │  "it_documents"           │    │
│  │  system_prompt           │  HR-specific           │  IT-specific              │    │
│  │  greeting_response       │  HR greeting           │  IT greeting              │    │
│  │  bot_intro_response      │  HR capabilities       │  IT capabilities          │    │
│  │  out_of_domain_response  │  HR OOD                │  IT OOD                   │    │
│  └──────────────────────────┴────────────────────────┴──────────────────────────┤    │
│                                                                                      │
│  Everything else (pipeline logic, retrieval, confidence, streaming) is identical.    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. IT System Prompt

```
You are an IT support assistant for [Company Name]. Your job is to help employees with technical issues using ONLY the provided context from official IT documentation and troubleshooting guides.

RULES:
1. Answer ONLY using the information in the CONTEXT section below. Do not use outside knowledge.
2. If the CONTEXT doesn't contain a solution, say: "I couldn't find a specific solution in our IT documentation for this issue. I recommend contacting IT support directly at it-support@company.com or submitting a ticket via the IT portal."
3. Always cite your sources inline: [Source: Document Name, Page X, Section Y]
4. Be step-by-step and actionable. Use numbered steps for troubleshooting procedures.
5. Never make up technical details, commands, or settings not present in the context.
6. If a solution requires admin access, clearly state that.
7. For security-related issues (suspicious emails, password concerns), prioritize safety and recommend contacting IT security immediately.
8. Maintain a helpful, patient tone. Technical issues can be frustrating.
9. If the confidence is MEDIUM, add: "⚠️ I'm not fully confident in this solution. Please verify with IT support before proceeding."
10. Format your response clearly:
    - Numbered steps for procedures
    - Bullet points for options
    - Code/commands in backticks if applicable

CONVERSATION HISTORY:
{conversation_history}

CONTEXT FROM IT DOCUMENTATION:
---
{retrieved_context}
---

USER QUESTION: {user_query}

{confidence_note}

IT SUPPORT RESPONSE:
```

---

## 7. IT Direct Response Templates

### Greeting:
```
"Hello {user_name}! I'm your IT support assistant. I can help you with:

💻 Technical issues:
• Laptop and hardware problems
• VPN and network connectivity
• Software installation and updates
• Email and calendar issues
• Password resets and account access
• Printer and peripheral setup

What technical issue can I help you with today?"
```

### Bot Question:
```
"I'm the IT support assistant for [Company Name]. I help employees troubleshoot technical issues by searching through our IT documentation and guides.

I can assist with:
• VPN and network problems
• Laptop and hardware troubleshooting
• Software and application help
• Account and password issues
• Email and communication tools

Just describe your technical issue, and I'll find the relevant solution. How can I help?"
```

### Out of Domain:
```
"I'm specialized in IT support — I help with technical issues like laptops, VPN, software, and network problems.

If you're looking for:
• HR policies, benefits, or leave → the HR Agent can help
• Other non-technical topics → I'm not the right resource

Is there a technical issue I can help you troubleshoot?"
```

---

## 8. IT Fallback Responses

### Hard Fallback (No results or score < 0.30):
```
"I couldn't find information about this in our IT documentation.

Here's what I recommend:
• Contact IT support directly: it-support@company.com
• Submit a ticket via the IT portal: [portal link]
• Call the IT helpdesk: [phone number]

In the meantime, is there another technical issue I can help with?"
```

### Soft Fallback (Score 0.30 - 0.49):
```
"I found some related information but couldn't find a complete solution to your specific issue.

Here's what might help:
{list top 1-2 chunk excerpts if available}

I'd recommend:
• Trying the steps above first
• Contacting IT support if the issue persists: it-support@company.com
• Providing more details about your specific setup (OS version, error messages)

Is there another way I can help troubleshoot this?"
```

---

## 9. Database Changes

### New Collection: `it_documents`

Same schema as `hr_documents` — created in the same table with a collection discriminator, or as a separate table.

**Option A: Separate table (Recommended for isolation)**

```sql
CREATE TABLE IF NOT EXISTS it_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding VECTOR(768) NOT NULL,
    source VARCHAR(500) NOT NULL,
    page INTEGER,
    section VARCHAR(500),
    chunk_index INTEGER NOT NULL,
    access_level VARCHAR(50) NOT NULL DEFAULT 'all',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_it_documents_source ON it_documents(source);
CREATE INDEX IF NOT EXISTS idx_it_documents_access_level ON it_documents(access_level);
CREATE INDEX IF NOT EXISTS idx_it_documents_embedding ON it_documents 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Option B: Single table with collection column**

Add `collection VARCHAR(50) NOT NULL DEFAULT 'hr'` to existing `hr_documents` table (rename to `documents`). Less isolation but simpler queries.

**✅ Use Option A** — clean separation, no risk of cross-contamination, easier to backup/restore per agent.

---

## 10. Files to Create

### `app/agents/it_agent.py`

**Class: `ITAgent(BaseAgent)`**

Only defines the 7 required attributes — no method overrides:

```python
class ITAgent(BaseAgent):
    agent_name = "it"
    display_name = "IT Support"
    collection_name = "it_documents"
    system_prompt = IT_SYSTEM_PROMPT
    greeting_response = IT_GREETING_RESPONSE
    bot_intro_response = IT_BOT_INTRO_RESPONSE
    out_of_domain_response = IT_OOD_RESPONSE
```

All pipeline logic inherited from `BaseAgent`.

### `app/prompts/it_agent.py`

IT-specific prompt templates:
- `IT_SYSTEM_PROMPT`
- `IT_GREETING_RESPONSE`
- `IT_BOT_INTRO_RESPONSE`
- `IT_OOD_RESPONSE`
- `IT_HARD_FALLBACK_RESPONSE`
- `IT_SOFT_FALLBACK_RESPONSE`
- `IT_LOW_CONFIDENCE_DISCLAIMER`

### `app/api/v1/it_query.py`

Router for IT agent endpoints:
- `POST /` — streaming query (delegates to `ITAgent.process_query()`)
- `POST /test` — non-streaming test (delegates to `ITAgent.process_query_test()`)
- `GET /health` — IT agent health check
- All endpoints protected by `get_current_user`
- Thin controllers — parse request, create ITAgent, call method, format response

---

## 11. Files to Change

### `app/main.py`

Add IT router:
```python
from app.api.v1 import it_query

app.include_router(it_query.router, prefix="/api/v1/it/query", tags=["IT Agent"])
```

### `app/database.py`

Add `it_documents` table creation to `init_db()`:
- Same columns as `hr_documents`
- Separate vector index on `it_documents`

### `app/api/v1/documents.py`

Update upload endpoint:
- Accept `agent_type` field in multipart form (values: "hr", "it", default: "hr")
- Pass `collection_name` based on agent_type to ingestion service
- HR admin role still required

### `app/services/ingestion.py`

Update `ingest_document()`:
- Accept `collection_name` parameter (default: "hr_documents")
- Use `collection_name` when inserting chunks and embeddings
- All other logic unchanged

### `app/services/search.py`

Update `search()`:
- Accept `collection_name` parameter (default: "hr_documents")
- Query against the specified collection
- All other logic unchanged

### `app/core/constants.py`

Add IT-specific constants:
- `IT_SUPPORT_EMAIL = "it-support@company.com"`
- `IT_PORTAL_URL = "https://portal.company.com/it"`
- `IT_HELPDESK_PHONE = "ext. 4357"`

---

## 12. Files to Create

```
app/agents/it_agent.py
app/prompts/it_agent.py
app/api/v1/it_query.py
```

---

## 13. Files to Change

```
app/main.py                       (add IT router)
app/database.py                   (add it_documents table)
app/api/v1/documents.py           (accept agent_type)
app/services/ingestion.py         (accept collection_name)
app/services/search.py            (accept collection_name)
app/core/constants.py             (add IT constants)
```

---

## 14. Dependencies

No new packages. All existing dependencies sufficient.

---

## 15. Rules for Implementation

- **ITAgent only defines attributes**: No pipeline logic duplicated from BaseAgent
- **Separate pgvector table**: `it_documents` — not mixed with `hr_documents`
- **Same embedding model**: `text-embedding-004`, 768 dimensions
- **Same chunking strategy**: 1000 chars, 200 overlap
- **Same confidence thresholds**: Default values from BaseAgent
- **IT-specific prompts only**: No HR language in IT responses
- **IT support contact info**: Configurable in constants, not hardcoded in prompts
- **Document upload accepts agent_type**: Backward compatible (defaults to "hr")
- **Health endpoint shows IT-specific stats**: Document count, index status
- **Thin controllers**: Routes parse, create agent, call method, return response

---

## 16. IT Document Types to Support

Same file types as HR:
- PDF (`.pdf`)
- Word (`.docx`)
- Text (`.txt`)

---

## 17. Sample IT Documents for Testing

### `sample_docs/vpn_troubleshooting.txt`
```
VPN TROUBLESHOOTING GUIDE

Connection Issues:
1. Check your internet connection is working
2. Verify VPN client is installed (version 5.2 or higher)
3. Restart the VPN client: Click tray icon → Quit → Reopen
4. If still failing, try alternate server: vpn-backup.company.com
5. Clear cached credentials: Settings → Clear Saved Password → Re-enter

Common Error Codes:
- Error 789: Security layer failure. Solution: Update VPN client to latest version
- Error 809: Network connection blocked. Solution: Check firewall settings
- Error 720: No PPP control protocols. Solution: Contact IT support

Mac Users:
- Additional step: Allow VPN in System Preferences → Security & Privacy
- Required: macOS 12.0 or higher

Contact: it-support@company.com for persistent issues
```

### `sample_docs/password_reset.txt`
```
PASSWORD RESET PROCEDURE

Self-Service Reset:
1. Go to https://portal.company.com/reset
2. Enter your employee email
3. Verify identity via SMS or backup email
4. New password requirements:
   - Minimum 12 characters
   - At least 1 uppercase, 1 lowercase, 1 number, 1 symbol
   - Cannot reuse last 5 passwords
5. Password expires every 90 days

If Locked Out:
- Account locks after 5 failed attempts
- Auto-unlocks after 15 minutes
- Contact IT support for immediate unlock

VPN Password:
- VPN uses the same password as your company account
- Password sync may take up to 5 minutes after reset

Never share your password with anyone, including IT support.
```

---

## 18. Verification Steps

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"john@company.com","password":"john123"}' | jq -r '.access_token')

ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@company.com","password":"admin123"}' | jq -r '.access_token')

# 1. Upload IT document
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@sample_docs/vpn_troubleshooting.txt" \
  -F "agent_type=it" \
  -F "access_level=all"

# 2. Upload another IT document
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -F "file=@sample_docs/password_reset.txt" \
  -F "agent_type=it" \
  -F "access_level=all"

# 3. IT health check
curl http://localhost:8000/api/v1/it/query/health

# 4. IT query (non-streaming test)
curl -X POST http://localhost:8000/api/v1/it/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "My VPN is not connecting"}'

# 5. IT query (streaming)
curl -X POST http://localhost:8000/api/v1/it/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  -d '{"query": "How do I reset my password?"}' \
  --no-buffer

# 6. IT greeting
curl -X POST http://localhost:8000/api/v1/it/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "hi"}'

# 7. IT out of domain
curl -X POST http://localhost:8000/api/v1/it/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is the leave policy?"}'

# 8. Verify HR agent still works independently
curl -X POST http://localhost:8000/api/v1/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is remote work policy?"}'

# 9. Verify document isolation — IT query shouldn't return HR docs
curl -X POST http://localhost:8000/api/v1/it/query/test \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query": "What is the remote work policy?"}'
# Expected: IT agent says it can't help, redirects to HR agent
```

---

## 19. Definition of Done

### IT Agent:
- [ ] `ITAgent` class extends `BaseAgent` with only 7 attributes defined
- [ ] IT system prompt is IT-specific (no HR language)
- [ ] IT greeting response introduces IT capabilities
- [ ] IT out-of-domain response redirects to HR agent
- [ ] IT fallback responses include IT support contact info
- [ ] Streaming works token-by-token via SSE
- [ ] Non-streaming test endpoint returns complete response
- [ ] Health endpoint shows IT-specific stats

### Document Isolation:
- [ ] `it_documents` table exists with vector index
- [ ] IT documents stored separately from HR documents
- [ ] IT queries only search `it_documents` collection
- [ ] HR queries only search `hr_documents` collection
- [ ] Document upload accepts `agent_type` parameter
- [ ] Cross-contamination impossible (separate tables)

### Integration:
- [ ] HR agent still works exactly as before
- [ ] IT agent works independently with its own knowledge base
- [ ] Both agents share the same BaseAgent pipeline logic
- [ ] No code duplication between HR and IT agents

### API:
- [ ] `/api/v1/it/query` streaming endpoint works
- [ ] `/api/v1/it/query/test` non-streaming endpoint works
- [ ] `/api/v1/it/query/health` returns correct status
- [ ] All IT endpoints require authentication
- [ ] Document upload with `agent_type="it"` routes correctly