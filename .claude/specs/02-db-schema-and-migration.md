# Feature 2: Database Schema & Migrations

## Overview

Create the complete PostgreSQL database schema including **pgvector** extension setup.

This feature establishes the data layer for the **HR Q&A Agent** — users, sessions, messages, feedback, and document embeddings with vector search capability.

All future features (authentication, ingestion, RAG pipeline) depend on these tables being correctly implemented.

---

## Dependencies

**Feature 1: Project Setup & Docker Environment** — PostgreSQL container must be running and accessible.

---

## API Routes

No new API routes are required for this feature.

Database initialization runs automatically on backend startup.

---

# Database Schema

## A. pgvector Extension

Enable the `vector` extension before creating any tables.

---

## B. `users`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique user identifier |
| `email` | `VARCHAR(255)` | `UNIQUE`, `NOT NULL` | Company email address |
| `hashed_password` | `VARCHAR(255)` | `NOT NULL` | bcrypt hashed password |
| `full_name` | `VARCHAR(255)` | `NOT NULL` | User's full name |
| `role` | `VARCHAR(50)` | `NOT NULL`, `DEFAULT 'employee'` | One of: `employee`, `manager`, `hr_admin` |
| `department` | `VARCHAR(100)` | `NOT NULL` | Department name (engineering, sales, hr, etc.) |
| `is_active` | `BOOLEAN` | `NOT NULL`, `DEFAULT TRUE` | Soft delete / deactivation flag |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW()` | Account creation time |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW()` | Last update time |

**Indexes:**

| Index | Type | Columns |
|-------|------|---------|
| `idx_users_email` | `UNIQUE` | `email` |
| `idx_users_role` | — | `role` |
| `idx_users_department` | — | `department` |

---

## C. `sessions`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique session identifier |
| `user_id` | `UUID` | `FOREIGN KEY → users.id`, `NOT NULL` | User who owns this session |
| `is_active` | `BOOLEAN` | `NOT NULL`, `DEFAULT TRUE` | Whether session is still valid |
| `device_info` | `JSONB` | `NULLABLE` | Browser/device metadata |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW()` | Session creation time |
| `last_active` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW()` | Last activity timestamp |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW() + INTERVAL '24 hours'` | Session expiry time |

**Indexes:**

| Index | Columns |
|-------|---------|
| `idx_sessions_user_id` | `user_id` |
| `idx_sessions_last_active` | `last_active` |
| `idx_sessions_expires_at` | `expires_at` |

---

## D. `messages`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique message identifier |
| `session_id` | `UUID` | `FOREIGN KEY → sessions.id`, `NOT NULL` | Session this message belongs to |
| `user_id` | `UUID` | `FOREIGN KEY → users.id`, `NOT NULL` | User who sent/received this message |
| `role` | `VARCHAR(20)` | `NOT NULL`, `CHECK (role IN ('user', 'assistant'))` | Who sent the message |
| `content` | `TEXT` | `NOT NULL` | Message text content |
| `sources` | `JSONB` | `NULLABLE` | Array of source documents used (for assistant messages) |
| `confidence` | `VARCHAR(20)` | `NULLABLE`, `CHECK (confidence IN ('high', 'medium', 'low', 'none'))` | Retrieval confidence level |
| `tokens_used` | `INTEGER` | `NULLABLE` | Total tokens consumed for this message |
| `classification` | `VARCHAR(30)` | `NULLABLE` | Query classification (see Classification Types below) |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW()` | Message creation time |

**Indexes:**

| Index | Columns |
|-------|---------|
| `idx_messages_session_id` | `session_id` |
| `idx_messages_user_id` | `user_id` |
| `idx_messages_created_at` | `created_at` |

---

