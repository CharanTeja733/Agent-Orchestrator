# Feature 10: Streaming & Frontend

## 1. Overview

Build the web-based chat interface for the HR Q&A Agent. The frontend connects to the FastAPI backend, displays a chat window with streaming token-by-token responses, shows source citations, supports session management (new chat, chat history), user authentication (login/register), and displays confidence levels.

This establishes the **user experience layer** — the interface employees actually use to interact with the HR agent.

---

## 2. Depends on

- **Feature 1: Project Setup & Docker Environment** — services running, frontend container exists
- **Feature 3: User Authentication** — login/register endpoints
- **Feature 8: RAG Pipeline** — streaming `/api/v1/query` endpoint
- **Feature 9: Session & Conversation Management** — session list, history, messages endpoints

---

## 3. Frontend Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    FRONTEND ARCHITECTURE                                              │
│                                                                                      │
│  Technology: HTML + CSS + Vanilla JavaScript (no framework)                          │
│  Rationale: Simple, zero dependencies, easy to deploy, sufficient for internal tool  │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                         SINGLE PAGE APPLICATION                              │    │
│  │                                                                              │    │
│  │  ┌──────────┐    ┌──────────────────────────────────────────────────────┐    │    │
│  │  │  LOGIN   │    │                  CHAT INTERFACE                       │    │    │
│  │  │  PAGE    │    │                                                       │    │    │
│  │  │          │    │  ┌─────────┐  ┌──────────────────────────────────┐   │    │    │
│  │  │  Email   │    │  │ SIDEBAR │  │  CHAT AREA                        │   │    │    │
│  │  │  Password│    │  │         │  │                                   │   │    │    │
│  │  │          │    │  │ • New   │  │  ┌─────────────────────────────┐  │   │    │    │
│  │  │ [Login]  │    │  │   Chat  │  │  │  MESSAGE HISTORY            │  │   │    │    │
│  │  │          │    │  │         │  │  │                             │  │   │    │    │
│  │  │ Register │    │  │ • Chat 1│  │  │  User: What is remote...    │  │   │    │    │
│  │  │   link   │    │  │ • Chat 2│  │  │  Bot: Based on our policy...│  │   │    │    │
│  │  └──────────┘    │  │ • Chat 3│  │  │  📄 Sources (2)             │  │   │    │    │
│  │                  │  │         │  │  │  👍 👎                      │  │   │    │    │
│  │                  │  │ [Logout]│  │  └─────────────────────────────┘  │   │    │    │
│  │                  │  └─────────┘  │                                   │   │    │    │
│  │                  │               │  ┌─────────────────────────────┐  │   │    │    │
│  │                  │               │  │  CHAT INPUT                  │  │   │    │    │
│  │                  │               │  │  [Type message...]  [Send]   │  │   │    │    │
│  │                  │               │  └─────────────────────────────┘  │   │    │    │
│  │                  │               └──────────────────────────────────┘   │    │    │
│  │                  └──────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Pages & Views

### A. Login Page (`/` or `#login`)

**Elements:**
- App logo/title: "HR Q&A Agent"
- Email input field
- Password input field
- "Login" button
- "Register" link (switches to registration form)
- Error message area (hidden by default)
- Loading spinner on submit

**Registration form (toggle):**
- Full name input field
- Email input field
- Department dropdown (engineering, sales, hr, marketing, finance, other)
- Role dropdown (employee, manager, hr_admin)
- Password input field
- Confirm password input field
- "Register" button
- "Back to Login" link
- Validation errors displayed inline

---

### B. Chat Interface (`#chat`)

**Sidebar (left, ~280px):**
- User info header (name, role badge, department)
- "New Chat" button (prominent)
- Session list (scrollable):
  - Each item shows: title, last message preview, timestamp, message count
  - Active session highlighted
  - Hover shows delete icon
- "Logout" button at bottom

**Chat Area (center, remaining width):**

