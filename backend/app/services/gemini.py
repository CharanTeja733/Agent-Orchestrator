"""Gemini service layer — centralized interface for all Gemini AI interactions.

This is the **only** module in the codebase that imports from ``google.genai``.
All other modules go through this service for embeddings, text generation,
classification, and query rewriting.

Key design decisions:
- Sync SDK calls are wrapped in ``asyncio.to_thread()`` to keep the event
  loop free.
- Streaming uses an ``asyncio.Queue`` + ``loop.run_in_executor`` bridge.
- Retry logic is centralized in ``_call_with_retry`` — never duplicated.
- Model names are class constants, not scattered across the codebase.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

from app.core.exceptions import (
    GeminiAPIError,
    GeminiConfigurationError,
    GeminiEmbeddingError,
    GeminiGenerationError,
    GeminiRateLimitError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_CLASSIFICATION_TEMPLATE = """\
You are an HR assistant classifier. Classify the user's message into one \
of these categories:

- "greeting_only": Simple greetings ("hi", "hello", "good morning", "hey")
- "bot_question": Questions about the assistant itself ("who are you?", \
"what can you do?", "are you an AI?")
- "out_of_domain": Questions not related to HR or workplace policies \
("what's the weather?", "tell me a joke", "who won the game?")
- "follow_up": Short context-dependent messages that refer to the previous \
exchange ("tell me more", "explain that", "why?", "what about X?")
- "hr_question": Questions about HR policies, benefits, leave, compensation, \
remote work, or any workplace-related topic

Conversation history (most recent first):
{history}

User message: {message}

Classification (exactly one word from the list above):"""

_REWRITE_TEMPLATE = """\
You are a query rewriter for an HR Q&A system. The user is asking a follow-up \
question that relies on context from the previous conversation.

Your task: Rewrite the follow-up into a **standalone question** that \
incorporates the necessary context so it can be understood and answered \
without seeing the conversation history.

Rules:
- Be specific — resolve all pronouns ("it", "that", "they") and vague \
references ("the policy", "those benefits").
- Preserve the user's original intent and wording as much as possible.
- Output ONLY the rewritten question — no explanations, no prefixes.

Conversation history (most recent first):
{history}

Follow-up message: {message}

