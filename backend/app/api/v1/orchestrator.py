"""Agent Orchestrator endpoints — unified query routing (Feature 14).

Provides a single entry point that automatically routes queries to the
appropriate domain agent (HR or IT) via LangGraph StateGraphs.  Also serves
agent discovery and aggregated health checks.

Reference: ``.claude/specs/14-agent-orchestrator.md`` Section 4.
LangGraph migration: Replaces the manual ``OrchestratorService`` +
``BaseAgent.process_query()`` pipeline with two compiled StateGraphs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.graph import (
    DEFAULT_AGENT,
    build_agent_graph,
    build_orchestrator_graph,
    get_available_agents,
    run_agent_graph_test,
    run_agent_graph_with_sse,
)
from app.graph.nodes import _sse_event
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

# Compiled once at module level — state is passed per-invocation so this is
# safe across concurrent requests.
_orchestrator_graph = build_orchestrator_graph()
_agent_graph = build_agent_graph()


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
            # ── Step 1: Run orchestrator graph ──────────────────────────
            orch_state = await _orchestrator_graph.ainvoke({
                "query": request.query,
                "user_id": current_user.id,
                "full_name": current_user.full_name,
                "user_role": current_user.role,
                "session_id": request.session_id,
                "requested_agent": request.agent_name,
                "db": db,
                "gemini_api_key": settings.GEMINI_API_KEY,
            })

            if orch_state.get("error"):
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": orch_state["error"],
                        "detail": orch_state["error"],
                        "error_type": "routing_failed",
                    }),
                }
                return

            agent_config = orch_state["agent_config"]
            agent_name = orch_state["agent_name"]

            # Emit route event (before agent graph starts)
            yield _sse_event("route", {
                "agent_name": agent_name,
                "display_name": agent_config["display_name"],
            })

            # ── Step 2: Build agent state ──────────────────────────────
            agent_state = {
                # Inputs
                "query": request.query,
                "user_id": current_user.id,
                "full_name": current_user.full_name,
                "user_role": current_user.role,
                "user_email": current_user.email,
                "session_id": request.session_id,
                # Agent config (all attributes flattened into state)
                **agent_config,
                # Infrastructure
                "db": db,
                "gemini_api_key": settings.GEMINI_API_KEY,
                # Pipeline initial values
                "classification_result": (
                    orch_state.get("classification_result") or {}
                ),
                "history_messages": [],
                "history_dicts": [],
                "search_query": request.query,
                "retrieved_chunks": [],
                "confidence_level": "",
                "gate_action": "",
                "full_response": "",
                "sources": [],
                "message_id": None,
                "overall_start": time.time(),
                "classification_ms": None,
                "rewriting_ms": None,
                "retrieval_ms": None,
                "generation_ms": None,
                "storage_ms": None,
                "error": None,
            }

            # ── Tool registry (Feature 16) ───────────────────────────────
            if agent_config.get("agent_name") == "hr":
                from app.repositories.leave import LeaveRepository
                from app.services.search import SearchService
                from app.tools import (
                    GetLeaveBalanceTool,
                    SearchPolicyTool,
                    ToolRegistry,
                )

                search_service = SearchService(
                    db,
                    settings.GEMINI_API_KEY,
                    collection_name=agent_config.get(
                        "collection_name", "hr_documents"
                    ),
                )
                registry = ToolRegistry()
                registry.register(SearchPolicyTool(search_service))
                registry.register(GetLeaveBalanceTool(LeaveRepository(db)))
                agent_state["tool_registry"] = registry
                agent_state["tools_enabled"] = True
                agent_state["tool_results"] = []

            elif agent_config.get("agent_name") == "it":
                try:
                    from app.services.jira import JiraService
                    from app.tools import GetMyTicketsTool, ToolRegistry

                    jira_service = JiraService(
                        base_url=settings.JIRA_BASE_URL,
                        email=settings.JIRA_BOT_EMAIL,
                        api_token=settings.JIRA_API_TOKEN,
                        timeout=settings.JIRA_REQUEST_TIMEOUT_SECONDS,
                        max_results=settings.JIRA_MAX_RESULTS,
                    )
                    registry = ToolRegistry()
                    registry.register(GetMyTicketsTool(jira_service))
                    agent_state["tool_registry"] = registry
                    agent_state["tools_enabled"] = True
                    agent_state["tool_results"] = []
                except ValueError:
                    logger.info(
                        "Jira not configured — IT Agent will run without tickets"
                    )

            # ── Step 3: Run agent graph with SSE streaming ───────────────
            async for sse_event in run_agent_graph_with_sse(
                _agent_graph, agent_state
            ):
                yield sse_event

        except ValueError as exc:
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
    ``agent_name`` override), then delegates to the agent graph in test mode.
    """
    try:
        # ── Step 1: Run orchestrator graph ──────────────────────────
        orch_state = await _orchestrator_graph.ainvoke({
            "query": request.query,
            "user_id": current_user.id,
            "full_name": current_user.full_name,
            "user_role": current_user.role,
            "session_id": request.session_id,
            "requested_agent": request.agent_name,
            "db": db,
            "gemini_api_key": settings.GEMINI_API_KEY,
        })

        if orch_state.get("error"):
            raise ValueError(orch_state["error"])

        agent_config = orch_state["agent_config"]
        agent_name = orch_state["agent_name"]

        # ── Step 2: Build agent state ──────────────────────────────
        agent_state = {
            "query": request.query,
            "user_id": current_user.id,
            "full_name": current_user.full_name,
            "user_role": current_user.role,
            "user_email": current_user.email,
            "session_id": request.session_id,
            **agent_config,
            "db": db,
            "gemini_api_key": settings.GEMINI_API_KEY,
            "classification_result": orch_state.get("classification_result") or {},
            "history_messages": [],
            "history_dicts": [],
            "search_query": request.query,
            "retrieved_chunks": [],
            "confidence_level": "",
            "gate_action": "",
            "full_response": "",
            "sources": [],
            "message_id": None,
            "overall_start": time.time(),
            "classification_ms": None,
            "rewriting_ms": None,
            "retrieval_ms": None,
            "generation_ms": None,
            "storage_ms": None,
            "error": None,
        }

        # ── Tool registry (Feature 16) ──────────────────────────────
        if agent_config.get("agent_name") == "hr":
            from app.repositories.leave import LeaveRepository
            from app.services.search import SearchService
            from app.tools import (
                GetLeaveBalanceTool,
                SearchPolicyTool,
                ToolRegistry,
            )

            search_service = SearchService(
                db,
                settings.GEMINI_API_KEY,
                collection_name=agent_config.get("collection_name", "hr_documents"),
            )
            registry = ToolRegistry()
            registry.register(SearchPolicyTool(search_service))
            registry.register(GetLeaveBalanceTool(LeaveRepository(db)))
            agent_state["tool_registry"] = registry
            agent_state["tools_enabled"] = True
            agent_state["tool_results"] = []

        elif agent_config.get("agent_name") == "it":
            try:
                from app.services.jira import JiraService
                from app.tools import GetMyTicketsTool, ToolRegistry

                jira_service = JiraService(
                    base_url=settings.JIRA_BASE_URL,
                    email=settings.JIRA_BOT_EMAIL,
                    api_token=settings.JIRA_API_TOKEN,
                    timeout=settings.JIRA_REQUEST_TIMEOUT_SECONDS,
                    max_results=settings.JIRA_MAX_RESULTS,
                )
                registry = ToolRegistry()
                registry.register(GetMyTicketsTool(jira_service))
                agent_state["tool_registry"] = registry
                agent_state["tools_enabled"] = True
                agent_state["tool_results"] = []
            except ValueError:
                logger.info(
                    "Jira not configured — IT Agent will run without tickets"
                )

        # ── Step 3: Run agent graph in test mode ───────────────────
        result = await run_agent_graph_test(_agent_graph, agent_state)
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
async def list_agents():
    """List all registered agents with their capabilities.

    Returns metadata for every agent in the orchestrator's registry,
    including the human-readable display name and description.
    """
    agents_data = get_available_agents()

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
        default_agent=DEFAULT_AGENT,
    )


# ---------------------------------------------------------------------------
# GET /orchestrator/query/health — aggregated health
# ---------------------------------------------------------------------------


@router.get("/query/health", response_model=OrchestratorHealthResponse)
async def orchestrator_health(
    db: AsyncSession = Depends(get_db),
):
    """Return the aggregated health status of all registered agents.

    Uses the existing ``OrchestratorService`` for health checks since it
    exercises the full agent stack (DB, Gemini, vector search).
    """
    orch = OrchestratorService(
        db=db, gemini_api_key=settings.GEMINI_API_KEY
    )
    return await orch.health_check()