**Message Display:**
- Welcome message on new chat:
  ```
  Hello {user_name}! 👋
  
  I'm your HR assistant. I can help you with:
  • Company policies and procedures
  • Leave and time-off policies
  • Benefits and insurance
  • Remote work guidelines
  • Payroll and compensation
  
  What would you like to know?
  ```
- User messages (right-aligned, blue/gray bubble)
- Bot messages (left-aligned, white/light bubble)
- Streaming bot message: text appears token by token
- Loading indicator during retrieval (before first token): animated dots
- Source citations below bot messages (collapsible)
- Confidence badge on bot messages (high=green, medium=yellow, low=red)
- Feedback buttons (👍/👎) below each bot message

**Message Bubble Content:**
- Sender icon/avatar (bot icon or user initial)
- Message text (rendered with markdown-like formatting)
- Timestamp
- For bot messages: confidence badge, source count, feedback buttons

**Chat Input (bottom bar, fixed):**
- Text input field (multi-line, auto-expanding up to 5 lines)
- Send button (disabled when empty or loading)
- Character count indicator
- "Enter to send, Shift+Enter for new line" tooltip
- Disabled state during bot response (shows "Waiting for response...")

---

## 5. Frontend State Management

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    FRONTEND STATE                                                     │
│                                                                                      │
│  App State (stored in JavaScript object):                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  {                                                                           │    │
│  │    "auth": {                                                                 │    │
│  │      "token": "eyJ...",           // JWT access token                        │    │
│  │      "refresh_token": "eyJ...",   // JWT refresh token                       │    │
│  │      "user": { ... },             // User object from /auth/me               │    │
│  │      "isAuthenticated": false     // Current auth state                      │    │
│  │    },                                                                        │    │
│  │    "chat": {                                                                 │    │
│  │      "activeSessionId": null,     // Currently active session UUID           │    │
│  │      "sessions": [],              // List of user's sessions                 │    │
│  │      "messages": [],              // Messages in active session              │    │
│  │      "isStreaming": false,        // Currently receiving bot response        │    │
│  │      "streamingMessageId": null   // ID of message being streamed            │    │
│  │    },                                                                        │    │
│  │    "ui": {                                                                   │    │
│  │      "currentPage": "login",      // 'login' or 'chat'                       │    │
│  │      "sidebarOpen": true,         // Sidebar visibility on mobile            │    │
│  │      "isLoading": false,          // Global loading state                    │    │
│  │      "error": null                // Global error message                    │    │
│  │    }                                                                         │    │
│  │  }                                                                           │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  LocalStorage Persistence:                                                            │
│  • auth.token (access token)                                                          │
│  • auth.refresh_token                                                                 │
│  • auth.user (basic info only: id, name, email)                                       │
│  • chat.activeSessionId                                                               │
│                                                                                      │
│  NOT persisted (loaded fresh from API):                                               │
│  • Session list (loaded on login)                                                     │
│  • Messages (loaded when session selected)                                            │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Frontend File Structure

```
frontend/
├── index.html              # Main HTML file (SPA)
├── css/
│   └── style.css           # All styles
├── js/
│   ├── app.js              # App initialization, state, routing
│   ├── api.js              # All API calls to backend
│   ├── auth.js             # Login/register/logout logic
│   ├── chat.js             # Chat interface logic
│   ├── sessions.js         # Session management logic
│   ├── streaming.js        # SSE handling for token streaming
│   └── utils.js            # Helper functions (formatting, dates, markdown)
└── Dockerfile              # Updated from Feature 1
```

---

## 7. Files to Create/Update

### `frontend/index.html`

**Structure:**
- Single HTML file with two main `<div>` sections: `#login-page` and `#chat-page`
- Only one visible at a time (controlled by CSS class `hidden`)
- Link to `css/style.css`
- Script imports at bottom: all JS files in dependency order
- Meta tags for responsive design
- Favicon/icon

**Login Page Section (`#login-page`):**
- Container div centered on page
- App title/logo
- Form with email, password inputs
- Submit button
- Toggle link to registration form
- Registration form (hidden by default): adds name, department select, role select, confirm password
- Error message div

