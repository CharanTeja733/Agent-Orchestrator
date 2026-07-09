"""Conditional edge functions for LangGraph StateGraphs.

Each function receives the current state and returns a string key that
determines which node to route to next.
"""

from __future__ import annotations

from app.graph.state import AgentState, OrchestratorState


# ---------------------------------------------------------------------------
# Orchestrator Graph Edges
# ---------------------------------------------------------------------------


def route_after_override_check(state: OrchestratorState) -> str:
    """If ``requested_agent`` was provided, skip classification entirely.

    Returns ``"load_agent_config"`` when an explicit agent override is set
    (bypasses classification), or ``"quick_classify"`` for automatic routing.
    """
    if state.get("agent_name"):
        return "load_agent_config"
    return "quick_classify"


# ---------------------------------------------------------------------------
# Agent Graph Edges
# ---------------------------------------------------------------------------


def route_after_classify(state: AgentState) -> str:
    """After classification, decide: direct response, rewrite, or retrieve.

    * ``respond_directly`` — greetings, bot questions, out-of-domain
    * ``rewrite_query`` — follow-ups that need context-dependent rewriting
    * ``retrieve_context`` — domain questions (HR, IT) needing vector search
    """
    if not state.get("requires_retrieval", True):
        return "respond_directly"
    if state.get("requires_rewriting", False):
        return "rewrite_query"
    return "retrieve_context"


def route_after_confidence(state: AgentState) -> str:
    """After confidence gate, decide: generate or fallback.

    * ``generate_response`` — high/medium confidence → use Gemini
    * ``generate_fallback`` — low/no_match → use pre-built fallback text
    """
    if state.get("gate_action") == "generate":
        return "generate_response"
    return "generate_fallback"