Standalone question:"""


# ---------------------------------------------------------------------------
# Gemini service
# ---------------------------------------------------------------------------


class GeminiService:
    """Unified service for all Gemini AI interactions.

    This is the single entry point for:

    - **Text embeddings** (document ingestion + query embedding)
    - **Text generation** (answers, classifications, rewriting)
    - **Streaming generation** (real-time chat responses)

    Handles client initialisation, retry logic with exponential backoff,
    error normalisation, and async wrapping for the synchronous SDK.
    """

    # Model constants — the single source of truth for model names
    EMBEDDING_MODEL = "gemini-embedding-001"
    GENERATION_MODEL = "gemini-2.5-flash"

    # Retry configuration
    MAX_RETRIES = 3
    RETRYABLE_STATUSES: set[int] = {429, 500, 502, 503}

    # Delay between successful embedding batches (rate-limit safety)
    _BATCH_COOLDOWN_SECONDS = 2.0

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, api_key: str) -> None:
        """Initialise the Gemini service.

        Args:
            api_key: Google Gemini API key.
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)

    # ------------------------------------------------------------------
    # Private — status code extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        """Try to extract an HTTP status code from an exception's string
        representation.

        The ``google-genai`` SDK wraps HTTP errors in exception classes
        whose ``str()`` output includes the status code.  This method
        uses regex to pull it out so we can decide whether to retry.
        """
        error_str = str(exc)
        # Look for patterns like "status: 429" or "429 Resource Exhausted"
        match = re.search(r"\bstatus[:\s]*(\d{3})\b", error_str, re.IGNORECASE)
        if match:
            return int(match.group(1))
        # Also try bare 3-digit codes near "error" / "failed"
        match = re.search(r"\b(4\d\d|5\d\d)\b", error_str)
        if match:
            return int(match.group(1))
        return None

    # ------------------------------------------------------------------
    # Private — generic retry wrapper
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self,
        sync_callable: Any,
        error_type: type[GeminiAPIError],
        context: str = "",
    ) -> Any:
        """Execute *sync_callable* with exponential-backoff retry logic.

        The callable is a **synchronous** closure that performs a single
        Gemini SDK call.  It is offloaded to a thread via
        ``asyncio.to_thread()`` so the event loop stays free.

        Args:
            sync_callable: A zero-argument synchronous function that
                performs the Gemini API call and returns the result.
            error_type: The ``GeminiAPIError`` subclass to raise if all
                retries are exhausted.
            context: Human-readable label for log messages (e.g.
                ``"embedding 12 texts"``).

        Returns:
            The return value of *sync_callable* on success.

        Raises:
            GeminiConfigurationError: On 401/403 (bad API key, no access).
            GeminiRateLimitError: On 429 after all retries exhausted.
            *error_type*: On all other failures after all retries exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = await asyncio.to_thread(sync_callable)

                # Log success after a retry
                if attempt > 1:
                    logger.info(
                        "Gemini API call succeeded after %d retry(ies)%s",
                        attempt - 1,
                        f" [{context}]" if context else "",
                    )
                return result

            except Exception as exc:
                last_exc = exc
                status_code = self._extract_status_code(exc)

                # Fail-fast: non-retryable client errors
                if status_code in {401, 403}:
                    logger.error(
                        "Gemini configuration error (status %d)%s: %s",
                        status_code,
                        f" [{context}]" if context else "",
                        exc,
                    )
                    raise GeminiConfigurationError(
                        message=str(exc),
                        status_code=status_code,
                        original_error=exc,
                    ) from exc

                if status_code is not None and status_code < 500:
                    # 400, 404, etc. — client error, don't retry
                    logger.error(
                        "Gemini client error (status %d)%s: %s",
                        status_code,
                        f" [{context}]" if context else "",
                        exc,
                    )
                    raise GeminiAPIError(
                        message=str(exc),
                        status_code=status_code,
                        original_error=exc,
                    ) from exc

                # Retryable or unknown status — apply backoff
                if attempt < self.MAX_RETRIES:
                    wait = 2 ** (attempt - 1)  # 1s, 2s, 4s
                    logger.warning(
                        "Gemini API retry %d/%d%s: %s. Waiting %ds...",
                        attempt,
                        self.MAX_RETRIES,
                        f" [{context}]" if context else "",
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Gemini API failed after %d attempts%s: %s",
                        self.MAX_RETRIES,
                        f" [{context}]" if context else "",
                        exc,
                    )

        # All retries exhausted
        if last_exc is not None:
            status_code = self._extract_status_code(last_exc)
            if status_code == 429:
                raise GeminiRateLimitError(
                    message=str(last_exc),
                    status_code=status_code,
                    original_error=last_exc,
                ) from last_exc

        raise error_type(
            message=str(last_exc) if last_exc else "Unknown error",
            status_code=(
                self._extract_status_code(last_exc) if last_exc else None
            ),
            original_error=last_exc,
        )

    # ------------------------------------------------------------------
    # Private — single embedding batch
    # ------------------------------------------------------------------

    async def _embed_batch_with_retry(
        self,
        texts: list[str],
        task_type: str,
        output_dimensionality: int,
    ) -> list[list[float]]:
        """Call the embedding API for a single batch with retry logic.

        Args:
            texts: Batch of texts (max ~50 recommended by Gemini).
            task_type: ``"RETRIEVAL_DOCUMENT"`` or ``"RETRIEVAL_QUERY"``.
            output_dimensionality: Vector dimensions (default 768).

        Returns:
            One embedding vector per input text.
        """
        config = types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=output_dimensionality,
        )

        def _do_embed() -> list[list[float]]:
            result = self.client.models.embed_content(
                model=self.EMBEDDING_MODEL,
                contents=texts,
                config=config,
            )
            return [emb.values for emb in result.embeddings]

        return await self._call_with_retry(
            _do_embed,
            GeminiEmbeddingError,
            context=f"embedding {len(texts)} texts, task={task_type}",
        )

    # ------------------------------------------------------------------
    # Public — embeddings
    # ------------------------------------------------------------------

    async def embed_texts(
        self,
        texts: list[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
        batch_size: int = 50,
        output_dimensionality: int = 768,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Splits *texts* into batches (max *batch_size* per API call) and
        calls the Gemini embedding endpoint with retry logic.

        Args:
            texts: List of text strings to embed.
            task_type: ``"RETRIEVAL_DOCUMENT"`` (ingestion) or
                ``"RETRIEVAL_QUERY"`` (search).
            batch_size: Max texts per API call (default 50).
            output_dimensionality: Embedding dimensions (default 768).

        Returns:
            One ``list[float]`` embedding vector per input text, in order.

        Raises:
            ValueError: If *texts* is not a list.
            GeminiEmbeddingError: If embedding fails after all retries.
        """
        if not isinstance(texts, list):
            raise ValueError(f"texts must be a list, got {type(texts).__name__}")

        if not texts:
            return []

        start_time = time.time()
        all_embeddings: list[list[float]] = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for batch_num, i in enumerate(range(0, len(texts), batch_size)):
            batch = texts[i : i + batch_size]

            batch_embeddings = await self._embed_batch_with_retry(
                batch,
                task_type=task_type,
                output_dimensionality=output_dimensionality,
            )
            all_embeddings.extend(batch_embeddings)

            # Small delay between batches to avoid rate limiting
            if batch_num < total_batches - 1:
                await asyncio.sleep(self._BATCH_COOLDOWN_SECONDS)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "Gemini embedding: %d texts, model=%s, task=%s, dims=%d, time=%.0fms",
            len(texts),
            self.EMBEDDING_MODEL,
            task_type,
            output_dimensionality,
            elapsed_ms,
        )

        return all_embeddings

    async def embed_single(
        self,
        text: str,
        task_type: str = "RETRIEVAL_QUERY",
    ) -> list[float]:
        """Generate embedding for a single text.

        Convenience wrapper around :meth:`embed_texts`.

        Args:
            text: Single text string.
            task_type: ``"RETRIEVAL_DOCUMENT"`` or ``"RETRIEVAL_QUERY"``
                (default: query mode for search).

        Returns:
            Single embedding vector (``list[float]``).
        """
        results = await self.embed_texts([text], task_type=task_type)
        return results[0]

    # ------------------------------------------------------------------
    # Private — safety settings builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_safety_settings() -> list[types.SafetySetting]:
        """Return safety settings with all harm categories set to BLOCK_NONE."""
        return [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]

    # ------------------------------------------------------------------
    # Public — text generation (non-streaming)
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_output_tokens: int = 1024,
        top_p: float = 0.95,
    ) -> str:
        """Generate text (non-streaming).

        Args:
            prompt: Full prompt string.
            temperature: Creativity control, 0.0–1.0 (default 0.3).
            max_output_tokens: Max tokens in the response (default 1024).
            top_p: Nucleus sampling parameter (default 0.95).

        Returns:
            Generated text string.

        Raises:
            ValueError: If *prompt* is empty.
            GeminiGenerationError: If generation fails after all retries.
        """
        if not prompt:
            raise ValueError("prompt is required")

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            top_p=top_p,
            safety_settings=self._build_safety_settings(),
        )

        logger.debug(
            "Gemini request: model=%s, temp=%.1f, max_tokens=%d, prompt_length=%d",
            self.GENERATION_MODEL,
            temperature,
            max_output_tokens,
            len(prompt),
        )

        def _do_generate() -> str:
            response = self.client.models.generate_content(
                model=self.GENERATION_MODEL,
                contents=prompt,
                config=config,
            )

            # Log token usage at debug level when available
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                logger.debug(
                    "Gemini token usage: prompt=%d, candidates=%d, total=%d",
                    getattr(response.usage_metadata, "prompt_token_count", 0),
                    getattr(
                        response.usage_metadata, "candidates_token_count", 0
                    ),
                    getattr(response.usage_metadata, "total_token_count", 0),
                )

            text = response.text
            if not text:
                raise RuntimeError(
                    "Gemini returned an empty response (possibly blocked "
                    "by safety filter or no candidates generated)"
                )
            return text

        return await self._call_with_retry(
            _do_generate,
            GeminiGenerationError,
            context="text generation",
        )

    # ------------------------------------------------------------------
    # Public — streaming generation
    # ------------------------------------------------------------------

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_output_tokens: int = 1024,
        top_p: float = 0.95,
    ) -> AsyncIterator[str]:
        """Generate text with token-by-token streaming.

        Uses an ``asyncio.Queue`` + ``loop.run_in_executor`` pattern to
        bridge the synchronous streaming SDK into an async generator.

        Args:
            prompt: Full prompt string.
            temperature: Creativity control, 0.0–1.0 (default 0.3).
            max_output_tokens: Max tokens in the response (default 1024).
            top_p: Nucleus sampling parameter (default 0.95).

        Yields:
            Text tokens as they arrive from the Gemini API.
        """
        if not prompt:
            raise ValueError("prompt is required")

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            top_p=top_p,
            safety_settings=self._build_safety_settings(),
        )

        queue: asyncio.Queue[str | None] = asyncio.Queue()
        stream_error: list[Exception] = []  # capture error from thread

        def _stream_runner() -> None:
            """Run the synchronous stream in a thread, pushing tokens into
            the queue.  A ``None`` sentinel signals completion or error."""
            try:
                for chunk in self.client.models.generate_content_stream(
                    model=self.GENERATION_MODEL,
                    contents=prompt,
                    config=config,
                ):
                    if chunk.text:
                        queue.put_nowait(chunk.text)
            except Exception as exc:
                logger.exception("Gemini streaming error — stream truncated")
                stream_error.append(exc)
            finally:
                queue.put_nowait(None)  # sentinel

        # Start the stream in a background thread — don't await the future
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _stream_runner)

        # Yield tokens as they arrive
        while True:
            token = await queue.get()
            if token is None:
                break
            yield token

        # If the stream failed, raise the error so callers can handle it
        if stream_error:
            raise stream_error[0]

    # ------------------------------------------------------------------
    # Public — function / tool calling (Feature 16)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tool_declarations(tools: list[dict]) -> list[types.Tool]:
        """Convert internal tool dicts into Google ``types.Tool`` objects.

        Each tool dict should have:
          - ``name`` (str) — unique function name
          - ``description`` (str) — what the function does
          - ``parameters`` (dict) — JSON Schema for the function's arguments

        Returns a list containing a single ``types.Tool`` wrapping all
        function declarations (Gemini's contract: one ``Tool`` per
        ``tools`` entry; each ``Tool`` can hold multiple declarations).
        """
        declarations: list[types.FunctionDeclaration] = []
        for tool in tools:
            declarations.append(
                types.FunctionDeclaration(
                    name=tool["name"],
                    description=tool["description"],
                    parameters=tool.get("parameters"),
                )
            )
        return [types.Tool(function_declarations=declarations)]

    async def generate_with_tools(
        self,
        prompt: str,
        tools: list[dict],
        temperature: float = 0.3,
        max_output_tokens: int = 1024,
    ) -> dict:
        """Call Gemini with function declarations. Returns text OR function_calls.

        This is the FIRST call in a manual function-calling loop — Gemini
        either responds with plain text (no tool needed) or with
        ``function_calls`` that the caller must execute.

        Args:
            prompt: Full prompt string (system + user).
            tools: List of tool dicts (name, description, parameters).
            temperature: Creativity control (default 0.3).
            max_output_tokens: Max tokens (default 1024).

        Returns:
            A dict with:
            - ``{"type": "text", "content": "..."}`` when Gemini answers directly.
            - ``{"type": "function_calls", "calls": [{"name": ..., "args": {...}, "id": ...}]}``
              when Gemini wants to call one or more functions.
        """
        if not prompt:
            raise ValueError("prompt is required")

        tool_objs = self._build_tool_declarations(tools)
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            safety_settings=self._build_safety_settings(),
            tools=tool_objs,
        )

        def _do_generate() -> dict:
            response = self.client.models.generate_content(
                model=self.GENERATION_MODEL,
                contents=prompt,
                config=config,
            )

            # Check for function calls first
            if hasattr(response, "function_calls") and response.function_calls:
                calls = []
                for fc in response.function_calls:
                    calls.append({
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                        "id": fc.id if hasattr(fc, "id") else None,
                    })
                logger.info(
                    "Gemini returned %d function call(s): %s",
                    len(calls),
                    ", ".join(c["name"] for c in calls),
                )
                return {"type": "function_calls", "calls": calls}

            # Plain text response
            text = response.text or ""
            return {"type": "text", "content": text}

        return await self._call_with_retry(
            _do_generate,
            GeminiGenerationError,
            context="generation with tools",
        )

    async def generate_with_tools_and_history(
        self,
        prompt: str,
        function_calls: list[dict],
        function_results: list[dict],
        tools: list[dict],
        temperature: float = 0.3,
        max_output_tokens: int = 1024,
    ) -> dict:
        """Continue a conversation after function calls were executed.

        Sends the full history back to Gemini: original user prompt →
        model's function calls → function results.  Gemini can either
        respond with text or request more function calls (multi-round).

        Args:
            prompt: The ORIGINAL user prompt that started the conversation.
            function_calls: List of ``{"name": ..., "args": ..., "id": ...}``
                from the previous ``generate_with_tools`` response.
            function_results: List of ``{"tool_name": ..., "data": ..., "error": ...}``
                from executing the functions.
            tools: Same tool declarations as the first call.
            temperature: Creativity control.
            max_output_tokens: Max tokens.

        Returns:
            Same dict shape as :meth:`generate_with_tools`.
        """
        tool_objs = self._build_tool_declarations(tools)
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            safety_settings=self._build_safety_settings(),
            tools=tool_objs,
        )

        def _do_generate() -> dict:
            # Build the contents list with full conversation history
            contents: list[types.Content] = []

            # 1. User's original message
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)],
                )
            )

            # 2. Model's function call(s)
            model_parts: list[types.Part] = []
            for fc in function_calls:
                fc_id = fc.get("id")
                fc_name = fc["name"]
                fc_args = fc.get("args", {})
                model_parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            id=fc_id,
                            name=fc_name,
                            args=fc_args,
                        )
                    )
                )
            contents.append(
                types.Content(role="model", parts=model_parts)
            )

            # 3. Function results (as user role with function_response parts)
            result_parts: list[types.Part] = []
            for i, fr in enumerate(function_results):
                fc = function_calls[i] if i < len(function_calls) else {}
                fc_name = fc.get("name", fr.get("tool_name", "unknown"))
                fc_id = fc.get("id")
                # Build response payload
                response_data = {
                    "tool_name": fr.get("tool_name", fc_name),
                    "data": fr.get("data", {}),
                    "error": fr.get("error"),
                }
                result_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=fc_id,
                            name=fc_name,
                            response=response_data,
                        )
                    )
                )
            contents.append(
                types.Content(role="user", parts=result_parts)
            )

            response = self.client.models.generate_content(
                model=self.GENERATION_MODEL,
                contents=contents,
                config=config,
            )

            # Check for function calls (model could request more tools)
            if hasattr(response, "function_calls") and response.function_calls:
                calls = []
                for fc in response.function_calls:
                    calls.append({
                        "name": fc.name,
                        "args": dict(fc.args) if fc.args else {},
                        "id": fc.id if hasattr(fc, "id") else None,
                    })
                return {"type": "function_calls", "calls": calls}

            # Final text response
            text = response.text or ""
            return {"type": "text", "content": text}

        return await self._call_with_retry(
            _do_generate,
            GeminiGenerationError,
            context="generation with tools (history)",
        )

    async def generate_stream_with_tool_results(
        self,
        prompt: str,
        temperature: float = 0.3,
        max_output_tokens: int = 1024,
        top_p: float = 0.95,
    ) -> AsyncIterator[str]:
        """Stream generation after all tool results have been gathered.

        This is a convenience wrapper around :meth:`generate_stream` that
        is called AFTER the function-calling loop completes.  The *prompt*
        should already include the formatted tool results.

        Args:
            prompt: Full prompt with tool results injected.
            temperature: Creativity control.
            max_output_tokens: Max tokens.
            top_p: Nucleus sampling.

        Yields:
            Text tokens as they arrive from Gemini.
        """
        async for token in self.generate_stream(
            prompt=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            top_p=top_p,
        ):
            yield token

    # ------------------------------------------------------------------
    # Public — classification
    # ------------------------------------------------------------------

    async def classify(
        self,
        message: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Classify a user message into one of 5 categories.

        Uses a structured prompt with few-shot guidance sent to the
        generation model at low temperature for deterministic output.

        Args:
            message: The user's message text.
            conversation_history: Optional list of recent messages
                (each with ``"role"`` and ``"content"`` keys) for context.

        Returns:
            One of: ``"greeting_only"``, ``"bot_question"``,
            ``"out_of_domain"``, ``"follow_up"``, ``"hr_question"``.

            Falls back to ``"out_of_domain"`` if the model returns an
            unrecognised value.
        """
        history = _format_history(conversation_history or [])
        prompt = _CLASSIFICATION_TEMPLATE.format(
            history=history,
            message=message,
        )

        response = await self.generate(
            prompt=prompt,
            temperature=0.1,
            max_output_tokens=50,
            top_p=0.9,
        )

        classification = response.strip().lower()

        valid_categories = {
            "greeting_only",
            "bot_question",
            "out_of_domain",
            "follow_up",
            "hr_question",
        }

        if classification not in valid_categories:
            logger.warning(
                "Unexpected classification '%s' for message: %s. "
                "Defaulting to 'hr_question'.",
                classification,
                message[:100],
            )
            return "hr_question"

        return classification

    # ------------------------------------------------------------------
    # Public — query rewriting
    # ------------------------------------------------------------------

    async def rewrite_query(
        self,
        follow_up_message: str,
        conversation_history: list[dict] | None = None,
    ) -> str:
        """Rewrite a context-dependent follow-up into a standalone question.

        Resolves pronouns ("it", "that"), vague references ("the policy"),
        and other context-dependent language so the question can be
        understood and vector-searched independently.

        Args:
            follow_up_message: The user's follow-up message.
            conversation_history: Recent conversation for context
                (each with ``"role"`` and ``"content"`` keys).

        Returns:
            A standalone question string.  Falls back to the original
            *follow_up_message* if the model returns an empty response.
        """
        history = _format_history(conversation_history or [])
        prompt = _REWRITE_TEMPLATE.format(
            history=history,
            message=follow_up_message,
        )

        rewritten = await self.generate(
            prompt=prompt,
            temperature=0.2,
            max_output_tokens=200,
        )

        rewritten = rewritten.strip()

        if not rewritten:
            logger.warning(
                "Query rewriting returned empty — falling back to original"
            )
            return follow_up_message

        return rewritten


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _format_history(history: list[dict]) -> str:
    """Format a conversation history list into a readable string.

    Args:
        history: List of dicts with ``"role"`` and ``"content"`` keys.

    Returns:
        Formatted string like ``"user: Hello\\nassistant: Hi there"``,
        or ``"(no history)"`` if empty.
    """
    if not history:
        return "(no history)"

    lines: list[str] = []
    for msg in history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)
