# Feature 15: Frontend Updates for Multi-Agent System

## 1. Overview

Update the web chat interface to reflect the new multi-agent architecture. The frontend now shows which agent is responding (HR Agent or IT Support), displays agent-specific welcome messages, provides visual differentiation between agents, and allows users to see the orchestrator's routing decisions.

This establishes the **multi-agent user experience** — users interact naturally with a single chat interface while the system intelligently routes to the right specialist behind the scenes.

---

## 2. Depends on

- **Feature 10: Streaming & Frontend** — existing chat interface
- **Feature 14: Agent Orchestrator** — orchestrator routing, agent_name in responses
- **Feature 13: IT Agent** — IT agent responses available
- **Feature 12: BaseAgent Pattern** — HR agent responses include agent metadata

---

## 3. Routes

No new backend routes. Frontend updates only.

All existing routes remain:
- `POST /api/v1/query` — main orchestrator endpoint (already used by frontend)
- `GET /api/v1/sessions` — session list
- `GET /api/v1/sessions/{id}/messages` — message history
- `POST /api/v1/feedback` — feedback submission

---

## 4. Frontend Changes Overview

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    FRONTEND CHANGES                                                   │
│                                                                                      │
│  CURRENT STATE                          TARGET STATE                                  │
│  ─────────────                          ────────────                                  │
│  Single "HR Agent" chat                Multi-agent chat with visual indicators       │
│  No agent labels on messages           Agent badge on each bot message               │
│  HR-only welcome message               Orchestrator welcome (both agents)            │
│  Single color scheme                   Agent-specific color accents                  │
│  No agent context in UI               Active agent indicator                        │
│  No suggestion chips                   Agent-specific suggestion chips               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Visual Design Changes

### Agent Color Scheme

| Agent | Primary Color | Badge Color | Message Accent |
|-------|--------------|-------------|----------------|
| Orchestrator | #6B7280 (Gray) | Gray | Neutral |
| HR Agent | #2563EB (Blue) | Blue | Left blue border |
| IT Support | #059669 (Green) | Green | Left green border |

### Agent Icons

| Agent | Icon | Display Name |
|-------|------|-------------|
| Orchestrator | 🤖 | Assistant |
| HR Agent | 📋 | HR Agent |
| IT Support | 💻 | IT Support |

---

## 6. UI Components to Update

### A. Welcome Message (New Chat)

**Before:**
```
Hello John! I'm your HR assistant. I can help with policies, leave, benefits...
```

**After:**
```
Hello John! 👋

I'm your company assistant. I can connect you with:

📋 HR Agent — for policies, leave, benefits, payroll, remote work
💻 IT Support — for laptops, VPN, software, passwords, network issues

What can I help you with today?
```

---

### B. Message Bubbles — Agent Identification

**Bot messages now include an agent badge:**

```
┌─────────────────────────────────────────────────────────────┐
│ 📋 HR Agent                                    High confidence │
│                                                             │
│ Based on our remote work policy, employees may work         │
│ remotely up to 2 days per week...                           │
│                                                             │
│ 📄 Sources (2)                                  👍  👎      │
└─────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────┐
│ 💻 IT Support                                  High confidence │
│                                                             │
│ Let's troubleshoot your VPN connection:                     │
│ 1. Check your internet connection...                        │
│                                                             │
│ 📄 Sources (1)                                  👍  👎      │
└─────────────────────────────────────────────────────────────┘
```

---

### C. Active Agent Indicator

In the chat header or input area, show which agent is currently active:

