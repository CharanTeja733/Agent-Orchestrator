"""Non-streaming test endpoint handler.

Mirrors ``BaseAgent.process_query_test()`` — runs the agent graph in
``_test_mode`` (non-streaming generation, no SSE events) and returns the
complete debug dict.
"""

from __future__ import annotations

import time
from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.graph.nodes import _estimate_tokens


async def run_agent_graph_test(
    agent_graph: CompiledStateGraph,
    initial_state: dict[str, Any],
) -> dict:
    """Run the agent graph in non-streaming test mode.

    Args:
        agent_graph: Compiled agent :class:`StateGraph`.
        initial_state: Fully populated initial state (same as the streaming
            path but ``_test_mode`` is forced to ``True``).

    Returns:
        Complete debug dict matching ``OrchestratorTestResponse`` shape.
    """
    initial_state["_event_queue"] = None
    initial_state["_test_mode"] = True
    initial_state["overall_start"] = time.time()

    final_state = await agent_graph.ainvoke(initial_state)

    rewritten_query = final_state.get("search_query")
    if rewritten_query == final_state.get("query"):
        rewritten_query = None

    return {
        "query": final_state.get("query", ""),
        "rewritten_query": rewritten_query,
        "classification": final_state.get("classification", ""),
        "classification_confidence": (
            final_state.get("classification_result", {}).get("confidence", 0.0)
            if final_state.get("classification_result")
            else 0.0
        ),
        "retrieved_chunks": final_state.get("retrieved_chunks", []),
        "retrieval_count": len(final_state.get("retrieved_chunks", [])),
        "overall_confidence": final_state.get("confidence_level", "no_match"),
        "answer": final_state.get("full_response", ""),
        "sources": final_state.get("sources", []),
        "tokens_used": _estimate_tokens(final_state.get("full_response", "")),
        "processing_time_ms": round(
            (time.time() - initial_state["overall_start"]) * 1000, 2
        ),
        "pipeline_steps": {
            "classification_ms": final_state.get("classification_ms"),
            "rewriting_ms": final_state.get("rewriting_ms"),
            "retrieval_ms": final_state.get("retrieval_ms"),
            "generation_ms": final_state.get("generation_ms"),
            "storage_ms": final_state.get("storage_ms"),
        },
    }
