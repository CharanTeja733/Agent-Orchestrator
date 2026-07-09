"""SSE streaming bridge for LangGraph agent graph execution.

LangGraph's ``ainvoke()`` returns only the final state.  To preserve the
token-by-token SSE streaming contract the frontend expects, we use an
``asyncio.Queue`` producer/consumer pattern:

1. Create an ``asyncio.Queue``, attach it to ``state["_event_queue"]``.
2. Start ``agent_graph.ainvoke()`` as a background ``asyncio.Task``.
3. Node functions push SSE event dicts to the queue **in real time**
   (e.g. ``generate_response`` pushes ``token`` events,
   ``store_and_finish`` pushes ``sources`` + ``done``).
4. This wrapper yields events from the queue to the SSE response.
5. A ``None`` sentinel signals completion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from langgraph.graph.state import CompiledStateGraph

from app.graph.state import AgentState

logger = logging.getLogger(__name__)


async def run_agent_graph_with_sse(
    agent_graph: CompiledStateGraph,
    initial_state: AgentState,
) -> AsyncIterator[dict]:
    """Run *agent_graph* and yield SSE event dicts.

    Each yielded dict has the shape ``{"event": "<name>", "data": "<json>"}``
    — the exact contract consumed by ``sse_starlette.sse.EventSourceResponse``
    and expected by ``frontend/js/streaming.js``.

    Args:
        agent_graph: A compiled :class:`StateGraph` built by
            :func:`~app.graph.agent_graph.build_agent_graph`.
        initial_state: Fully populated :class:`AgentState` (including
            agent config, user info, classification cache, and infrastructure).

    Yields:
        SSE event dicts: ``token``, ``sources``, ``done``, or ``error``.
    """
    event_queue: asyncio.Queue[dict | None] = asyncio.Queue()
    initial_state["_event_queue"] = event_queue
    initial_state["_test_mode"] = False
    initial_state["overall_start"] = time.time()

    async def _run_graph() -> None:
        """Execute the graph in the background.

        Any unhandled exception is caught, logged, and emitted as an
        ``error`` SSE event before the sentinel is pushed.
        """
        try:
            await agent_graph.ainvoke(initial_state)
        except Exception as exc:
            logger.exception("Agent graph execution failed")
            await event_queue.put(
                _build_error_event(
                    str(exc),
                    detail=getattr(exc, "message", str(exc)),
                    error_type=_error_type_from_exception(exc),
                )
            )
        finally:
            # Sentinel — signals the consumer to stop iterating
            await event_queue.put(None)

    # Start graph execution in the background
    task: asyncio.Task[None] = asyncio.create_task(_run_graph())

    try:
        # Consume events as node functions produce them
        while True:
            event = await event_queue.get()
            if event is None:  # sentinel — graph is done
                break
            yield event
    finally:
        # If the caller cancels the SSE stream (e.g. frontend disconnects),
        # clean up the background task
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_error_event(
    error: str, detail: str = "", error_type: str = "internal_error"
) -> dict:
    """Build an SSE ``error`` event dict matching the existing contract."""
    return {
        "event": "error",
        "data": json.dumps(
            {
                "error": error,
                "detail": detail or error,
                "error_type": error_type,
            }
        ),
    }


def _error_type_from_exception(exc: Exception) -> str:
    """Map exception class names to SSE ``error_type`` strings.

    Mirrors ``BaseAgent._error_type_from_exception``.
    """
    name = type(exc).__name__
    mapping = {
        "ClassificationError": "classification_failed",
        "GeminiGenerationError": "generation_failed",
        "GeminiEmbeddingError": "retrieval_failed",
        "GeminiAPIError": "generation_failed",
        "ForbiddenException": "forbidden",
        "NotFoundException": "not_found",
        "SessionExpiredException": "session_expired",
        "SessionDeactivatedException": "session_deactivated",
    }
    return mapping.get(name, "internal_error")
