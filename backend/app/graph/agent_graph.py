"""Agent RAG pipeline StateGraph — per-agent question answering.

Replaces :meth:`~app.agents.base.BaseAgent.process_query` with a LangGraph
StateGraph for the full RAG pipeline (classify → rewrite → retrieve →
confidence gate → generate/fallback → store).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.conditional_edges import route_after_classify, route_after_confidence
from app.graph.nodes import (
    apply_confidence_gate,
    classify_message,
    generate_fallback,
    generate_response,
    load_context,
    respond_directly,
    retrieve_context,
    rewrite_query,
    store_and_finish,
)
from app.graph.state import AgentState


def build_agent_graph() -> CompiledStateGraph:
    """Build the per-agent RAG pipeline graph.

    Flow::

        START → load_context → classify_message
          ├─ [direct] → respond_directly → END
          └─ [retrieval]
               ├─ [rewrite?] → rewrite_query → retrieve_context
               └─ [no rewrite] → retrieve_context
               → apply_confidence_gate
                    ├─ [generate] → generate_response → store_and_finish → END
                    └─ [fallback] → generate_fallback → END

    Returns:
        A compiled :class:`StateGraph` ready for ``ainvoke()`` or use through
        :func:`~app.graph.streaming.run_agent_graph_with_sse`.
    """
    builder = StateGraph(AgentState)  # type: ignore[arg-type]

    # --- Add nodes ---
    builder.add_node("load_context", load_context)
    builder.add_node("classify_message", classify_message)
    builder.add_node("respond_directly", respond_directly)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("apply_confidence_gate", apply_confidence_gate)
    builder.add_node("generate_fallback", generate_fallback)
    builder.add_node("generate_response", generate_response)
    builder.add_node("store_and_finish", store_and_finish)

    # --- Edges ---
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "classify_message")

    # Classification branch: direct response vs. retrieval (with/without rewrite)
    builder.add_conditional_edges(
        "classify_message",
        route_after_classify,
        {
            "respond_directly": "respond_directly",
            "rewrite_query": "rewrite_query",
            "retrieve_context": "retrieve_context",
        },
    )

    builder.add_edge("rewrite_query", "retrieve_context")
    builder.add_edge("retrieve_context", "apply_confidence_gate")

    # Confidence branch: generate vs. fallback
    builder.add_conditional_edges(
        "apply_confidence_gate",
        route_after_confidence,
        {
            "generate_response": "generate_response",
            "generate_fallback": "generate_fallback",
        },
    )

    builder.add_edge("generate_response", "store_and_finish")

    # Terminal edges
    builder.add_edge("respond_directly", END)
    builder.add_edge("generate_fallback", END)
    builder.add_edge("store_and_finish", END)

    return builder.compile()
