"""RAG pipeline service — orchestrates the full Q&A flow (Feature 8).

Combines classification, query rewriting, vector search, confidence gating,
prompt assembly, streaming generation via Gemini, and message persistence.

Reference: ``.claude/specs/08-rag-pipeline.md`` Section 5 (pipeline flow).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ForbiddenException,
    SessionDeactivatedException,
    SessionExpiredException,
)
from app.models.models import User
from app.prompts.rag import (
    BOT_QUESTION_RESPONSE,
    CONFIDENCE_NOTE_MEDIUM,
    CONTEXT_CHUNK_TEMPLATE,
    GREETING_TEMPLATE,
    HARD_FALLBACK_RESPONSE,
    HISTORY_EMPTY,
    HISTORY_ENTRY_TEMPLATE,
    OUT_OF_DOMAIN_RESPONSE,
    SOFT_FALLBACK_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from app.repositories.message import MessageRepository
from app.repositories.session import SessionRepository
from app.services.classifier import ClassifierService
from app.services.gemini import GeminiService
from app.services.search import SearchService
from app.services.session import SessionService

logger = logging.getLogger(__name__)


class RAGService:
    """Orchestrates the full RAG pipeline: classify → rewrite → retrieve →
    confidence-gate → generate/fallback → store.

    Follows the self-initialising constructor pattern used by
    :class:`SearchService` — dependencies are created internally so the
    route layer only needs a db session and API key.
    """

    def __init__(self, db: AsyncSession, gemini_api_key: str) -> None:
        self.db = db
        self.config = settings
        self.gemini_service = GeminiService(gemini_api_key)
        self.classifier_service = ClassifierService(self.gemini_service)
        self.search_service = SearchService(db, gemini_api_key)
        self.session_repo = SessionRepository(db)
        self.message_repo = MessageRepository(db)
        self.session_service = SessionService(db)

    # ------------------------------------------------------------------
    # Public — streaming endpoint
    # ------------------------------------------------------------------

    async def process_query(
        self,
        query: str,
        user: User,
        session_id: Optional[UUID] = None,
    ) -> AsyncIterator[dict]:
        """Run the full RAG pipeline and yield SSE event dicts.

        Each yielded dict has the shape ``{"event": "<name>", "data": "<json>"}``
        and is consumed by ``sse_starlette.sse.EventSourceResponse``.

        Args:
            query: Raw user message.
            user: Authenticated user ORM object.
            session_id: Existing session UUID or ``None`` to auto-create.
        """
        overall_start = time.time()
        full_response = ""
        chunks_for_sources: list[dict] = []
        search_query = query  # may be overwritten by rewriting

        # Per-step timers (populated as pipeline runs)
        classification_ms: Optional[float] = None
        rewriting_ms: Optional[float] = None
        retrieval_ms: Optional[float] = None
        generation_ms: Optional[float] = None
        classification_result: dict = {}

        try:
            # --- Step 0: Load / create session & history -----------------
            session, history_messages = await self._load_context(user, session_id)

            history_dicts = self._messages_to_history_dicts(history_messages)

            # --- Step 1: Classify ----------------------------------------
            t0 = time.time()
            classification_result = await self._classify_message(query, history_dicts)
            classification_ms = (time.time() - t0) * 1000
            classification = classification_result["classification"]

            # --- Route: direct (non-retrieval) ---------------------------
            if not classification_result["requires_retrieval"]:
                direct_response = self._get_direct_response(
                    classification, user.full_name
                )
                # Stream the direct response token by token
                for token in self._tokenize(direct_response):
                    full_response += token
                    yield self._sse_event("token", {"token": token})

                sources: list[dict] = []
                yield self._sse_event("sources", {"sources": sources})

                store_result = await self._store_messages(
                    user_id=user.id,
                    session_id=session.id,
                    query=query,
                    response=full_response,
                    sources=sources,
                    confidence="high",
                    classification=classification,
                    tokens_used=self._estimate_tokens(full_response),
                )

                # Attempt auto-title generation on first substantive message
                await self.session_service.maybe_update_title(
                    session.id, query
                )

                elapsed = (time.time() - overall_start) * 1000
                yield self._sse_event(
                    "done",
                    {
                        "message_id": store_result["message_id"],
                        "session_id": str(session.id),
                        "confidence": "high",
                        "tokens_used": self._estimate_tokens(full_response),
                        "processing_time_ms": round(elapsed, 2),
                    },
                )
                return

            # --- Step 1.5: Rewrite (follow-ups) --------------------------
            if classification_result["requires_rewriting"]:
                t0 = time.time()
                search_query = await self._rewrite_query(query, history_dicts)
                rewriting_ms = (time.time() - t0) * 1000

            # --- Step 2: Retrieve ----------------------------------------
            t0 = time.time()
            search_result = await self._retrieve_context(search_query, user.role)
            retrieval_ms = (time.time() - t0) * 1000
            chunks = search_result["results"]

            # --- Step 3: Confidence gate ---------------------------------
            confidence_level, gate_action = self._apply_confidence_gate(chunks)

            # --- Fallback path -------------------------------------------
            if gate_action == "fallback":
                fallback_text = self._get_fallback_response(confidence_level, chunks)
                for token in self._tokenize(fallback_text):
                    full_response += token
                    yield self._sse_event("token", {"token": token})

                chunks_for_sources = chunks if confidence_level == "low" else []
                sources = self._build_sources_from_chunks(chunks_for_sources)
                yield self._sse_event("sources", {"sources": sources})

                store_result = await self._store_messages(
                    user_id=user.id,
                    session_id=session.id,
                    query=query,
                    response=full_response,
                    sources=sources,
                    confidence=confidence_level,
                    classification=classification,
                    tokens_used=self._estimate_tokens(full_response),
                )

                await self.session_service.maybe_update_title(
                    session.id, query
                )

                elapsed = (time.time() - overall_start) * 1000
                yield self._sse_event(
                    "done",
                    {
                        "message_id": store_result["message_id"],
                        "session_id": str(session.id),
                        "confidence": confidence_level,
                        "tokens_used": self._estimate_tokens(full_response),
                        "processing_time_ms": round(elapsed, 2),
                    },
                )
                return

            # --- Generate path (high / medium confidence) -----------------
            # Step 4: Build prompt
            prompt = self._build_prompt(
                query=search_query,
                chunks=chunks,
                history_messages=history_messages,
                confidence=confidence_level,
            )

            # Step 5: Stream generation
            t0 = time.time()
            async for token in self.gemini_service.generate_stream(
                prompt=prompt,
                temperature=self.config.RESPONSE_TEMPERATURE,
                max_output_tokens=self.config.MAX_COMPLETION_TOKENS,
                top_p=0.95,
            ):
                full_response += token
                yield self._sse_event("token", {"token": token})
            generation_ms = (time.time() - t0) * 1000

            # Build sources from retrieved chunks
            chunks_for_sources = chunks
            sources = self._build_sources_from_chunks(chunks_for_sources)
            yield self._sse_event("sources", {"sources": sources})

            # Step 6: Store
            store_result = await self._store_messages(
                user_id=user.id,
                session_id=session.id,
                query=query,
                response=full_response,
                sources=sources,
                confidence=confidence_level,
                classification=classification,
                tokens_used=self._estimate_tokens(full_response),
            )

            await self.session_service.maybe_update_title(
                session.id, query
            )

            elapsed = (time.time() - overall_start) * 1000
            yield self._sse_event(
                "done",
                {
                    "message_id": store_result["message_id"],
                    "session_id": str(session.id),
                    "confidence": confidence_level,
                    "tokens_used": self._estimate_tokens(full_response),
                    "processing_time_ms": round(elapsed, 2),
                },
            )

        except Exception as exc:
            logger.exception("RAG pipeline error for query: %s", query[:100])
            yield self._sse_event(
                "error",
                {
                    "error": str(exc),
                    "detail": getattr(exc, "message", str(exc)),
                    "error_type": self._error_type_from_exception(exc),
                },
            )

    # ------------------------------------------------------------------
    # Public — non-streaming test endpoint
    # ------------------------------------------------------------------

    async def process_query_test(
        self,
        query: str,
        user: User,
        session_id: Optional[UUID] = None,
    ) -> dict:
        """Run the pipeline and return a complete debug result dict.

        Same pipeline as :meth:`process_query` but uses non-streaming
        generation and captures per-step timing.
        """
        overall_start = time.time()

        pipeline_steps = {
            "classification_ms": None,
            "rewriting_ms": None,
            "retrieval_ms": None,
            "generation_ms": None,
            "storage_ms": None,
        }

        rewritten_query: Optional[str] = None
        search_query = query
        retrieved_chunks: list[dict] = []
        answer = ""
        classification_result: dict = {}
        classification = ""
        confidence_level = "no_match"

        # Step 0: Session & history
        session, history_messages = await self._load_context(user, session_id)
        history_dicts = self._messages_to_history_dicts(history_messages)

        # Step 1: Classify
        t0 = time.time()
        classification_result = await self._classify_message(query, history_dicts)
        pipeline_steps["classification_ms"] = round((time.time() - t0) * 1000, 2)
        classification = classification_result["classification"]

        # Route: direct response
        if not classification_result["requires_retrieval"]:
            answer = self._get_direct_response(classification, user.full_name)
            t0 = time.time()
            store = await self._store_messages(
                user_id=user.id,
                session_id=session.id,
                query=query,
                response=answer,
                sources=[],
                confidence="high",
                classification=classification,
                tokens_used=self._estimate_tokens(answer),
            )
            pipeline_steps["storage_ms"] = round((time.time() - t0) * 1000, 2)
            elapsed = (time.time() - overall_start) * 1000
            return {
                "query": query,
                "rewritten_query": None,
                "classification": classification,
                "classification_confidence": classification_result["confidence"],
                "retrieved_chunks": [],
                "retrieval_count": 0,
                "overall_confidence": "high",
                "answer": answer,
                "sources": [],
                "tokens_used": self._estimate_tokens(answer),
                "processing_time_ms": round(elapsed, 2),
                "pipeline_steps": pipeline_steps,
            }

        # Step 1.5: Rewrite
        if classification_result["requires_rewriting"]:
            t0 = time.time()
            search_query = await self._rewrite_query(query, history_dicts)
            pipeline_steps["rewriting_ms"] = round((time.time() - t0) * 1000, 2)
            rewritten_query = search_query

        # Step 2: Retrieve
        t0 = time.time()
        search_result = await self._retrieve_context(search_query, user.role)
        pipeline_steps["retrieval_ms"] = round((time.time() - t0) * 1000, 2)
        chunks = search_result["results"]
        retrieved_chunks = chunks

        # Step 3: Confidence gate
        confidence_level, gate_action = self._apply_confidence_gate(chunks)

        # Fallback
        if gate_action == "fallback":
            answer = self._get_fallback_response(confidence_level, chunks)
            src_chunks = chunks if confidence_level == "low" else []
            sources = self._build_sources_from_chunks(src_chunks)

            t0 = time.time()
            await self._store_messages(
                user_id=user.id,
                session_id=session.id,
                query=query,
                response=answer,
                sources=sources,
                confidence=confidence_level,
                classification=classification,
                tokens_used=self._estimate_tokens(answer),
            )
            pipeline_steps["storage_ms"] = round((time.time() - t0) * 1000, 2)

            elapsed = (time.time() - overall_start) * 1000
            return {
                "query": query,
                "rewritten_query": rewritten_query,
                "classification": classification,
                "classification_confidence": classification_result["confidence"],
                "retrieved_chunks": retrieved_chunks,
                "retrieval_count": len(retrieved_chunks),
                "overall_confidence": confidence_level,
                "answer": answer,
                "sources": sources,
                "tokens_used": self._estimate_tokens(answer),
                "processing_time_ms": round(elapsed, 2),
                "pipeline_steps": pipeline_steps,
            }

        # Generate
        prompt = self._build_prompt(
            query=search_query,
            chunks=chunks,
            history_messages=history_messages,
            confidence=confidence_level,
        )

        t0 = time.time()
        answer = await self.gemini_service.generate(
            prompt=prompt,
            temperature=self.config.RESPONSE_TEMPERATURE,
            max_output_tokens=self.config.MAX_COMPLETION_TOKENS,
            top_p=0.95,
        )
        pipeline_steps["generation_ms"] = round((time.time() - t0) * 1000, 2)

        sources = self._build_sources_from_chunks(chunks)

        t0 = time.time()
        await self._store_messages(
            user_id=user.id,
            session_id=session.id,
            query=query,
            response=answer,
            sources=sources,
            confidence=confidence_level,
            classification=classification,
            tokens_used=self._estimate_tokens(answer),
        )
        pipeline_steps["storage_ms"] = round((time.time() - t0) * 1000, 2)

        elapsed = (time.time() - overall_start) * 1000
        return {
            "query": query,
            "rewritten_query": rewritten_query,
            "classification": classification,
            "classification_confidence": classification_result["confidence"],
            "retrieved_chunks": retrieved_chunks,
            "retrieval_count": len(retrieved_chunks),
            "overall_confidence": confidence_level,
            "answer": answer,
            "sources": sources,
            "tokens_used": self._estimate_tokens(answer),
            "processing_time_ms": round(elapsed, 2),
            "pipeline_steps": pipeline_steps,
        }

    # ------------------------------------------------------------------
    # Public — health check
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Check every component the RAG pipeline depends on."""
        components: dict[str, str] = {}

        # Database
        try:
            from app.database import get_db_connection

            conn = await get_db_connection()
            await conn.close()
            components["database"] = "connected"
        except Exception:
            components["database"] = "disconnected"

        # Gemini (required by classifier + generation + search embedding)
        if self.config.GEMINI_API_KEY:
            components["gemini"] = "available"
        else:
            components["gemini"] = "unavailable"

        # Classifier (depends on Gemini)
        components["classifier"] = components["gemini"]

        # Search
        try:
            search_health = await self.search_service.health_check()
            components["search"] = search_health["status"]
            documents_indexed = search_health["total_documents_indexed"]
        except Exception:
            components["search"] = "degraded"
            documents_indexed = 0

        # Active sessions
        try:
            active_sessions = await self.session_repo.count_active_sessions()
        except Exception:
            active_sessions = 0

        status = (
            "healthy"
            if all(v in ("available", "healthy", "connected") for v in components.values())
            else "degraded"
        )

        return {
            "status": status,
            "components": components,
            "documents_indexed": documents_indexed,
            "active_sessions": active_sessions,
        }

    # ------------------------------------------------------------------
    # Private — Step 0: Load context
    # ------------------------------------------------------------------

    async def _load_context(
        self, user: User, session_id: Optional[UUID]
    ) -> tuple:
        """Load or create a session and return ``(session, history_messages)``.

        Delegates session management to :class:`SessionService` (Feature 9).

        Raises:
            ForbiddenException: If *session_id* belongs to a different user.
            NotFoundException: If *session_id* does not exist.
            SessionDeactivatedException: If session was manually deactivated.
        """
        session = await self.session_service.get_or_create_session(
            user_id=user.id, session_id=session_id
        )
        history = await self.message_repo.get_conversation_history(
            session.id, limit=self.config.MAX_CONVERSATION_HISTORY
        )
        return session, history

    # ------------------------------------------------------------------
    # Private — Step 1: Classify
    # ------------------------------------------------------------------

    async def _classify_message(
        self, message: str, history: list[dict]
    ) -> dict:
        """Delegate to :class:`ClassifierService.classify`."""
        return await self.classifier_service.classify(message, history)

    # ------------------------------------------------------------------
    # Private — Step 1.5: Rewrite
    # ------------------------------------------------------------------

    async def _rewrite_query(
        self, follow_up: str, history: list[dict]
    ) -> str:
        """Delegate to :meth:`GeminiService.rewrite_query`."""
        return await self.gemini_service.rewrite_query(follow_up, history)

    # ------------------------------------------------------------------
    # Private — Step 2: Retrieve
    # ------------------------------------------------------------------

    async def _retrieve_context(self, query: str, user_role: str) -> dict:
        """Delegate to :meth:`SearchService.search`."""
        return await self.search_service.search(
            query=query,
            user_role=user_role,
            top_k=self.config.TOP_K_RETRIEVAL,
            min_score=self.config.MIN_RETRIEVAL_SCORE,
        )

    # ------------------------------------------------------------------
    # Private — Step 3: Confidence gate
    # ------------------------------------------------------------------

    def _apply_confidence_gate(self, chunks: list[dict]) -> tuple[str, str]:
        """Determine confidence tier and gating action.

        Returns:
            ``(confidence_level, action)`` where *action* is
            ``"generate"`` or ``"fallback"``.
        """
        if not chunks:
            return ("no_match", "fallback")

        max_score = max(r["score"] for r in chunks)

        if max_score >= self.config.HIGH_CONFIDENCE_THRESHOLD:
            return ("high", "generate")
        elif max_score >= self.config.MEDIUM_CONFIDENCE_THRESHOLD:
            return ("medium", "generate")
        elif max_score >= self.config.LOW_CONFIDENCE_THRESHOLD:
            return ("low", "fallback")
        else:
            return ("no_match", "fallback")

    # ------------------------------------------------------------------
    # Private — Step 4: Build prompt
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        query: str,
        chunks: list[dict],
        history_messages: list,
        confidence: str,
    ) -> str:
        """Assemble the full prompt with system prompt + user template."""
        context_str = self._format_context_for_prompt(chunks)
        history_str = self._format_history_for_prompt(history_messages)
        confidence_note = (
            CONFIDENCE_NOTE_MEDIUM if confidence == "medium" else ""
        )

        user_prompt = USER_PROMPT_TEMPLATE.format(
            conversation_history=history_str,
            retrieved_context=context_str,
            user_query=query,
            confidence_note=confidence_note,
        )

        return f"{SYSTEM_PROMPT}\n\n{user_prompt}"

    # ------------------------------------------------------------------
    # Private — formatting helpers
    # ------------------------------------------------------------------

    def _format_context_for_prompt(self, chunks: list[dict]) -> str:
        """Format retrieved chunks for the prompt using the spec template."""
        if not chunks:
            return "(No relevant documents found)"

        formatted = []
        for ch in chunks:
            formatted.append(
                CONTEXT_CHUNK_TEMPLATE.format(
                    source=ch.get("source", "Unknown"),
                    page=ch.get("page") or "N/A",
                    section=ch.get("section") or "N/A",
                    content=ch.get("content", ""),
                )
            )
        return "\n".join(formatted)

    def _format_history_for_prompt(self, messages: list) -> str:
        """Format conversation history as ``User: ...\\nAssistant: ...``."""
        if not messages:
            return HISTORY_EMPTY

        lines = []
        for msg in messages:
            # Message can be an ORM object or a dict
            if hasattr(msg, "role"):
                role = msg.role.capitalize()
                content = msg.content
            else:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")
            lines.append(HISTORY_ENTRY_TEMPLATE.format(role=role, content=content))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private — response builders
    # ------------------------------------------------------------------

    def _get_fallback_response(
        self, confidence_tier: str, chunks: list[dict]
    ) -> str:
        """Return the appropriate fallback text."""
        if confidence_tier in ("no_match",):
            return HARD_FALLBACK_RESPONSE

        # Soft fallback — include top 1-2 excerpts
        excerpts: list[str] = []
        for ch in chunks[:2]:
            content = ch.get("content", "")
            excerpts.append(f"• {content[:200]}...")

        related = "\n".join(excerpts) if excerpts else "(No related excerpts found)"
        return SOFT_FALLBACK_TEMPLATE.format(related_excerpts=related)

    def _get_direct_response(self, classification: str, user_name: str) -> str:
        """Return the pre-built response for non-retrieval classifications."""
        if classification == "greeting_only":
            return GREETING_TEMPLATE.format(user_name=user_name)
        elif classification == "bot_question":
            return BOT_QUESTION_RESPONSE
        elif classification == "out_of_domain":
            return OUT_OF_DOMAIN_RESPONSE
        # Fallback — should never happen as classifier validates output
        return GREETING_TEMPLATE.format(user_name=user_name)

    # ------------------------------------------------------------------
    # Private — source extraction
    # ------------------------------------------------------------------

    def _build_sources_from_chunks(self, chunks: list[dict]) -> list[dict]:
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

    # ------------------------------------------------------------------
    # Private — Step 6: Store messages
    # ------------------------------------------------------------------

    async def _store_messages(
        self,
        user_id: UUID,
        session_id: UUID,
        query: str,
        response: str,
        sources: list[dict],
        confidence: str,
        classification: str,
        tokens_used: int,
    ) -> dict:
        """Persist the user message and assistant response.

        If the database write fails the error is logged but **not** re-raised
        — the user still gets their answer.
        """
        try:
            # Store user message
            await self.message_repo.create_message(
                session_id=session_id,
                user_id=user_id,
                role="user",
                content=query,
                classification=classification,
            )

            # Store assistant response
            msg = await self.message_repo.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=response,
                sources=sources,
                confidence=confidence,
                tokens_used=tokens_used,
            )

            # Touch session timestamp and extend expiry (Feature 9)
            await self.session_service.update_activity(session_id)

            return {"message_id": str(msg.id), "session_id": str(session_id)}

        except Exception:
            logger.exception(
                "Failed to store messages for session %s — response already "
                "returned to user",
                session_id,
            )
            return {"message_id": "", "session_id": str(session_id)}

    # ------------------------------------------------------------------
    # Private — utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _messages_to_history_dicts(messages: list) -> list[dict]:
        """Convert ORM Message objects to the ``[{"role": ..., "content": ...}]``
        format expected by ClassifierService and GeminiService."""
        return [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Split a pre-built response into pseudo-tokens for SSE streaming.

        Splits on word boundaries so direct/fallback responses still produce
        a reasonable stream of ``token`` events.
        """
        # Split on word boundaries while preserving whitespace/punctuation
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

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token count — ~4 chars per token for English text."""
        return max(1, len(text) // 4)

    @staticmethod
    def _sse_event(event: str, data: dict) -> dict:
        """Build an SSE event dict consumed by
        ``sse_starlette.sse.EventSourceResponse``."""
        return {"event": event, "data": json.dumps(data)}

    @staticmethod
    def _error_type_from_exception(exc: Exception) -> str:
        """Map exception classes to SSE ``error_type`` strings."""
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
