# Feature 1: Project Setup & Docker Environment

## Overview

Set up the complete Docker-based development environment for the **HR Q&A Agent**.

This feature establishes the project's infrastructure by configuring three Docker services:

- **FastAPI Backend**
- **PostgreSQL with pgvector**
- **Frontend**

All future features depend on this environment being configured correctly.

---

## Dependencies

**None** — This is the first feature.

---

## API Routes

| Method | Route | Description |
|---------|-------|-------------|
| GET | `/health` | Returns application health status |

No additional routes are required for this feature.

---

# Project Structure

```text
hr-agent/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       └── config.py
├── frontend/
│   ├── Dockerfile
│   └── index.html
└── database/
    └── init.sql
```

---

# Services

## 1. PostgreSQL + pgvector (`db`)

| Setting | Value |
|----------|-------|
| Image | `pgvector/pgvector:pg16` |
| Container Name | `hr-agent-db` |
| Port | `5432:5432` |
| Database | `hr_agent` |
| Username | `POSTGRES_USER` |
| Password | `POSTGRES_PASSWORD` |
| Volume | `pgdata:/var/lib/postgresql/data` |
| Health Check | `pg_isready -U ${POSTGRES_USER} -d hr_agent` |

---

## 2. FastAPI Backend (`backend`)

| Setting | Value |
|----------|-------|
| Build Context | `./backend` |
| Container Name | `hr-agent-backend` |
| Port | `8000:8000` |
| Environment Variables | `DATABASE_URL`, `GEMINI_API_KEY`, `SECRET_KEY` |
| Depends On | `db` (`condition: service_healthy`) |
| Command | `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` |

---

## 3. Frontend (`frontend`)

| Setting | Value |
|----------|-------|
| Build Context | `./frontend` |
| Container Name | `hr-agent-frontend` |
| Port | `8501:8501` |
| Depends On | `backend` |

---

# Files to Create

## docker-compose.yml

Configure all three services.

Requirements:

- Use a named Docker volume:
  - `pgdata`
- Read secrets from `.env`
- Backend waits until database health check passes
- All services communicate using Docker's default network

---

## .env.example

```env
POSTGRES_USER=hr_agent_user
POSTGRES_PASSWORD=change_this_password
POSTGRES_DB=hr_agent

GEMINI_API_KEY=your_gemini_api_key_here
SECRET_KEY=your_random_secret_key_here

DATABASE_URL=postgresql+asyncpg://hr_agent_user:change_this_password@db:5432/hr_agent
```

---

## .gitignore

```gitignore
.env

__pycache__/
*.pyc

.venv/
venv/

pgdata/
*.db

.DS_Store
```

---

## backend/Dockerfile

Requirements:

