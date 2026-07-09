"""LangGraph node functions for orchestrator and agent graphs.

Each node is an ``async`` function that receives the current state and
returns a partial state dict with only the fields it updates.

All existing services (``GeminiService``, ``ClassifierService``,
``SearchService``, ``SessionService``) and repositories are imported and
called directly — no new service wrappers.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.repositories.message import MessageRepository
from app.services.classifier import ClassifierService
from app.services.gemini import GeminiService
from app.services.search import SearchService
from app.services.session import SessionService

logger = logging.getLogger(__name__)


# ===========================================================================
# Pure helper functions (extracted from BaseAgent)
# ===========================================================================


def _tokenize(text: str) -> list[str]:
    """Split a pre-built response into pseudo-tokens for SSE streaming.

    Splits on word boundaries so direct/fallback responses still produce
    a reasonable stream of ``token`` events.
    """
    tokens: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in (" ", "\n", ".", ",", "!", "?", ":", ";"):
            tokens.append(current)
            current = ""
    if current:
        tokens.append(current)
    return tokens


def _estimate_tokens(text: str) -> int:
    """Rough token count — ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def _sse_event(event: str, data: dict) -> dict:
    """Build an SSE event dict consumed by
    ``sse_starlette.sse.EventSourceResponse``."""
    return {"event": event, "data": json.dumps(data)}


def _build_sources_from_chunks(chunks: list[dict]) -> list[dict]:
    """Extract source metadata from retrieved chunks."""
    return [
        {
            "document": ch.get("source", "Unknown"),
            "page": ch.get("page"),
            "section": ch.get("section"),
            "excerpt": ch.get("content", "")[:200],
        }
        for ch in chunks
    ]


def _format_context_for_prompt(
    chunks: list[dict], context_chunk_template: str
) -> str:
    """Format retrieved chunks for the prompt."""
    if not chunks:
        return "(No relevant documents found)"
    formatted = []
    for ch in chunks:
        formatted.append(
            context_chunk_template.format(
                source=ch.get("source", "Unknown"),
                page=ch.get("page") or "N/A",
                section=ch.get("section") or "N/A",
                content=ch.get("content", ""),
            )
        )
    return "\n".join(formatted)


def _format_history_for_prompt(
    messages: list, history_entry_template: str, history_empty: str
) -> str:
    """Format conversation history as ``User: ...\\nAssistant: ...``."""
    if not messages:
        return history_empty
    lines = []
    for msg in messages:
        if hasattr(msg, "role"):
            role = msg.role.capitalize()
            content = msg.content
        else:
            role = msg.get("role", "unknown").capitalize()
            content = msg.get("content", "")
        lines.append(history_entry_template.format(role=role, content=content))
    return "\n".join(lines)


def _messages_to_history_dicts(messages: list) -> list[dict]:
    """Convert ORM Message objects to ``[{"role": ..., "content": ...}]``."""
    return [{"role": m.role, "content": m.content} for m in messages]


def _build_prompt(state: dict[str, Any]) -> str:
    """Assemble the full prompt with system prompt + user template.

    Reads all inputs from *state* rather than ``self`` attributes.
    """
    context_str = _format_context_for_prompt(
        state.get("retrieved_chunks", []), state["context_chunk_template"]
    )
    history_str = _format_history_for_prompt(
        state.get("history_messages", []),
        state["history_entry_template"],
        state["history_empty"],
    )
    confidence_note = (
        state["confidence_note_medium"]
        if state.get("confidence_level") == "medium"
        else ""
    )

    user_prompt = state["user_prompt_template"].format(
        conversation_history=history_str,
        retrieved_context=context_str,
        user_query=state.get("search_query", state.get("query", "")),
        confidence_note=confidence_note,
    )
    return f"{state['system_prompt']}\n\n{user_prompt}"


