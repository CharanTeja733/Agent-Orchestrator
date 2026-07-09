"""TypedDict state schemas for LangGraph graphs.

Defines the contract between all graph nodes — what state is available at
each step and what updates each node must produce.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from typing_extensions import NotRequired, TypedDict


# ---------------------------------------------------------------------------
# Orchestrator State
# ---------------------------------------------------------------------------


class OrchestratorState(TypedDict):
    """State for the routing-level orchestrator graph.

    Input fields (set before invocation):
      query, user_id, full_name, user_role, session_id, requested_agent,
      db, gemini_api_key

    Output fields (populated by graph execution):
      classification_result, agent_name, agent_config, error
    """

    # Inputs (from HTTP request / auth)
    query: str
    user_id: UUID
    full_name: str
    user_role: str
    session_id: Optional[UUID]
    requested_agent: Optional[str]

    # Infrastructure (from FastAPI Depends)
    db: Any  # sqlalchemy.ext.asyncio.AsyncSession
    gemini_api_key: str

    # Routing results (set by nodes)
    classification_result: NotRequired[Optional[dict]]
    agent_name: NotRequired[Optional[str]]
    agent_config: NotRequired[Optional[dict]]  # full agent attrs dict

    # Error
    error: NotRequired[Optional[str]]


# ---------------------------------------------------------------------------
# Agent State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    """State for the per-agent RAG pipeline graph.

    Input fields:
      query, user_id, full_name, user_role, session_id, agent_config fields,
      db, gemini_api_key

    Mutable pipeline fields (set by nodes as execution progresses):
      session, history_messages, classification_result, search_query,
      retrieved_chunks, confidence_level, gate_action, full_response, ...

    Streaming:
      _event_queue: asyncio.Queue[dict | None]
      _test_mode: bool
    """

    # -- Inputs --
    query: str
    user_id: UUID
    full_name: str
    user_role: str
    session_id: Optional[UUID]

    # -- Agent configuration (injected from registry, one dict per agent) --
    agent_name: str
    display_name: str
    collection_name: str
    system_prompt: str
    user_prompt_template: str
    context_chunk_template: str
    history_entry_template: str
    history_empty: str
    confidence_note_medium: str
    low_confidence_disclaimer: str
    hard_fallback_response: str
    soft_fallback_template: str
    greeting_template: str
    thanks_response: str
    bye_response: str
    greeting_back_response: str
    bot_question_response: str
    out_of_domain_response: str

    # -- Thresholds (with defaults from agent config) --
    top_k_retrieval: int
    min_retrieval_score: float
    high_confidence_threshold: float
    medium_confidence_threshold: float
    low_confidence_threshold: float
    max_conversation_history: int
    max_completion_tokens: int
    response_temperature: float

    # -- Infrastructure --
    db: Any
    gemini_api_key: str

    # -- Pipeline mutable state --
    session: Any  # sqlalchemy ORM Session object
    history_messages: list
    history_dicts: list
    classification_result: dict
    classification: str
    requires_retrieval: bool
    requires_rewriting: bool
    search_query: str
    retrieved_chunks: list
    confidence_level: str
    gate_action: str
    full_response: str
    sources: list
    message_id: Optional[str]

    # -- Timing --
    overall_start: float
    classification_ms: Optional[float]
    rewriting_ms: Optional[float]
    retrieval_ms: Optional[float]
    generation_ms: Optional[float]
    storage_ms: Optional[float]

    # -- Streaming / mode --
    _event_queue: Optional[Any]  # asyncio.Queue, set by streaming wrapper
    _test_mode: bool  # True for /test endpoint

    # -- Error --
    error: Optional[str]