**Chat Page Section (`#chat-page`):**
- Sidebar div: user info, new chat button, session list container
- Main chat div: messages container, welcome message, chat input bar
- Source panel (slide-out or expandable)
- Loading overlay for initial data fetch

---

### `frontend/css/style.css`

**Design System:**
- Color palette:
  - Primary: #2563EB (blue)
  - Primary dark: #1D4ED8
  - Background: #F8FAFC (light gray)
  - Sidebar: #1E293B (dark)
  - User bubble: #DBEAFE (light blue)
  - Bot bubble: #FFFFFF (white)
  - Text primary: #1E293B
  - Text secondary: #64748B
  - Success/High confidence: #16A34A (green)
  - Warning/Medium: #D97706 (amber)
  - Error/Low confidence: #DC2626 (red)
  - Border: #E2E8F0

**Layout:**
- Full viewport height (`100vh`)
- Flexbox layout for sidebar + main area
- Sidebar: fixed width 280px, full height, scrollable sessions list
- Chat area: flex-grow, flex column (messages scrollable, input fixed bottom)
- Responsive: sidebar collapses on < 768px, hamburger toggle

**Components Styled:**
- Input fields (email, password, text)
- Buttons (primary, secondary, danger, icon)
- Message bubbles (user, bot, streaming)
- Session list items (default, active, hover)
- Badges (confidence: high/medium/low, role)
- Source citations (collapsible accordion)
- Loading spinner
- Scrollbar (custom, thin)
- Toast notifications (success, error)
- Feedback buttons (thumbs up/down)

---

### `frontend/js/app.js`

**Responsibilities:**
- Initialize application
- Check for stored auth token on page load
- If token exists: validate with `/auth/me`, switch to chat page
- If no token: show login page
- Set up automatic token refresh (5 minutes before expiry)
- Global error handling (401 → redirect to login, network errors → toast)
- Page routing between login and chat views

**Key Functions:**
- `init()` — entry point, check auth state
- `showLoginPage()` — display login, hide chat
- `showChatPage()` — display chat, hide login, load sessions
- `handleAuthError()` — clear token, show login
- `setupTokenRefresh()` — set interval for refresh

---

### `frontend/js/api.js`

**Responsibilities:**
- Centralized API communication
- Automatically attach Authorization header
- Handle response parsing
- Handle common error codes

**Key Functions:**
- `apiGet(url, params)` — GET request with query params
- `apiPost(url, body)` — POST request with JSON body
- `apiPatch(url, body)` — PATCH request
- `apiDelete(url)` — DELETE request
- `apiStream(url, body, onToken, onSources, onDone, onError)` — SSE stream handler
- Base URL configuration: `http://backend:8000/api/v1` (Docker network) or `http://localhost:8000/api/v1` (local dev)

**SSE Streaming Implementation:**
```text
1. Create fetch() with Authorization header
2. Get ReadableStream from response.body
3. Parse SSE events from stream chunks:
   - Split by double newline
   - Extract event type and data
   - Parse JSON data
4. Call appropriate callback:
   - event:token → onToken(data.token)
   - event:sources → onSources(data.sources)
   - event:done → onDone(data)
   - event:error → onError(data)
5. Handle stream interruption (user navigates away, network loss)
```

---

### `frontend/js/auth.js`

**Responsibilities:**
- Login form handling
- Registration form handling
- Logout
- Token storage and retrieval

**Key Functions:**
- `handleLogin(event)` — prevent default, validate, call API, store token, redirect
- `handleRegister(event)` — validate passwords match, call API, show success, switch to login
- `handleLogout()` — clear storage, clear state, show login page
- `validateEmail(email)` — basic email format check
- `validatePassword(password)` — min 8 chars, complexity requirements
- `storeAuth(token, refreshToken, user)` — save to localStorage and state
- `clearAuth()` — remove from localStorage and state
- `refreshToken()` — call `/auth/refresh`, update stored token