## E. `feedback`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique feedback identifier |
| `message_id` | `UUID` | `FOREIGN KEY → messages.id`, `NOT NULL` | Message receiving feedback |
| `user_id` | `UUID` | `FOREIGN KEY → users.id`, `NOT NULL` | User providing feedback |
| `rating` | `VARCHAR(10)` | `NOT NULL`, `CHECK (rating IN ('positive', 'negative'))` | Thumbs up or down |
| `reason` | `VARCHAR(50)` | `NULLABLE` | Reason for negative rating |
| `comment` | `TEXT` | `NULLABLE` | Additional user comment |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW()` | Feedback submission time |

**Indexes:**

| Index | Columns |
|-------|---------|
| `idx_feedback_message_id` | `message_id` |
| `idx_feedback_user_id` | `user_id` |
| `idx_feedback_rating` | `rating` |

---

## F. `hr_documents`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | `PRIMARY KEY`, `DEFAULT gen_random_uuid()` | Unique chunk identifier |
| `content` | `TEXT` | `NOT NULL` | Text chunk content |
| `embedding` | `VECTOR(768)` | `NOT NULL` | Gemini `text-embedding-004` vector (768 dimensions) |
| `source` | `VARCHAR(500)` | `NOT NULL` | Original document filename |
| `page` | `INTEGER` | `NULLABLE` | Page number in source document |
| `section` | `VARCHAR(500)` | `NULLABLE` | Section title or heading |
| `chunk_index` | `INTEGER` | `NOT NULL` | Position of chunk in document (ordering) |
| `access_level` | `VARCHAR(50)` | `NOT NULL`, `DEFAULT 'all'` | One of: `all`, `manager`, `hr_admin` |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `DEFAULT NOW()` | When this chunk was indexed |

**Indexes:**

| Index | Columns |
|-------|---------|
| `idx_hr_documents_source` | `source` |
| `idx_hr_documents_access_level` | `access_level` |

**Vector Index (for similarity search):**

```sql
CREATE INDEX IF NOT EXISTS idx_hr_documents_embedding
ON hr_documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

---

# Files to Create

## backend/app/database.py

This is the core database module. It must provide:

### Connection Management

| Component | Details |
|-----------|---------|
| `engine` | SQLAlchemy async engine created from `DATABASE_URL` config |
| Library | `create_async_engine` from `sqlalchemy.ext.asyncio` |
| Pool size | `20` |
| Max overflow | `10` |
| Pool pre-ping | `True` (validates connections before use) |
| `AsyncSessionLocal` | Async session factory using `async_sessionmaker` |
| `expire_on_commit` | `False` |

### Functions

**`get_db()`** — Async generator function (FastAPI dependency)

- Yields an async session
- Ensures session is closed after use

**`get_db_connection()`** — Returns raw `asyncpg` connection

- For operations that need direct connection access (vector operations)
- Not a generator — returns connection directly

### Initialization

**`init_db()`** — Async function

