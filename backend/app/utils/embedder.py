"""Gemini embedding wrapper — uses the **new** ``google-genai`` SDK.

..  note::

    The old ``google-generativeai`` SDK was deprecated in November 2025.
    This module requires ``google-genai>=1.0.0``.
"""

from __future__ import annotations

import asyncio
import logging
import re

from google import genai
from google.genai import types

from app.core.exceptions import EmbeddingGenerationError

logger = logging.getLogger(__name__)

# Minimum delay between batches to stay under free-tier rate limits
_BATCH_COOLDOWN_SECONDS = 2.0


def _extract_retry_delay(error_message: str) -> float | None:
    """Try to parse a retry delay (in seconds) from a Gemini error message."""
    match = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)\s*s", error_message)
    if not match:
        # Try "Please retry in X.XXs" pattern
        match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_message)
    if match:
        return float(match.group(1))
    return None


async def embed_texts(
    texts: list[str],
    api_key: str,
    model: str = "gemini-embedding-001",
    task_type: str = "RETRIEVAL_DOCUMENT",
    output_dimensionality: int = 768,
    batch_size: int = 50,
    max_retries: int = 3,
) -> list[list[float]]:
    """Generate embeddings for *texts* using the Gemini embedding model.

    Parameters
    ----------
    texts : list[str]
        The texts to embed.
    api_key : str
        Google Gemini API key.
    model : str
        Embedding model name (default: ``"gemini-embedding-001"``).
    task_type : str
        Task type for the embedding model (default: ``"RETRIEVAL_DOCUMENT"``).
        Only supported by ``gemini-embedding-001``.
    output_dimensionality : int
        Truncate embeddings to this many dimensions (default: 768).
    batch_size : int
        Number of texts per API call (default: 50).
    max_retries : int
        Number of retries with exponential backoff (default: 3).

    Returns
    -------
    list[list[float]]
        One 768-dimensional embedding vector per input text.

    Raises
    ------
    EmbeddingGenerationError
        If all retries are exhausted.
    """
    if not texts:
        return []

    client = genai.Client(api_key=api_key)
    config = types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=output_dimensionality,
    )

    all_embeddings: list[list[float]] = []
    total_batches = (len(texts) + batch_size - 1) // batch_size

    for batch_num, i in enumerate(range(0, len(texts), batch_size)):
        batch = texts[i:i + batch_size]

        for attempt in range(max_retries):
            try:
                # The google-genai SDK is synchronous — offload to a thread
                result = await asyncio.to_thread(
                    client.models.embed_content,
                    model=model,
                    contents=batch,
                    config=config,
                )

                for emb in result.embeddings:
                    all_embeddings.append(emb.values)

                break  # batch succeeded

            except Exception as exc:
                error_str = str(exc)
                logger.warning(
                    "Embedding batch %d/%d, attempt %d/%d failed: %s",
                    batch_num + 1,
                    total_batches,
                    attempt + 1,
                    max_retries,
                    exc,
                )

                if attempt == max_retries - 1:
                    raise EmbeddingGenerationError(attempts=max_retries) from exc

                # Respect the API's suggested retry delay, or use our backoff
                retry_delay = _extract_retry_delay(error_str)
                if retry_delay is not None:
                    wait = max(retry_delay, 2 ** attempt)
                    logger.info("API suggests %.1fs retry — waiting %.1fs", retry_delay, wait)
                else:
                    wait = 2 ** attempt
                await asyncio.sleep(wait)

        # Small delay between successful batches to avoid rate limiting
        if batch_num < total_batches - 1:
            await asyncio.sleep(_BATCH_COOLDOWN_SECONDS)

    return all_embeddings


async def embed_single(
    text: str,
    api_key: str,
    model: str = "gemini-embedding-001",
) -> list[float]:
    """Convenience wrapper — embed a single text and return its vector."""
    results = await embed_texts([text], api_key, model=model)
    return results[0]