- Base image: `python:3.12-slim`
- Working directory: `/app`
- Copy `requirements.txt` first (Docker layer caching)
- Install dependencies
- Copy backend source code
- Expose port `8000`
- Start FastAPI using:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## backend/requirements.txt

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
asyncpg==0.29.0
sqlalchemy[asyncio]==2.0.35
pgvector==0.3.6
google-generativeai==0.8.3
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.12
pydantic==2.9.2
pydantic-settings==2.5.2
PyPDF2==3.0.1
python-docx==1.1.2
```

---

## backend/app/__init__.py

Empty file.

Purpose:

- Marks `app` as a Python package.

---

## backend/app/config.py

Use **pydantic-settings** (`BaseSettings`).

Load configuration from `.env`.

Required settings:

```python
DATABASE_URL: str
GEMINI_API_KEY: str
SECRET_KEY: str
POSTGRES_USER: str
POSTGRES_PASSWORD: str
POSTGRES_DB: str
```

---

## backend/app/main.py

Create a FastAPI application.

Requirements:

- Application title:
  - **HR Q&A Agent API**
- Enable CORS
  - Allow all origins (development only)
- Print a startup confirmation message
- Implement:

```
GET /health
```

Health response:

```json
{
  "status": "healthy",
  "database": "connected",
  "gemini_api": "configured"
}
```

The endpoint must:

- Test database connectivity
- Check whether `GEMINI_API_KEY` is configured
- Return the appropriate status without crashing

---

## frontend/Dockerfile

Requirements:

- Base image:
  - `python:3.12-slim`
- Working directory:
  - `/app`
- Copy `index.html`
- Expose port:
  - `8501`
- Serve the page using a lightweight HTTP server
  (e.g. Python's `http.server`)

---

## frontend/index.html

Create a minimal webpage.

Requirements:

- Page title:
  - **HR Q&A Agent**
- Heading:
  - **HR Q&A Agent**
- Status indicator
- Fetch:

```
http://backend:8000/health
```

when the page loads.

Display:

- Backend health
- Database status
- Gemini API status

Use a clean light or dark theme.

---

## database/init.sql

Placeholder file.

```sql
-- Database initialization script
```

This file will be expanded in Feature 2.

---

# Files Modified

None.

All files are newly created.

---

# Required Software

- Docker Desktop

or

- Docker Engine
- Docker Compose

No local Python installation is required.

Everything runs inside Docker containers.

---

# Environment Variables

| Variable | Used By | Purpose |
|----------|----------|----------|
| POSTGRES_USER | DB, Backend | Database username |
| POSTGRES_PASSWORD | DB, Backend | Database password |
| POSTGRES_DB | DB, Backend | Database name |
| DATABASE_URL | Backend | Async PostgreSQL connection |
| GEMINI_API_KEY | Backend | Google Gemini authentication |
| SECRET_KEY | Backend | JWT signing key |

---

# Implementation Rules

- Never hardcode secrets.
- Always use environment variables.
- Never commit the `.env` file.
- Include `.env.example`.
- Configure a database health check.
- Backend must wait for database readiness.
- Use explicit image versions (avoid `latest`).
- Persist PostgreSQL data using a named volume.
- Include all backend dependencies required for future features.
- Frontend must demonstrate connectivity to the backend by displaying health status.

---

# Expected Behavior

## Startup Sequence

Running:

```bash
docker compose up
```

should perform the following sequence:

1. Start PostgreSQL.
2. Wait until PostgreSQL passes its health check.
3. Start the FastAPI backend.
4. Start the frontend.
5. Print a backend startup confirmation.

---

## Health Endpoint Responses

### Healthy

```json
{
  "status": "healthy",
  "database": "connected",
  "gemini_api": "configured"
}
```

---

### Database Unavailable

```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "gemini_api": "configured"
}
```

---

### Gemini API Missing

```json
{
  "status": "degraded",
  "database": "connected",
  "gemini_api": "missing"
}
```

---

## Frontend

Accessible at:

```
http://localhost:8501
```

The page should:

- Display **HR Q&A Agent**
- Fetch `/health`
- Show backend health
- Update status automatically on page load

---

# Error Handling

- Docker Compose should fail clearly if `.env` is missing.
- Backend should gracefully handle database connection failures.
- `/health` must catch database errors and return the correct status.
- Missing `GEMINI_API_KEY` must **not** crash the application.
- Retry logic is **not** required for this feature.

---

# Definition of Done

The feature is complete when all of the following are satisfied:

- [ ] `docker compose up` starts all services successfully.
- [ ] PostgreSQL passes its health check.
- [ ] Backend `/health` returns HTTP **200**.
- [ ] Health response contains the correct status.
- [ ] Frontend is available at `http://localhost:8501`.
- [ ] Frontend displays backend health status.
- [ ] `.env.example` contains all required variables.
- [ ] `.gitignore` excludes `.env` and `pgdata`.
- [ ] No secrets are hardcoded.
- [ ] `docker compose down` stops all services.
- [ ] `docker compose down -v` removes the database volume.
- [ ] Services restart successfully after shutdown.