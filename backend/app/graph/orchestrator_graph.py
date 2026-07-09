"""Orchestrator StateGraph — classifies and routes queries to domain agents.

Replaces :class:`~app.services.orchestrator.OrchestratorService` with a
LangGraph StateGraph for the routing decision.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.conditional_edges import route_after_override_check
from app.graph.nodes import (
    check_override,
    load_agent_config,
    map_to_agent,
    quick_classify,
)
from app.graph.state import OrchestratorState


def build_orchestrator_graph() -> CompiledStateGraph:
    """Build the orchestrator routing graph.

    Flow::

        START → check_override
          ├─ [agent_name set] → load_agent_config → END
          └─ [no override] → quick_classify → map_to_agent
               → load_agent_config → END

    Returns:
        A compiled :class:`StateGraph` ready for ``ainvoke()``.
    """
    builder = StateGraph(OrchestratorState)  # type: ignore[arg-type]

    builder.add_node("check_override", check_override)
    builder.add_node("quick_classify", quick_classify)
    builder.add_node("map_to_agent", map_to_agent)
    builder.add_node("load_agent_config", load_agent_config)

    builder.add_edge(START, "check_override")

    builder.add_conditional_edges(
        "check_override",
        route_after_override_check,
        {
            "quick_classify": "quick_classify",
            "load_agent_config": "load_agent_config",
        },
    )

    builder.add_edge("quick_classify", "map_to_agent")
    builder.add_edge("map_to_agent", "load_agent_config")
    builder.add_edge("load_agent_config", END)

    return builder.compile()
