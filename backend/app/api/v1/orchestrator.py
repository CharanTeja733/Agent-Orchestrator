"""Agent Orchestrator endpoints — unified query routing (Feature 14).

Provides a single entry point that automatically routes queries to the
appropriate domain agent (HR or IT).  Also serves agent discovery and
aggregated health checks.

Reference: ``.claude/specs/14-agent-orchestrator.md`` Section 4.
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
from app.schemas.orchestrator import (
    AgentInfo,
    OrchestratorAgentsResponse,
    OrchestratorHealthResponse,
    OrchestratorQueryRequest,
    OrchestratorTestResponse,
)
from app.services.orchestrator import OrchestratorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["Orchestrator"])


# ---------------------------------------------------------------------------
# POST /orchestrator/query — streaming SSE
# ---------------------------------------------------------------------------


@router.post("/query")
async def orchestrator_query_stream(
    request: OrchestratorQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Answer a question via the best domain agent using SSE streaming.

    Automatically routes to the HR or IT agent based on query classification.
    Emits a ``route`` event before the agent's token stream so the frontend
    can display which agent is responding.

    Yields ``route`` → ``token*`` → ``sources`` → ``done`` events.
    Emits an ``error`` event on failure.
    """

    async def event_generator():
        try:
            orch = OrchestratorService(
                db=db, gemini_api_key=settings.GEMINI_API_KEY
            )
            agent, agent_name = await orch.route_query(
                query=request.query,
                user=current_user,
                session_id=request.session_id,
                requested_agent=request.agent_name,
            )

            # Emit route event so the frontend knows which agent is responding
            from app.agents.base import BaseAgent

            yield BaseAgent._sse_event("route", {
                "agent_name": agent_name,
                "display_name": type(agent).display_name,
            })

            # Delegate to the chosen agent's streaming pipeline
            async for sse_event in agent.process_query(
                query=request.query,
                user=current_user,
                session_id=request.session_id,
            ):
                yield sse_event

        except ValueError as exc:
            # Invalid agent_name override
            logger.warning("Orchestrator routing error: %s", exc)
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "error": str(exc),
                        "detail": str(exc),
                        "error_type": "routing_failed",
                    }
                ),
            }
        except Exception:
            logger.exception("Unhandled error in orchestrator streaming endpoint")
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "error": "Orchestrator processing failed",
                        "detail": "An unexpected error occurred during routing",
                        "error_type": "internal_error",
                    }
                ),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# POST /orchestrator/query/test — non-streaming debug
# ---------------------------------------------------------------------------


@router.post("/query/test", response_model=OrchestratorTestResponse)
async def orchestrator_query_test(
    request: OrchestratorQueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming debug endpoint — returns the complete pipeline result
    with routing metadata.

    Routes automatically based on query classification (or explicit
    ``agent_name`` override), then delegates to the chosen agent's
    ``process_query_test()``.
    """
    try:
        orch = OrchestratorService(
            db=db, gemini_api_key=settings.GEMINI_API_KEY
        )
        agent, agent_name = await orch.route_query(
            query=request.query,
            user=current_user,
            session_id=request.session_id,
            requested_agent=request.agent_name,
        )

        result = await agent.process_query_test(
            query=request.query,
            user=current_user,
            session_id=request.session_id,
        )
        result["agent_name"] = agent_name
        return result

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in orchestrator test endpoint")
        raise HTTPException(
            status_code=500,
            detail=f"Orchestrator query processing failed: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# GET /orchestrator/agents — agent discovery
# ---------------------------------------------------------------------------


@router.get("/agents", response_model=OrchestratorAgentsResponse)
async def list_agents(
    db: AsyncSession = Depends(get_db),
):
    """List all registered agents with their capabilities.

    Returns metadata for every agent in the orchestrator's registry,
    including the human-readable display name and description.
    """
    orch = OrchestratorService(
        db=db, gemini_api_key=settings.GEMINI_API_KEY
    )
    agents_data = orch.get_available_agents()

    return OrchestratorAgentsResponse(
        agents=[
            AgentInfo(
                name=a["name"],
                display_name=a["display_name"],
                description=a["description"],
                collection_name=a["collection_name"],
            )
            for a in agents_data
        ],
        default_agent=OrchestratorService.DEFAULT_AGENT,
    )


# ---------------------------------------------------------------------------
# GET /orchestrator/query/health — aggregated health
# ---------------------------------------------------------------------------


@router.get("/query/health", response_model=OrchestratorHealthResponse)
async def orchestrator_health(
    db: AsyncSession = Depends(get_db),
):
    """Return the aggregated health status of all registered agents."""
    orch = OrchestratorService(
        db=db, gemini_api_key=settings.GEMINI_API_KEY
    )
    return await orch.health_check()