---

### `frontend/js/chat.js`

**Responsibilities:**
- Message display and management
- Send user queries
- Handle bot responses
- Display sources and confidence
- Feedback buttons

**Key Functions:**
- `sendMessage()` — get input text, add user bubble, call API, handle response
- `addUserMessage(text)` — create user message bubble, append to chat
- `addBotMessagePlaceholder()` — create empty bot bubble with loading indicator
- `updateBotMessage(token)` — append token to streaming bot bubble
- `finalizeBotMessage(messageId, sources, confidence)` — finalize streaming message, add sources
- `addSourceCitations(sources)` — create collapsible source list
- `addConfidenceBadge(confidence)` — add colored confidence indicator
- `addFeedbackButtons(messageId)` — add thumbs up/down
- `handleFeedback(messageId, rating)` — send feedback to API (Feature 11 prep)
- `scrollToBottom()` — auto-scroll chat to latest message
- `showWelcomeMessage(userName)` — display welcome message for new chats
- `clearChat()` — remove all messages from display
- `loadMessages(messages)` — render message history from session

---

### `frontend/js/sessions.js`

**Responsibilities:**
- Session list in sidebar
- Create new chat
- Switch between sessions
- Delete sessions
- Rename sessions

**Key Functions:**
- `loadSessions()` — fetch session list from API, render sidebar
- `renderSessionList(sessions)` — build session list DOM elements
- `createNewChat()` — clear active session, show welcome message
- `switchSession(sessionId)` — load messages for selected session
- `deleteSession(sessionId)` — confirm, delete via API, remove from list
- `renameSession(sessionId, newTitle)` — update via API
- `updateSessionPreview(sessionId)` — update last message preview in sidebar
- `highlightActiveSession(sessionId)` — visual indicator on active session

---

### `frontend/js/streaming.js`

**Responsibilities:**
- Handle SSE stream from `/api/v1/query`
- Parse incoming events
- Update UI in real-time

**Key Functions:**
- `startStream(query, sessionId)` — initiate SSE connection, return abort controller
- `stopStream(abortController)` — abort ongoing stream (user cancels or navigates away)
- `handleTokenEvent(token)` — call chat.updateBotMessage()
- `handleSourcesEvent(sources)` — call chat.addSourceCitations()
- `handleDoneEvent(data)` — call chat.finalizeBotMessage(), update session preview
- `handleErrorEvent(data)` — show error in chat, enable input
- `createSSEReader(response)` — parse fetch response body as SSE stream

---

### `frontend/js/utils.js`

**Responsibilities:**
- Pure utility functions used across modules

**Key Functions:**
- `formatDate(isoString)` — format timestamp to "Jul 1, 2026 10:30 AM"
- `formatRelativeTime(isoString)` — "2 hours ago", "Yesterday", "3 days ago"
- `truncateText(text, maxLength)` — truncate with ellipsis
- `simpleMarkdown(text)` — convert **bold**, *italic*, bullet points, numbered lists to HTML
- `escapeHtml(text)` — prevent XSS
- `debounce(func, delay)` — debounce function calls
- `generateId()` — generate temporary unique IDs for UI elements
- `getConfidenceColor(confidence)` — return CSS class for confidence level
- `getRoleBadge(role)` — return formatted role display text

---

## 8. Frontend Docker Configuration

### `frontend/Dockerfile`

