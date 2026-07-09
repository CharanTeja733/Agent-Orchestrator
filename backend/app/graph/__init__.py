"""LangGraph-based orchestrator and RAG pipeline graphs.

Replaces the manual procedural pipeline in
:class:`~app.services.orchestrator.OrchestratorService` and
:class:`~app.agents.base.BaseAgent` with LangGraph StateGraphs.

Two independent graphs:
- **Orchestrator graph** — classifies + routes queries to the right domain agent
- **Agent graph** — per-agent RAG pipeline (classify, rewrite, retrieve,
  confidence gate, generate/fallback, store)

The API route runs them sequentially, not as LangGraph subgraphs (avoids
passing non-serializable objects across graph boundaries).
"""

from app.graph.agent_graph import build_agent_graph
from app.graph.agent_registry import (
    CLASSIFICATION_AGENT_MAP,
    DEFAULT_AGENT,
    get_agent_config,
    get_available_agents,
)
from app.graph.orchestrator_graph import build_orchestrator_graph
from app.graph.streaming import run_agent_graph_with_sse
from app.graph.test_handler import run_agent_graph_test

__all__ = [
    "build_agent_graph",
    "build_orchestrator_graph",
    "CLASSIFICATION_AGENT_MAP",
    "DEFAULT_AGENT",
    "get_agent_config",
    "get_available_agents",
    "run_agent_graph_test",
    "run_agent_graph_with_sse",
]