- Creates the vector extension if not exists:
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector
  ```
- Calls `create_tables()`
- Logs success/failure
- Safe to call multiple times (idempotent)

**`create_tables()`** — Async function

- Uses raw SQL via `asyncpg` connection (not SQLAlchemy ORM)
- Creates all 6 tables with `CREATE TABLE IF NOT EXISTS`
- Creates all indexes from the Database Schema section
- Creates the `ivfflat` vector index on `hr_documents`
- Must handle the case where `pgvector` extension is not yet loaded

### Connection String Construction

Build `DATABASE_URL` for asyncpg from individual env vars if full URL is not provided.

Format:

```
postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}
```

---

## backend/app/models.py

SQLAlchemy ORM models (declarative base) for type hints and optional ORM use:

| Model | Table |
|-------|-------|
| `Base` | SQLAlchemy declarative base |
| `User` | `users` |
| `Session` | `sessions` |
| `Message` | `messages` |
| `Feedback` | `feedback` |
| `HRDocument` | `hr_documents` |

Each model should:

- Use `__tablename__` matching the table name
- Include all columns with correct types from the schema
- Define relationships (`User` → `Sessions` → `Messages`)

---

## backend/app/schemas.py

Pydantic models for request/response validation:

| Schema | Fields |
|--------|--------|
| `UserCreate` | `email`, `password`, `full_name`, `role`, `department` |
| `UserResponse` | `id`, `email`, `full_name`, `role`, `department`, `is_active`, `created_at` |
| `UserLogin` | `email`, `password` |
| `SessionResponse` | `id`, `user_id`, `is_active`, `created_at`, `last_active`, `expires_at` |
| `MessageCreate` | `session_id`, `role`, `content` |
| `MessageResponse` | `id`, `session_id`, `user_id`, `role`, `content`, `sources`, `confidence`, `classification`, `created_at` |
| `FeedbackCreate` | `message_id`, `rating`, `reason` (optional), `comment` (optional) |
| `FeedbackResponse` | `id`, `message_id`, `user_id`, `rating`, `reason`, `comment`, `created_at` |
| `DocumentChunk` | `content`, `source`, `page`, `section`, `chunk_index`, `access_level` |
| `HealthResponse` | `status`, `database`, `gemini_api` |

---

## backend/app/seed.py

Database seeding module.

### `seed_users()` — Async function

| Step | Behavior |
|------|----------|
| 1. Check | If `users` table has any records → log and return early (idempotent) |
| 2. Seed | If no records → insert demo users |

**Demo Users:**

| Email | Password (plaintext → hashed) | Full Name | Role | Department |
|-------|-------------------------------|-----------|------|------------|
| `admin@company.com` | `admin123` | Admin User | `hr_admin` | hr |
| `john@company.com` | `john123` | John Doe | `employee` | engineering |
| `sarah@company.com` | `sarah123` | Sarah Smith | `manager` | sales |
| `priya@company.com` | `priya123` | Priya Sharma | `employee` | hr |

Requirements:

- Hash all passwords using **passlib bcrypt** before inserting
- Log each created user

---

## database/init.sql

SQL script for manual database initialization (reference only).

Requirements:

- Enables `vector` extension
- Creates all tables with `IF NOT EXISTS`
- Insert statements for seed data (commented out, for reference)

---

# Files Modified

| File | Changes |
|------|---------|
| `backend/app/main.py` | Add startup initialization and update health check |
| `backend/app/config.py` | Add database pool settings |

---

# Changes to Existing Files

## backend/app/main.py

### Add to startup sequence:

```python
from app.database import init_db
from app.seed import seed_users

@app.on_event("startup")
async def startup():
    await init_db()
    await seed_users()