```dockerfile
FROM nginx:alpine
COPY . /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### `frontend/nginx.conf`

```nginx
server {
    listen 80;
    server_name localhost;
    
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
    
    # Proxy API calls to backend
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Disable buffering for SSE streaming
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```

---

## 9. Changes to Existing Files

### `backend/app/main.py`

Update CORS settings:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://frontend:80", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### `docker-compose.yml`

Update frontend service:
```yaml
frontend:
  build: ./frontend
  container_name: hr-agent-frontend
  ports:
    - "80:80"
  depends_on:
    - backend
  restart: unless-stopped
```

---

## 10. New Dependencies

None — vanilla HTML/CSS/JS, no frameworks or npm packages.

---

## 11. Rules for Implementation

- **Vanilla JavaScript only**: No React, Vue, Angular, or other frameworks
- **No npm/build step**: All files served directly by nginx
- **Progressive enhancement**: Works without JavaScript disabled (basic form submission)
- **Accessibility**: ARIA labels, keyboard navigation, focus management
- **Security**:
  - Escape all user-generated content before rendering (prevent XSS)
  - Tokens stored in localStorage (acceptable for internal tool)
  - Never expose refresh token in URLs
- **Responsive**: Works on desktop (primary) and tablet (secondary), mobile (basic)
- **Error handling**: Network errors show toast, 401 clears auth, 500 shows error message
- **Streaming handling**: Cancel stream on navigation, handle disconnect gracefully
- **No hardcoded API URLs**: Use relative paths or configurable base URL

---

## 12. SSE Client Implementation Details

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    SSE CLIENT IMPLEMENTATION                                          │
│                                                                                      │
│  Function: startStream(query, sessionId)                                              │
│                                                                                      │
│  1. Create AbortController for cancellation                                          │
│                                                                                      │
│  2. fetch() POST to /api/v1/query with:                                              │
│     - Headers: Authorization, Content-Type, Accept: text/event-stream                │
│     - Body: JSON { query, session_id }                                               │
│     - Signal: abortController.signal                                                 │
│                                                                                      │
│  3. Get response.body.getReader()                                                     │
│                                                                                      │
│  4. Read chunks in while loop:                                                       │
│     a. Decode chunk (Uint8Array → text via TextDecoder)                              │
│     b. Append to buffer                                                              │
│     c. Split buffer by "\n\n" (SSE event delimiter)                                 │
│     d. Process complete events, keep incomplete in buffer                            │
│                                                                                      │
│  5. For each complete event:                                                         │
│     a. Parse lines: "event: <type>" and "data: <json>"                               │
│     b. Switch on event type:                                                         │
│        - "token": append token to streaming message                                  │
│        - "sources": store sources for display after streaming                        │
│        - "done": finalize message, enable input, store message_id                    │
│        - "error": show error, enable input                                           │
│                                                                                      │
│  6. Handle errors:                                                                    │
│     - AbortError: user cancelled (normal)                                            │
│     - NetworkError: show "Connection lost" toast                                     │
│     - Other: show error message                                                      │
│                                                                                      │
│  7. Return abortController for external cancellation                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. User Flow

### Login Flow:
1. User opens app → sees login page
2. Enters credentials → clicks Login
3. Loading spinner shows
4. On success → chat page loads with welcome message
5. On failure → error message displayed
6. If token exists in localStorage → auto-login, validate, go to chat

### Chat Flow:
1. User types question → clicks Send or presses Enter
2. User message bubble appears immediately
3. Bot placeholder appears with loading dots
4. Input disabled (grayed out)
5. Tokens stream into bot bubble one by one
6. After streaming completes:
   - Sources appear below message
   - Confidence badge shows
   - Feedback buttons appear
   - Input re-enabled
7. Session list updates with new/last message preview

### New Chat Flow:
1. User clicks "New Chat" in sidebar
2. Current chat cleared
3. Welcome message displayed
4. activeSessionId set to null
5. Next message will auto-create new session

### Session Switch Flow:
1. User clicks session in sidebar
2. Chat area clears
3. Loading indicator shows
4. Messages loaded from API
5. All messages rendered (not streamed — history loaded instantly)
6. Input enabled for new messages

---

## 14. Source Display Design

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    SOURCE CITATION DISPLAY                                            │
│                                                                                      │
│  Below each bot message:                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  📄 Sources (3)                                              [Expand ▼]      │    │
│  │  ┌─────────────────────────────────────────────────────────────────────────┐│    │
│  │  │ 1. Remote Work Policy 2024 — Page 3, Section 2.1: Eligibility          ││    │
│  │  │    "Employees may work remotely up to 2 days per week with manager      ││    │
│  │  │     approval. Minimum tenure of 3 months required..."                   ││    │
│  │  │                                                                         ││    │
│  │  │ 2. Employee Handbook — Page 15, Remote Work Guidelines                  ││    │
│  │  │    "Remote work must be scheduled at least 24 hours in advance..."      ││    │
│  │  │                                                                         ││    │
│  │  │ 3. Leave Policy 2024 — Page 2, Leave Combination Rules                  ││    │
│  │  │    "Annual leave may be combined with remote work days..."              ││    │
│  │  └─────────────────────────────────────────────────────────────────────────┘│    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  Default: Collapsed — shows "📄 Sources (3)" with expand toggle                      │
│  Expanded: Shows all sources with excerpt                                            │
│  Confidence badge shown next to source count: 🟢 High / 🟡 Medium / 🔴 Low           │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 15. Error Display

### Toast Notifications:
- Success: Green, auto-dismiss 3s (e.g., "Session deleted")
- Error: Red, with dismiss button (e.g., "Failed to send message")
- Warning: Yellow, auto-dismiss 5s (e.g., "Session expired, new session created")

### Inline Errors:
- Login: Red text below form ("Invalid email or password")
- Chat: Error bubble in chat ("I'm having trouble responding. Please try again.")
- Session: Red text in sidebar if load fails

### Network Errors:
- Full-page overlay if completely offline
- "Reconnecting..." indicator during temporary disconnect
- Auto-retry on reconnect

---

## 16. Accessibility Requirements

- All interactive elements have ARIA labels
- Keyboard navigation:
  - Tab through inputs and buttons
  - Enter to send message
  - Escape to close panels
- Focus management:
  - Input auto-focused on chat page load
  - Focus returns to input after sending
- Screen reader support:
  - New messages announced
  - Loading state announced
  - Error messages announced
- Color contrast meets WCAG AA (minimum)

---

## 17. Definition of Done

### Login & Auth:
- [ ] Login page renders correctly with email/password fields
- [ ] Registration form toggles with all fields
- [ ] Login API call works and stores token
- [ ] Registration validates passwords match
- [ ] Auto-login from stored token works
- [ ] Token refresh works before expiry
- [ ] Logout clears state and redirects to login

### Chat Interface:
- [ ] Chat page renders with sidebar and chat area
- [ ] Welcome message shows on new chat with user name
- [ ] User messages appear as right-aligned bubbles
- [ ] Input disabled during bot response
- [ ] Enter sends, Shift+Enter adds new line
- [ ] Auto-scroll to latest message

### Streaming:
- [ ] Tokens appear in bot bubble one by one
- [ ] Loading indicator shows before first token
- [ ] Sources appear after streaming completes
- [ ] Confidence badge shows correctly
- [ ] Input re-enabled after response complete
- [ ] Stream cancellation works (user navigates away)

### Sessions:
- [ ] Session list loads in sidebar
- [ ] New Chat button clears chat
- [ ] Clicking session loads message history
- [ ] Active session highlighted
- [ ] Session preview updates after new messages
- [ ] Session deletion works with confirmation

### Responsive:
- [ ] Desktop layout: sidebar + chat side by side
- [ ] Tablet layout: collapsible sidebar
- [ ] Mobile layout: full-width chat, hamburger menu for sidebar

### Error Handling:
- [ ] Network errors show toast
- [ ] 401 responses redirect to login
- [ ] API errors shown in chat
- [ ] Stream errors re-enable input

### Security:
- [ ] User content escaped (XSS prevention)
- [ ] Token not exposed in URLs
- [ ] Auth checked on page load

### Browser Support:
- [ ] Chrome (latest 2 versions)
- [ ] Firefox (latest 2 versions)
- [ ] Edge (latest 2 versions)
- [ ] Safari (latest 2 versions)