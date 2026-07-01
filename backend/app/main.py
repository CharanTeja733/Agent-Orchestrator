from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError

from app.auth.router import router as auth_router
from app.config import settings
from app.database import ASYNCPG_URL, init_db
from app.seed import seed_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("HR Q&A Agent API — starting up...")
    await init_db()
    await seed_users()
    yield
    print("Shutting down...")


app = FastAPI(
    title="HR Q&A Agent API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Auth router
# ---------------------------------------------------------------------------

app.include_router(auth_router)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(JWTError)
async def jwt_error_handler(request: Request, exc: JWTError) -> JSONResponse:
    """Safety net — catch any JWTError that escapes the auth module."""
    return JSONResponse(
        status_code=401,
        content={"detail": "Could not validate credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.get("/health")
async def health():
    # Test database connectivity
    db_status = "disconnected"
    try:
        conn = await asyncpg.connect(ASYNCPG_URL)
        await conn.close()
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    # Check Gemini API key
    gemini_status = (
        "configured"
        if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here"
        else "missing"
    )

    # Determine overall status
    if db_status == "connected" and gemini_status == "configured":
        overall_status = "healthy"
    elif db_status == "disconnected":
        overall_status = "unhealthy"
    else:
        overall_status = "degraded"

    return {
        "status": overall_status,
        "database": db_status,
        "gemini_api": gemini_status,
    }