def _get_fallback_response(
    confidence_tier: str,
    chunks: list[dict],
    hard_fallback_response: str,
    soft_fallback_template: str,
) -> str:
    """Return the appropriate fallback text."""
    if confidence_tier in ("no_match",):
        return hard_fallback_response

    # Soft fallback — include top 1-2 excerpts
    excerpts: list[str] = []
    for ch in chunks[:2]:
        content = ch.get("content", "")
        excerpts.append(f"• {content[:200]}...")

    related = "\n".join(excerpts) if excerpts else "(No related excerpts found)"
    return soft_fallback_template.format(related_excerpts=related)


def _build_rate_limit_fallback(chunks: list[dict]) -> str:
    """Build a helpful response from chunks when Gemini is unavailable."""
    if not chunks:
        return (
            "I found some relevant information but I'm currently unable "
            "to generate a complete response due to API rate limits. "
            "Please try again in a minute, or contact the IT Service Desk "
            "at ext. 4357 for urgent issues."
        )

    lines = [
        "⚠️ **Service is temporarily busy — showing retrieved results instead "
        "of a generated response.**\n",
        "Here's what I found that may help:\n",
    ]
    for i, ch in enumerate(chunks[:3], 1):
        source = ch.get("source", "Unknown")
        section = ch.get("section", "")
        content = ch.get("content", "")
        label = f"**{source}**"
        if section:
            label += f" — {section}"
        lines.append(f"{i}. {label}\n> {content[:300].strip()}...\n")

    lines.append(
        "---\n"
        "🔁 Please try your query again shortly, or contact the IT Service "
        "Desk at ext. 4357 for immediate help."
    )
    return "\n".join(lines)


def _get_direct_response(
    classification: str,
    user_name: str,
    query: str,
    greeting_template: str,
    thanks_response: str,
    bye_response: str,
    greeting_back_response: str,
    bot_question_response: str,
    out_of_domain_response: str,
) -> str:
    """Return the pre-built response for non-retrieval classifications."""
    if classification == "greeting_only":
        return _pick_greeting_response(
            query, user_name, greeting_template, thanks_response,
            bye_response, greeting_back_response,
        )
    elif classification == "bot_question":
        return bot_question_response
    elif classification == "out_of_domain":
        return out_of_domain_response
    return greeting_template.format(user_name=user_name)


def _pick_greeting_response(
    query: str,
    user_name: str,
    greeting_template: str,
    thanks_response: str,
    bye_response: str,
    greeting_back_response: str,
) -> str:
    """Select the appropriate greeting response based on message content."""
    msg = query.strip().lower()

    thanks_patterns = [
        r"^(thanks|thank\s*you|thx|ty|tyvm|cheers|appreciate\s*it|much\s*appreciated)",
        r"\b(thanks|thank\s*you)\b",
    ]
    for pat in thanks_patterns:
        if re.search(pat, msg):
            return thanks_response.format(user_name=user_name)

    bye_patterns = [
        r"^(bye|goodbye|see\s*you|cya|later|good\s*night|have\s*a\s*good\s*(day|one))",
    ]
    for pat in bye_patterns:
        if re.search(pat, msg):
            return bye_response.format(user_name=user_name)

    short_greeting_patterns = [
        r"^(hey|heya|yo|sup|howdy|good\s*morning|good\s*afternoon|good\s*evening)",
    ]
    for pat in short_greeting_patterns:
        if re.search(pat, msg):
            return greeting_back_response.format(user_name=user_name)

    return greeting_template.format(user_name=user_name)


async def _push_event(
    state: dict[str, Any], event: str, data: dict
) -> None:
    """Push an SSE event to the async queue if streaming is active."""
    queue = state.get("_event_queue")
    if queue is not None and not state.get("_test_mode", False):
        await queue.put(_sse_event(event, data))


