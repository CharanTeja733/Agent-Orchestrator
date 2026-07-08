"""Request and response schemas for the Agent Orchestrator (Feature 14).

Provides a unified entry point that auto-routes queries to the appropriate
domain agent (HR, IT, and future agents).

Reference: ``.claude/specs/14-agent-orchestrator.md``
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.query import QueryRequest, QueryTestResponse


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class OrchestratorQueryRequest(QueryRequest):
    """Unified query request with optional agent override.

    Extends :class:`QueryRequest` with an ``agent_name`` field that bypasses
    automatic routing when provided.
    """

    agent_name: Optional[str] = Field(
        default=None,
        description="Force routing to a specific agent ('hr', 'it'). "
        "When omitted, the orchestrator routes automatically based on "
        "query classification.",
        examples=["hr", "it"],
    )


# ---------------------------------------------------------------------------
# Agent metadata
# ---------------------------------------------------------------------------


class AgentInfo(BaseModel):
    """Metadata about a single registered agent."""

    name: str = Field(..., description="Machine identifier, e.g. 'hr', 'it'")
    display_name: str = Field(..., description="Human-readable name, e.g. 'HR Agent'")
    description: str = Field(..., description="One-line summary of agent capabilities")
    collection_name: str = Field(
        ..., description="pgvector collection this agent searches"
    )


class OrchestratorAgentsResponse(BaseModel):
    """Response listing all registered agents."""

    agents: list[AgentInfo] = Field(..., description="All registered agents")
    default_agent: str = Field(
        ..., description="Agent used for non-domain queries and fallbacks"
    )


# ---------------------------------------------------------------------------
# Test / debug endpoint response
# ---------------------------------------------------------------------------


class OrchestratorTestResponse(QueryTestResponse):
    """Non-streaming debug response with the routed agent name.

    Extends :class:`QueryTestResponse` from the base query schema so all
    existing fields are present, plus the agent that handled the query.
    """

    agent_name: str = Field(
        ..., description="Name of the agent that handled this query"
    )


# ---------------------------------------------------------------------------
# Health-check response
# ---------------------------------------------------------------------------


class OrchestratorHealthResponse(BaseModel):
    """Aggregated health status of all registered agents."""

    status: str = Field(
        ..., description="Overall health: 'healthy' if all agents healthy, else 'degraded'"
    )
    agents: dict[str, dict] = Field(
        ..., description="Per-agent health check results, keyed by agent_name"
    )
    default_agent: str = Field(
        ..., description="Default agent name for non-domain queries"
    )