```
┌─────────────────────────────────────────────────────────────┐
│ Currently talking to: 📋 HR Agent                           │
│ [Type your message...]                          [Send]      │
└─────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Hidden on new chat (no active agent yet)
- Appears after first domain-classified response
- Updates when agent changes
- Shows "Switched to 💻 IT Support" briefly on domain change

---

### D. Suggestion Chips

After the welcome message, show clickable suggestion chips:

```
┌─────────────────────────────────────────────────────────────┐
│ Try asking:                                                 │
│ [What's the remote work policy?] [How many leave days?]     │
│ [VPN not connecting] [Reset my password]                    │
└─────────────────────────────────────────────────────────────┘
```

First row: HR examples, Second row: IT examples.

Clicking a chip populates the input and sends automatically.

---

### E. Agent Transition Indicator

When the orchestrator switches agents mid-conversation, show a subtle transition:

```
┌─────────────────────────────────────────────────────────────┐
│                   🔄 Switched to 💻 IT Support              │
│                                                             │
│ (Your IT-related question is being handled by IT Support)   │
└─────────────────────────────────────────────────────────────┘
```

This appears as a system message (not a user/bot bubble) between messages.

---

## 7. SSE Event Handling Updates

The `done` event now includes `agent_name`:

```json
{
  "message_id": "uuid",
  "session_id": "uuid",
  "agent_name": "hr",
  "confidence": "high",
  "tokens_used": 156,
  "processing_time_ms": 850
}
```

**Frontend must:**
- Extract `agent_name` from done event
- Apply correct agent styling to the completed message
- Update active agent indicator
- Store agent_name with message in local state

---

## 8. Message History Updates

When loading message history from `/api/v1/sessions/{id}/messages`, each assistant message may now have an `agent_name` field:

```json
{
  "id": "uuid",
  "role": "assistant",
  "content": "Based on our remote work policy...",
  "agent_name": "hr",
  "sources": [...],
  "confidence": "high",
  "created_at": "2026-07-01T10:00:00Z"
}
```

**Frontend must:**
- Read `agent_name` from stored messages
- Apply correct agent styling to historical messages
- Handle messages without `agent_name` (from before Feature 14) — default to "HR Agent"

---

## 9. Files to Change

### `frontend/index.html`

**Changes:**
- Add agent-specific CSS classes for styling
- Add suggestion chips container below welcome message area
- Add active agent indicator in chat header
- Add agent transition indicator template (hidden by default)
- Update welcome message template to mention both agents

---

### `frontend/css/style.css`

**Additions:**
- `.agent-badge` — base badge style
- `.agent-badge.hr` — blue badge for HR
- `.agent-badge.it` — green badge for IT
- `.agent-badge.orchestrator` — gray badge for orchestrator
- `.message-bubble.hr` — blue left border accent
- `.message-bubble.it` — green left border accent
- `.message-bubble.orchestrator` — gray left border accent
- `.active-agent-indicator` — fixed bar above input
- `.agent-transition` — system message style for agent switches
- `.suggestion-chips` — container for clickable chips
- `.suggestion-chip` — individual chip style
- `.suggestion-chip.hr` — blue chip
- `.suggestion-chip.it` — green chip

---

### `frontend/js/chat.js`

**Updates:**

- `addBotMessagePlaceholder()` — now accepts `agent_name` parameter
- `finalizeBotMessage(messageId, sources, confidence, agent_name)` — applies agent styling
- `addAgentBadge(element, agent_name)` — adds 📋 HR Agent or 💻 IT Support badge
- `addActiveAgentIndicator(agent_name)` — updates the "Currently talking to" indicator
- `addAgentTransition(old_agent, new_agent)` — shows transition message
- `showWelcomeMessage(userName)` — updated to mention both agents
- `addSuggestionChips()` — renders HR and IT suggestion chips
- `handleSuggestionChipClick(chipText)` — populates and sends query
- `loadMessages(messages)` — reads `agent_name` from stored messages

**Agent styling logic:**
```text
function getAgentConfig(agent_name):
    if agent_name == "hr":
        return { icon: "📋", label: "HR Agent", cssClass: "hr", color: "#2563EB" }
    if agent_name == "it":
        return { icon: "💻", label: "IT Support", cssClass: "it", color: "#059669" }
    if agent_name == "orchestrator":
        return { icon: "🤖", label: "Assistant", cssClass: "orchestrator", color: "#6B7280" }
    return { icon: "🤖", label: "Assistant", cssClass: "orchestrator", color: "#6B7280" }
```

---

### `frontend/js/streaming.js`

**Updates:**

- `handleDoneEvent(data)` — extracts `agent_name` from data, passes to `finalizeBotMessage()`
- `startStream(query, sessionId)` — no changes needed, SSE parsing is generic

---

### `frontend/js/sessions.js`

**Updates:**

- `renderSessionList(sessions)` — optionally show agent icon next to last message preview
- `loadMessages(messages)` — passes `agent_name` to message rendering

---

### `frontend/js/app.js`

**Updates:**

- `showChatPage()` — renders new welcome message with both agents
- `init()` — no changes, orchestrator endpoint is same URL

---

## 10. Files to Change (Summary)

```
frontend/index.html              (welcome message, suggestion chips, agent indicator)
frontend/css/style.css           (agent-specific styles, badges, transitions)
frontend/js/chat.js              (agent badges, active indicator, transitions, chips)
frontend/js/streaming.js         (extract agent_name from done event)
frontend/js/sessions.js          (agent info in history)
frontend/js/app.js               (updated welcome message)
```

---

## 11. Files to Create

None — all changes are modifications to existing frontend files.

---

## 12. Dependencies

No new packages. Vanilla HTML/CSS/JS.

---

## 13. Rules for Implementation

- **Single chat interface**: Users don't choose agents — the system routes automatically
- **Agent identity is informational**: Shows who answered, but doesn't require user action
- **Graceful fallback**: Messages without `agent_name` (old data) default to HR styling
- **No agent selector**: Users don't manually pick HR vs IT (orchestrator handles it)
- **Transition is subtle**: Agent switch indicator is informative, not disruptive
- **Streaming preserved**: Agent badge appears when streaming completes (not during)
- **Suggestion chips are optional**: Can be hidden if not relevant
- **Responsive design**: Agent badges and indicators work on mobile

---

## 14. Suggestion Chips Configuration

```javascript
const SUGGESTION_CHIPS = [
    // HR suggestions (blue)
    { text: "What's the remote work policy?", agent: "hr" },
    { text: "How many leave days do I get?", agent: "hr" },
    { text: "Tell me about health benefits", agent: "hr" },
    
    // IT suggestions (green)
    { text: "VPN not connecting", agent: "it" },
    { text: "Reset my password", agent: "it" },
    { text: "Laptop won't turn on", agent: "it" },
];
```

Show 3-4 chips initially, with option to show more.

---

## 15. Backward Compatibility

| Scenario | Handling |
|----------|----------|
| Old message without `agent_name` | Default to HR Agent styling |
| Session from before Feature 14 | No `active_agent` — treat as new |
| Direct agent endpoint response | `agent_name` from response metadata |
| Orchestrator response | `agent_name` from done SSE event |

---

## 16. Verification Steps

```bash
# Start all services
docker compose up -d

# Open browser at http://localhost

# 1. Check welcome message
# → Should mention both HR Agent and IT Support

# 2. Check suggestion chips
# → Should show clickable HR and IT suggestions
# → Clicking a chip sends the query

# 3. Send HR query
# → "What is remote work policy?"
# → Response should show 📋 HR Agent badge with blue accent

# 4. Send IT query
# → "VPN not connecting"
# → Response should show 💻 IT Support badge with green accent

# 5. Check agent transition
# → After HR query, send IT query in same session
# → Should show "Switched to 💻 IT Support" transition

# 6. Send follow-up
# → After IT query, send "tell me more"
# → Should stay on IT Support (no transition)

# 7. Send greeting
# → "hi"
# → Should show 🤖 Assistant badge (orchestrator)

# 8. Refresh page, load session history
# → Old messages should show correct agent badges

# 9. Check active agent indicator
# → After first agent response, indicator shows current agent
# → Updates on agent switch

# 10. Mobile responsiveness
# → Agent badges and indicators should display correctly on narrow screens
```

---

## 17. Definition of Done

### Agent Identification:
- [ ] Each bot message shows correct agent badge (📋 HR Agent, 💻 IT Support, 🤖 Assistant)
- [ ] Agent badge color matches agent (blue/green/gray)
- [ ] Message bubble has subtle agent-specific accent (left border)
- [ ] Agent badge appears after streaming completes

### Welcome & Suggestions:
- [ ] Welcome message introduces both HR and IT agents
- [ ] Suggestion chips show sample HR and IT queries
- [ ] Clicking a chip sends the query
- [ ] Chips are color-coded by agent

### Active Agent Indicator:
- [ ] Shows current agent in chat header/input area
- [ ] Hidden on new chat (no active agent)
- [ ] Updates when agent changes
- [ ] Shows transition message on agent switch

### Streaming:
- [ ] `agent_name` extracted from SSE done event
- [ ] Agent styling applied to completed message
- [ ] Streaming UX unchanged (token-by-token)

### History:
- [ ] Old messages loaded with correct agent badges
- [ ] Messages without `agent_name` default to HR styling
- [ ] Session list shows agent context where relevant

### Responsive:
- [ ] Agent badges readable on mobile
- [ ] Active indicator fits on narrow screens
- [ ] Suggestion chips wrap correctly

### Browser Compatibility:
- [ ] Chrome (latest 2 versions)
- [ ] Firefox (latest 2 versions)
- [ ] Edge (latest 2 versions)
- [ ] Safari (latest 2 versions)