async def _store_messages(
    state: dict[str, Any], sources: list[dict]
) -> dict:
    """Persist user + assistant messages and update session activity.

    Errors are logged but NOT re-raised — the user still gets their answer.
    """
    db = state["db"]
    message_repo = MessageRepository(db)
    session_service = SessionService(db)
    session = state.get("session")
    session_id = session.id if session else state.get("session_id")
    user_id = state["user_id"]
    query = state["query"]
    full_response = state.get("full_response", "")
    confidence = state.get("confidence_level", "no_match")
    classification = state.get("classification", "")
    agent_name = state.get("agent_name", "")
    overall_start = state.get("overall_start", time.time())

    elapsed = (time.time() - overall_start) * 1000
    tokens_used = _estimate_tokens(full_response)

    try:
        await message_repo.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=query,
            classification=classification,
            agent_name=agent_name,
        )

        msg = await message_repo.create_message(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=full_response,
            sources=sources,
            confidence=confidence,
            tokens_used=tokens_used,
            processing_time_ms=round(elapsed, 2),
            agent_name=agent_name,
        )

        await session_service.update_activity(session_id)

        return {"message_id": str(msg.id), "session_id": str(session_id)}

    except Exception:
        logger.exception(
            "Failed to store messages for session %s — response already "
            "returned to user",
            session_id,
        )
        return {"message_id": "", "session_id": str(session_id) if session_id else ""}


# ===========================================================================
# Orchestrator Graph Nodes
# ===========================================================================


async def check_override(state: dict[str, Any]) -> dict[str, Any]:
    """Orchestrator: validate explicit agent override if provided.

    If ``requested_agent`` is set and valid, writes ``agent_name`` to state
    so downstream nodes skip classification.
    """
    requested = state.get("requested_agent")
    if not requested:
        return {}

    from app.graph.agent_registry import get_agent_config

    agent_name = requested.lower().strip()
    try:
        get_agent_config(agent_name)
    except KeyError:
        from app.graph.agent_registry import _load_configs
        _load_configs()
        from app.graph.agent_registry import AGENT_CONFIGS
        valid = list(AGENT_CONFIGS.keys())
        return {
            "error": f"Unknown agent '{requested}'. Valid agents: {valid}",
        }

    logger.info("Orchestrator: explicit override → %s", agent_name)
    return {"agent_name": agent_name}


async def quick_classify(state: dict[str, Any]) -> dict[str, Any]:
    """Orchestrator: classify the query for automatic routing.

    Fetches conversation history if a ``session_id`` is provided so the
    classifier can detect follow-ups.
    """
    db = state["db"]
    gemini_api_key = state["gemini_api_key"]
    query = state["query"]
    session_id = state.get("session_id")

    gemini = GeminiService(gemini_api_key)
    classifier = ClassifierService(gemini)

    history: list[dict] = []
    if session_id:
        try:
            message_repo = MessageRepository(db)
            history_msgs = await message_repo.get_conversation_history(
                session_id, limit=6
            )
            history = _messages_to_history_dicts(history_msgs)
        except Exception:
            logger.warning(
                "Could not load history for session %s — "
                "classifying without context",
                session_id,
            )

    result = await classifier.classify(query, history)
    logger.info(
        "Orchestrator classification: %s → %s (confidence: %s)",
        query[:80],
        result.get("classification"),
        result.get("confidence"),
    )
    return {"classification_result": result}


async def map_to_agent(state: dict[str, Any]) -> dict[str, Any]:
    """Orchestrator: map classification label to agent name.

    - ``hr_question`` / ``it_question`` → direct mapping
    - ``follow_up`` → look up last agent used in this session
    - Everything else → default agent
    """
    from app.graph.agent_registry import CLASSIFICATION_AGENT_MAP, DEFAULT_AGENT

    classification_result = state.get("classification_result", {})
    classification = classification_result.get("classification", "")
    session_id = state.get("session_id")

    # Direct mapping
    if classification in CLASSIFICATION_AGENT_MAP:
        agent_name = CLASSIFICATION_AGENT_MAP[classification]
        logger.info("Orchestrator routing: %s → %s", classification, agent_name)
        return {"agent_name": agent_name}

    # Follow-ups → same agent as previous message in session
    if classification == "follow_up":
        if session_id:
            try:
                db = state["db"]
                message_repo = MessageRepository(db)
                last_agent = await message_repo.get_last_agent_name(session_id)
                if last_agent:
                    logger.info(
                        "Orchestrator follow-up: session %s → %s",
                        session_id, last_agent,
                    )
                    return {"agent_name": last_agent}
            except Exception:
                logger.exception(
                    "Failed to look up last agent for session %s", session_id
                )

    # Default
    logger.info("Orchestrator default: %s → %s", classification, DEFAULT_AGENT)
    return {"agent_name": DEFAULT_AGENT}


