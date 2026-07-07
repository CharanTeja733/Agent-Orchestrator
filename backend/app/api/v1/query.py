"""RAG Query endpoints — streaming, test, and health (Feature 8).

Reference: ``.claude/specs/08-rag-pipeline.md`` Section 4.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.models import User
from app.schemas.query import (
    PipelineSteps,
    QueryHealthResponse,
    QueryRequest,
    QueryTestResponse,
    RetrievedChunkDetail,
    SourceDetail,
)
from app.agents.hr_agent import HRAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["Query"])


# ---------------------------------------------------------------------------
# POST /query — streaming SSE
# ---------------------------------------------------------------------------


@router.post("/")
async def query_stream(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Answer an HR question via a Server-Sent Events stream.

    Yields ``token`` events for each generated token, a ``sources`` event
    with cited documents, and a ``done`` event with metadata.  Emits an
    ``error`` event on failure.
    """

    async def event_generator():
        try:
            agent = HRAgent.create(db=db, gemini_api_key=settings.GEMINI_API_KEY)
            async for sse_event in agent.process_query(
                query=request.query,
                user=current_user,
                session_id=request.session_id,
            ):
                yield sse_event
        except Exception:
            logger.exception("Unhandled error in streaming query endpoint")
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "error": "Internal server error",
                        "detail": "An unexpected error occurred",
                        "error_type": "internal_error",
                    }
                ),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# POST /query/test — non-streaming debug
# ---------------------------------------------------------------------------


@router.post("/test", response_model=QueryTestResponse)
async def query_test(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming debug endpoint — returns the complete pipeline result.

    Useful for testing and troubleshooting.  Mirrors the streaming pipeline
    but uses non-streaming generation and captures per-step timing.
    """
    try:
        agent = HRAgent.create(db=db, gemini_api_key=settings.GEMINI_API_KEY)
        result = await agent.process_query_test(
            query=request.query,
            user=current_user,
            session_id=request.session_id,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in test query endpoint")
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# GET /query/health — component health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=QueryHealthResponse)
async def query_health(
    db: AsyncSession = Depends(get_db),
):
    """Return the operational status of every RAG pipeline component."""
    agent = HRAgent.create(db=db, gemini_api_key=settings.GEMINI_API_KEY)
    return await agent.health_check()