```

### Update health check endpoint (`/health`):

| Condition | `database` value |
|-----------|-----------------|
| Query `SELECT 1` succeeds | `"connected"` |
| Query fails | `"disconnected"` |

---

## backend/app/config.py

Add configuration for database connection pooling:

| Setting | Type | Default |
|---------|------|---------|
| `DB_POOL_SIZE` | `int` | `20` |
| `DB_MAX_OVERFLOW` | `int` | `10` |
| `DB_POOL_PRE_PING` | `bool` | `True` |

---

# Dependencies

All already in `requirements.txt` from Feature 1:

| Package | Purpose |
|---------|---------|
| `sqlalchemy[asyncio]` | ORM + async support |
| `asyncpg` | PostgreSQL async driver |
| `pgvector` | Vector operations in Python |
| `passlib[bcrypt]` | Password hashing |
| `pydantic` | Data validation |

No new pip packages required.

---

# Enumerated Value Lists

## Access Levels (for `hr_documents.access_level`)

| Value | Visibility |
|-------|------------|
| `all` | Visible to everyone |
| `manager` | Visible to managers and `hr_admin` only |
| `hr_admin` | Visible to `hr_admin` only |

## User Roles (for `users.role`)

| Value |
|-------|
| `employee` |
| `manager` |
| `hr_admin` |

## Confidence Levels (for `messages.confidence`)

| Value |
|-------|
| `high` |
| `medium` |
| `low` |
| `none` |

## Classification Types (for `messages.classification`)

| Value |
|-------|
| `greeting_only` |
| `bot_question` |
| `out_of_domain` |
| `follow_up` |
| `hr_question` |

---

# Implementation Rules

- No raw string formatting in SQL queries — always use parameterized queries (`$1`, `$2`)
- For `CREATE TABLE` statements, raw SQL via `asyncpg` connection is acceptable (these are fixed, no user input)
- All user-facing queries must use parameterized form
- `init_db()` must be **idempotent** — safe to call on every startup
- `seed_users()` must check for existing data before inserting
- `CREATE TABLE IF NOT EXISTS` for all tables
- `CREATE INDEX IF NOT EXISTS` for all indexes
- Vector index (`ivfflat`) may need special handling — wrap in `try/except` for pgvector availability
- Use `UUID` type with `gen_random_uuid()` default for all primary keys
- Use `TIMESTAMP WITH TIME ZONE` for all timestamp columns
- Password hashing must use `passlib` with bcrypt scheme
- Schema changes should be **additive only** (no `DROP` statements)

---

# Expected Behavior

## First Run (`docker compose up`)

1. PostgreSQL starts and passes health check
2. Backend starts and runs `init_db()`
3. `vector` extension is enabled
4. All 6 tables are created with correct columns, types, and constraints
5. All indexes are created (including `ivfflat` vector index)
6. `seed_users()` runs and inserts 4 demo users with hashed passwords
7. Backend logs: `"Database initialized successfully"` and `"4 demo users seeded"`

## Subsequent Runs (`docker compose up`)

1. `init_db()` runs safely — no errors from existing tables
2. `seed_users()` detects existing users — logs `"Users already exist, skipping seed"`
3. No duplicate data created

## Health Endpoint (`/health`)

```json
{
  "status": "healthy",
  "database": "connected",
  "gemini_api": "configured"
}
```

## Adminer Verification

Accessible at `http://localhost:8080`:

- All 6 tables visible
- 4 users visible in `users` table
- `pgvector` extension visible in extensions list
- `hr_documents` table shows `embedding` column with type `vector(768)`

---

# Error Handling

| Scenario | Expected Behavior |
|----------|-------------------|
| Database connection failure on startup | Log error, health check shows `"disconnected"` |
| pgvector extension not available | Log warning, skip vector index creation (don't crash) |
| Duplicate email in seed data | Constraint violation caught, logged |
| `init_db()` called multiple times | No errors (`IF NOT EXISTS`) |
| Foreign key constraint violations | Proper error messages from PostgreSQL |

---

# Testing Verification

After implementation, verify using these SQL queries in Adminer:

```sql
-- Check extensions
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Check tables
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public';

-- Check users (should show 4 users with hashed passwords)
SELECT id, email, full_name, role, department FROM users;

-- Check vector index
SELECT indexname FROM pg_indexes WHERE tablename = 'hr_documents';
```

---

# Definition of Done

The feature is complete when all of the following are satisfied:

- [ ] `docker compose up` completes without database-related errors
- [ ] `pgvector` extension is enabled in the database
- [ ] All 6 tables exist with correct schema (verify in Adminer)
- [ ] All indexes exist including `ivfflat` vector index
- [ ] 4 demo users seeded with bcrypt-hashed passwords (verify in Adminer)
- [ ] Password hashes are not plaintext (verify hashes start with `$2b$`)
- [ ] `seed_users()` does not duplicate on restart
- [ ] `/health` endpoint shows database as `"connected"`
- [ ] Foreign key constraints work (test by inserting invalid references)
- [ ] `UNIQUE` constraint on `email` works (test by attempting duplicate email insert)
- [ ] Vector column accepts 768-dimensional vectors
- [ ] `init.sql` reference file is complete and matches schema