async def load_agent_config(state: dict[str, Any]) -> dict[str, Any]:
    """Orchestrator: load the full agent config dict from the registry."""
    from app.graph.agent_registry import get_agent_config

    agent_name = state.get("agent_name", "")
    if not agent_name:
        return {"error": "No agent determined for routing"}

    try:
        config = get_agent_config(agent_name)
        return {"agent_config": config}
    except KeyError as exc:
        return {"error": str(exc)}


# ===========================================================================
# Agent Graph Nodes
# ===========================================================================


async def load_context(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: load or create a session and fetch conversation history.

    Step 0 of the RAG pipeline — always runs first.
    """
    db = state["db"]
    user_id = state["user_id"]
    session_id = state.get("session_id")

    session_service = SessionService(db)
    session = await session_service.get_or_create_session(
        user_id=user_id, session_id=session_id
    )

    message_repo = MessageRepository(db)
    limit = state.get("max_conversation_history", 6)
    history_messages = await message_repo.get_conversation_history(
        session.id, limit=limit
    )
    history_dicts = _messages_to_history_dicts(history_messages)

    return {
        "session": session,
        "history_messages": history_messages,
        "history_dicts": history_dicts,
    }


async def classify_message(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: classify the query (or use cached classification from orchestrator).

    Step 1 of the RAG pipeline.  If ``classification_result`` is already
    populated (cached by the orchestrator), it is used directly — saving an
    API call.
    """
    classification_result = state.get("classification_result")

    if not classification_result or not classification_result.get("classification"):
        # No cached result — classify fresh
        gemini = GeminiService(state["gemini_api_key"])
        classifier = ClassifierService(gemini)
        history = state.get("history_dicts", [])
        classification_result = await classifier.classify(state["query"], history)
        logger.debug("Agent classification (fresh): %s", classification_result.get("classification"))
    else:
        logger.debug(
            "Agent classification (cached from orchestrator): %s",
            classification_result.get("classification"),
        )

    classification = classification_result.get("classification", "")
    requires_retrieval = classification_result.get("requires_retrieval", True)
    requires_rewriting = classification_result.get("requires_rewriting", False)

    return {
        "classification_result": classification_result,
        "classification": classification,
        "requires_retrieval": requires_retrieval,
        "requires_rewriting": requires_rewriting,
    }


async def respond_directly(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: respond without retrieval (greetings, bot questions, out-of-domain).

    Terminal node — pushes ``token*`` → ``sources`` → ``done``, stores
    messages, then ends the graph.
    """
    classification = state.get("classification", "greeting_only")
    user_name = state.get("full_name", "User")
    query = state.get("query", "")

    response = _get_direct_response(
        classification, user_name, query,
        state["greeting_template"],
        state["thanks_response"],
        state["bye_response"],
        state["greeting_back_response"],
        state["bot_question_response"],
        state["out_of_domain_response"],
    )

    # Stream tokens
    for token in _tokenize(response):
        state["full_response"] = state.get("full_response", "") + token
        await _push_event(state, "token", {"token": token})

    # Sources (empty for direct responses)
    await _push_event(state, "sources", {"sources": []})

    # Store messages
    store_result = await _store_messages(state, sources=[])

    # Auto-title
    session = state.get("session")
    if session:
        try:
            session_service = SessionService(state["db"])
            await session_service.maybe_update_title(session.id, query)
        except Exception:
            logger.exception("Failed to auto-title session")

    # Done event
    overall_start = state.get("overall_start", time.time())
    elapsed = (time.time() - overall_start) * 1000
    await _push_event(state, "done", {
        "message_id": store_result.get("message_id", ""),
        "session_id": store_result.get("session_id", ""),
        "confidence": "high",
        "tokens_used": _estimate_tokens(response),
        "processing_time_ms": round(elapsed, 2),
        "classification_ms": state.get("classification_ms"),
        "retrieval_ms": None,
        "generation_ms": None,
        "rewriting_ms": None,
        "agent_name": state.get("agent_name", ""),
    })

    return {
        "full_response": response,
        "message_id": store_result.get("message_id", ""),
    }


async def rewrite_query(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: rewrite a follow-up question into a standalone query.

    Step 1.5 — only runs for ``follow_up`` classifications.
    """
    gemini = GeminiService(state["gemini_api_key"])
    history = state.get("history_dicts", [])
    query = state.get("query", "")

    t0 = time.time()
    rewritten = await gemini.rewrite_query(query, history)
    rewriting_ms = (time.time() - t0) * 1000

    logger.info("Query rewritten: %r → %r", query[:80], rewritten[:80])
    return {
        "search_query": rewritten,
        "rewriting_ms": rewriting_ms,
    }


async def retrieve_context(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: perform vector search against the agent's document collection.

    Step 2 — generates embedding, runs pgvector cosine similarity, applies
    access-level filtering.
    """
    gemini_api_key = state["gemini_api_key"]
    db = state["db"]
    collection_name = state.get("collection_name", "hr_documents")
    search_query = state.get("search_query", state.get("query", ""))
    user_role = state.get("user_role", "employee")

    search_service = SearchService(
        db, gemini_api_key, collection_name=collection_name
    )

    t0 = time.time()
    result = await search_service.search(
        query=search_query,
        user_role=user_role,
        top_k=state.get("top_k_retrieval", 5),
        min_score=state.get("min_retrieval_score", 0.5),
    )
    retrieval_ms = (time.time() - t0) * 1000

    chunks = result.get("results", [])
    logger.info(
        "Retrieval: %d chunks (%.1fms), top score: %s",
        len(chunks),
        retrieval_ms,
        chunks[0]["score"] if chunks else 0,
    )

    return {
        "retrieved_chunks": chunks,
        "retrieval_ms": retrieval_ms,
    }


async def apply_confidence_gate(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: determine confidence level and gating action.

    Step 3 — maps the best chunk score to a tier and decides whether to
    generate or fallback.
    """
    chunks = state.get("retrieved_chunks", [])
    high = state.get("high_confidence_threshold", 0.75)
    medium = state.get("medium_confidence_threshold", 0.50)
    low = state.get("low_confidence_threshold", 0.30)

    if not chunks:
        return {"confidence_level": "no_match", "gate_action": "fallback"}

    max_score = max(r["score"] for r in chunks)

    if max_score >= high:
        return {"confidence_level": "high", "gate_action": "generate"}
    elif max_score >= medium:
        return {"confidence_level": "medium", "gate_action": "generate"}
    elif max_score >= low:
        return {"confidence_level": "low", "gate_action": "fallback"}
    else:
        return {"confidence_level": "no_match", "gate_action": "fallback"}


async def generate_fallback(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: emit a fallback response when confidence is too low.

    Terminal node — pushes ``token*`` → ``sources`` → ``done``, stores
    messages, then ends the graph.
    """
    confidence_tier = state.get("confidence_level", "no_match")
    chunks = state.get("retrieved_chunks", [])

    response = _get_fallback_response(
        confidence_tier, chunks,
        state["hard_fallback_response"],
        state["soft_fallback_template"],
    )

    # Stream tokens
    for token in _tokenize(response):
        state["full_response"] = state.get("full_response", "") + token
        await _push_event(state, "token", {"token": token})

    # Sources (only for low confidence, empty for no_match)
    if confidence_tier == "low":
        sources = _build_sources_from_chunks(chunks)
    else:
        sources = []
    await _push_event(state, "sources", {"sources": sources})

    # Store
    store_result = await _store_messages(state, sources=sources)

    # Auto-title
    session = state.get("session")
    if session:
        try:
            session_service = SessionService(state["db"])
            await session_service.maybe_update_title(
                session.id, state.get("query", "")
            )
        except Exception:
            logger.exception("Failed to auto-title session")

    # Done event
    overall_start = state.get("overall_start", time.time())
    elapsed = (time.time() - overall_start) * 1000
    await _push_event(state, "done", {
        "message_id": store_result.get("message_id", ""),
        "session_id": store_result.get("session_id", ""),
        "confidence": confidence_tier,
        "tokens_used": _estimate_tokens(response),
        "processing_time_ms": round(elapsed, 2),
        "classification_ms": state.get("classification_ms"),
        "retrieval_ms": state.get("retrieval_ms"),
        "generation_ms": None,
        "rewriting_ms": state.get("rewriting_ms"),
        "agent_name": state.get("agent_name", ""),
    })

    return {
        "full_response": response,
        "sources": sources,
        "message_id": store_result.get("message_id", ""),
    }


async def generate_response(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: build prompt and stream Gemini generation (or non-streaming in test).

    Step 4-5 — the core generation node.  Pushes ``token`` events in real
    time.  Falls back to a rate-limit response if generation fails.
    """
    gemini_api_key = state["gemini_api_key"]
    gemini = GeminiService(gemini_api_key)
    prompt = _build_prompt(state)
    queue = state.get("_event_queue")
    test_mode = state.get("_test_mode", False)
    full_response = ""
    t0 = time.time()

    try:
        if test_mode:
            # Non-streaming for /test endpoint
            full_response = await gemini.generate(
                prompt=prompt,
                temperature=state.get("response_temperature", 0.3),
                max_output_tokens=state.get("max_completion_tokens", 1024),
                top_p=0.95,
            )
        else:
            # Streaming — push each token as it arrives
            async for token in gemini.generate_stream(
                prompt=prompt,
                temperature=state.get("response_temperature", 0.3),
                max_output_tokens=state.get("max_completion_tokens", 1024),
                top_p=0.95,
            ):
                full_response += token
                if queue is not None:
                    await queue.put(
                        _sse_event("token", {"token": token})
                    )
    except Exception as exc:
        logger.warning("Generation failed (likely rate-limited): %s", exc)
        full_response = _build_rate_limit_fallback(
            state.get("retrieved_chunks", [])
        )
        if queue is not None and not test_mode:
            for token in _tokenize(full_response):
                await queue.put(
                    _sse_event("token", {"token": token})
                )

    generation_ms = (time.time() - t0) * 1000
    logger.info("Generation complete: %d tokens, %.1fms", len(full_response), generation_ms)

    return {
        "full_response": full_response,
        "generation_ms": generation_ms,
    }


async def store_and_finish(state: dict[str, Any]) -> dict[str, Any]:
    """Agent: build sources, persist messages, emit ``sources`` + ``done`` events.

    Final node of the generate path — terminal after this.
    """
    chunks = state.get("retrieved_chunks", [])
    sources = _build_sources_from_chunks(chunks)
    t0 = time.time()

    # Sources event
    await _push_event(state, "sources", {"sources": sources})

    # Store messages
    store_result = await _store_messages(state, sources=sources)
    storage_ms = (time.time() - t0) * 1000

    # Auto-title
    session = state.get("session")
    if session:
        try:
            session_service = SessionService(state["db"])
            await session_service.maybe_update_title(
                session.id, state.get("query", "")
            )
        except Exception:
            logger.exception("Failed to auto-title session")

    # Done event
    overall_start = state.get("overall_start", time.time())
    elapsed = (time.time() - overall_start) * 1000
    await _push_event(state, "done", {
        "message_id": store_result.get("message_id", ""),
        "session_id": store_result.get("session_id", ""),
        "confidence": state.get("confidence_level", "no_match"),
        "tokens_used": _estimate_tokens(state.get("full_response", "")),
        "processing_time_ms": round(elapsed, 2),
        "classification_ms": state.get("classification_ms"),
        "retrieval_ms": state.get("retrieval_ms"),
        "generation_ms": state.get("generation_ms"),
        "rewriting_ms": state.get("rewriting_ms"),
        "agent_name": state.get("agent_name", ""),
    })

    return {
        "sources": sources,
        "message_id": store_result.get("message_id", ""),
        "storage_ms": storage_ms,
    }
