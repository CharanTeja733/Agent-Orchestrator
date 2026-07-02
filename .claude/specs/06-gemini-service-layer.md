# Feature 6: Gemini Service Layer

## 1. Overview

Build a unified Gemini service layer that centralizes all interactions with Google Gemini models. This service provides a single interface for embeddings, text generation, classification, and query rewriting. All other features (search, classifier, RAG pipeline) will use this service instead of calling Gemini directly.

This establishes the **AI foundation** — a clean abstraction over Gemini that handles client initialization, error handling, retries, and model-specific configurations.

---

## 2. Depends on

- **Feature 1: Project Setup & Docker Environment** — services running
- **Feature 3: User Authentication** — not directly, but API key from config must work
- **Feature 4: Document Ingestion Pipeline** — embedder utility will be refactored to use this service
- **Feature 5: Vector Search Service** — embedder utility will be refactored to use this service

---

## 3. Routes

This is a service layer only — no new API routes.

---

## 4. Service Responsibilities

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    GEMINI SERVICE — SINGLE RESPONSIBILITY                            │
│                                                                                      │
│  This service is the ONLY place in the codebase that:                                │
│  • Imports from google.genai                                                         │
│  • Creates genai.Client instances                                                     │
│  • Knows model names and configurations                                              │
│  • Handles Gemini API errors and retries                                              │
│                                                                                      │
│  ALL other modules go through this service for any Gemini interaction.               │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                                                                              │    │
│  │  app/services/gemini.py                                                       │    │
│  │  ┌──────────────────────────────────────────────────────────────────────┐    │    │
│  │  │  GeminiService                                                        │    │    │
│  │  │                                                                       │    │    │
│  │  │  • embed_texts(texts, task_type) → list[list[float]]                 │    │    │
│  │  │  • embed_single(text, task_type) → list[float]                       │    │    │
│  │  │  • generate(prompt, **config) → str                                  │    │    │
│  │  │  • generate_stream(prompt, **config) → AsyncIterator[str]            │    │    │
│  │  │  • classify(message, history) → str                                  │    │    │
│  │  │  • rewrite_query(follow_up, history) → str                           │    │    │
│  │  └──────────────────────────────────────────────────────────────────────┘    │    │
│  │                                                                              │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  Used by:                                                                             │
│  • app/utils/embedder.py  → refactored to call GeminiService.embed_texts()           │
│  • app/services/search.py → refactored to call GeminiService.embed_single()         │
│  • Feature 7: Query Classifier → calls GeminiService.classify()                      │
│  • Feature 8: RAG Pipeline → calls GeminiService.generate_stream()                   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Model Configurations

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    MODEL CONFIGURATIONS                                               │
│                                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  TASK              │ MODEL                    │ CONFIG                         │    │
│  ├────────────────────┼──────────────────────────┼────────────────────────────────┤    │
│  │  Embeddings        │ gemini-embedding-001     │ output_dimensionality=768      │    │
│  │  (Documents)       │                          │ task_type=RETRIEVAL_DOCUMENT   │    │
│  ├────────────────────┼──────────────────────────┼────────────────────────────────┤    │
│  │  Embeddings        │ gemini-embedding-001     │ output_dimensionality=768      │    │
│  │  (Queries)         │                          │ task_type=RETRIEVAL_QUERY      │    │
│  ├────────────────────┼──────────────────────────┼────────────────────────────────┤    │
│  │  Classification    │ gemini-2.5-flash         │ temperature=0.1                │    │
│  │                    │                          │ max_output_tokens=50           │    │
│  │                    │                          │ top_p=0.9                      │    │
│  ├────────────────────┼──────────────────────────┼────────────────────────────────┤    │
│  │  Query Rewriting   │ gemini-2.5-flash         │ temperature=0.2                │    │
│  │                    │                          │ max_output_tokens=200          │    │
│  ├────────────────────┼──────────────────────────┼────────────────────────────────┤    │
│  │  Answer Generation │ gemini-2.5-flash         │ temperature=0.3                │    │
│  │                    │                          │ max_output_tokens=1024         │    │
│  │                    │                          │ top_p=0.95                     │    │
│  ├────────────────────┼──────────────────────────┼────────────────────────────────┤    │
│  │  Greeting/Chitchat │ gemini-2.5-flash         │ temperature=0.5                │    │
│  │                    │                          │ max_output_tokens=200          │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  Retry Configuration:                                                                 │
│  • Max retries: 3                                                                     │
│  • Backoff: Exponential (1s, 2s, 4s)                                                  │
│  • Retryable errors: 429 (rate limit), 500, 502, 503                                  │
│  • Non-retryable: 400, 401, 403, 404                                                  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. New Folder Structure (This Feature Only)

```text
backend/app/
├── services/
│   └── gemini.py                 # 🟢 Gemini service (NEW)
├── core/
│   └── exceptions.py             # UPDATE — add Gemini-specific exceptions
└── utils/
    └── embedder.py               # REFACTOR — use GeminiService internally
```

---

## 7. Files to Create

### A. `app/services/gemini.py`

The central Gemini service class. This is the ONLY module that imports from `google.genai`.

#### Class: `GeminiService`

```python
from google import genai
from google.genai import types
import asyncio
import time
import logging
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)


class GeminiService:
    """
    Unified service for all Gemini AI interactions.
    
    This is the single entry point for:
    - Text embeddings (document ingestion + query embedding)
    - Text generation (answers, classifications, rewriting)
    - Streaming generation (real-time chat responses)
    
    Handles:
    - Client initialization
    - Retry logic with exponential backoff
    - Error normalization
    - Async wrapping for sync SDK
    """
    
    # Model constants
    EMBEDDING_MODEL = "gemini-embedding-001"
    GENERATION_MODEL = "gemini-2.5-flash"
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRYABLE_STATUSES = {429, 500, 502, 503}
    
    def __init__(self, api_key: str):
        """
        Initialize the Gemini service.
        
        Args:
            api_key: Google Gemini API key
        """
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)
```

#### Methods:

##### `embed_texts(texts, task_type, batch_size, output_dimensionality) -> list[list[float]]`

```
Generate embeddings for multiple texts.

Args:
    texts: List of text strings to embed
    task_type: "RETRIEVAL_DOCUMENT" or "RETRIEVAL_QUERY"
    batch_size: Max texts per API call (default 50)
    output_dimensionality: Embedding dimensions (default 768)

Returns:
    List of embedding vectors (each is list[float] of length output_dimensionality)

Raises:
    GeminiAPIError: If embedding fails after all retries

Implementation:
    - Split texts into batches of batch_size
    - For each batch, call _embed_batch_with_retry()
    - Flatten results
    - Log batch progress
```

##### `embed_single(text, task_type) -> list[float]`

```
Generate embedding for a single text.

Args:
    text: Single text string
    task_type: "RETRIEVAL_DOCUMENT" or "RETRIEVAL_QUERY"

Returns:
    Single embedding vector (list[float])

Convenience wrapper around embed_texts().
```

##### `async generate(prompt, temperature, max_output_tokens, top_p) -> str`

```
Generate text (non-streaming).

Args:
    prompt: Full prompt string
    temperature: 0.0-1.0 (default 0.3)
    max_output_tokens: Max tokens in response (default 1024)
    top_p: Nucleus sampling parameter (default 0.95)

Returns:
    Generated text string

Raises:
    GeminiAPIError: If generation fails after all retries

Implementation:
    - Wrap sync client.models.generate_content() in asyncio.to_thread()
    - Apply retry logic
    - Return response.text
    - Log token usage if available
```

##### `async generate_stream(prompt, temperature, max_output_tokens, top_p) -> AsyncIterator[str]`

```
Generate text with token-by-token streaming.

Args:
    prompt: Full prompt string
    temperature: 0.0-1.0 (default 0.3)
    max_output_tokens: Max tokens in response (default 1024)
    top_p: Nucleus sampling parameter (default 0.95)

Returns:
    Async iterator yielding text tokens

Implementation:
    - Call client.models.generate_content_stream()
    - Yield each chunk.text as it arrives
    - Use asyncio.sleep(0) to yield control to event loop
    - Handle stream interruption gracefully
```

##### `async classify(message, conversation_history) -> str`

```
Classify a user message into one of 5 categories.

Args:
    message: User's message text
    conversation_history: List of recent messages for context

Returns:
    One of: "greeting_only", "bot_question", "out_of_domain", 
            "follow_up", "hr_question"

Implementation:
    - Build classification prompt (see Feature 7)
    - Call generate() with temperature=0.1, max_output_tokens=50
    - Parse and validate response
    - Return classification string
```

##### `async rewrite_query(follow_up_message, conversation_history) -> str`

```
Rewrite a context-dependent follow-up into a standalone question.

Args:
    follow_up_message: The user's follow-up message
    conversation_history: Recent conversation for context

Returns:
    Standalone question string incorporating all necessary context

Implementation:
    - Build rewriting prompt
    - Call generate() with temperature=0.2, max_output_tokens=200
    - Return rewritten query
```

#### Private Methods:

##### `_embed_batch_with_retry(texts, task_type, output_dimensionality) -> list[list[float]]`

```
Internal: Call embedding API with retry logic.

Args:
    texts: Batch of texts (max 50)
    task_type: RETRIEVAL_DOCUMENT or RETRIEVAL_QUERY
    output_dimensionality: Vector dimensions

Returns:
    List of embedding vectors

Implementation:
    - Create EmbedContentConfig
    - Call client.models.embed_content() in asyncio.to_thread()
    - On failure, check retryable status
    - Retry with exponential backoff
    - Extract embeddings from result.embeddings[i].values
    - Raise GeminiAPIError on final failure
```

##### `_retry_with_backoff(func, *args, **kwargs) -> Any`

```
Generic retry wrapper with exponential backoff.

Args:
    func: Async function to retry
    *args, **kwargs: Passed to func

Returns:
    Result from successful func call

Raises:
    GeminiAPIError: After exhausting all retries

Implementation:
    - Try calling func up to MAX_RETRIES times
    - On retryable error: wait (2^attempt) seconds, then retry
    - On non-retryable error: raise immediately
    - Log each retry attempt
    - Raise GeminiAPIError with original error details after final attempt
```

---

### B. `app/core/exceptions.py` — Add Gemini exceptions

```python
class GeminiAPIError(Exception):
    """Base exception for Gemini API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, original_error: Optional[Exception] = None):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        super().__init__(self.message)


class GeminiRateLimitError(GeminiAPIError):
    """Raised when Gemini API rate limit is exceeded."""
    pass


class GeminiEmbeddingError(GeminiAPIError):
    """Raised when embedding generation fails."""
    pass


class GeminiGenerationError(GeminiAPIError):
    """Raised when text generation fails."""
    pass


class GeminiConfigurationError(GeminiAPIError):
    """Raised when Gemini is misconfigured (bad API key, etc.)."""
    pass
```

---

## 8. Changes to Existing Files

### A. `app/utils/embedder.py` — REFACTOR

Replace direct Gemini SDK calls with `GeminiService`:

```python
"""
Embedding utility functions.
Now delegates to GeminiService for all Gemini interactions.
"""

from app.services.gemini import GeminiService


async def embed_texts(
    texts: list[str],
    api_key: str,
    task_type: str = "RETRIEVAL_DOCUMENT"
) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.
    Delegates to GeminiService.
    """
    service = GeminiService(api_key)
    return await service.embed_texts(texts=texts, task_type=task_type)


async def embed_single(
    text: str,
    api_key: str,
    task_type: str = "RETRIEVAL_QUERY"
) -> list[float]:
    """
    Generate embedding for a single text.
    Delegates to GeminiService.
    """
    service = GeminiService(api_key)
    return await service.embed_single(text=text, task_type=task_type)
```

### B. `app/services/search.py` — REFACTOR

Update `SearchService.__init__()` and `search()` to use `GeminiService`:

```python
# In __init__:
from app.services.gemini import GeminiService
self.gemini_service = GeminiService(gemini_api_key)

# In search():
# Replace: await embed_single(query, self.gemini_api_key, ...)
# With: await self.gemini_service.embed_single(query, task_type="RETRIEVAL_QUERY")
```

### C. `app/services/ingestion.py` — REFACTOR (from Feature 4)

Update `IngestionService` to use `GeminiService`:

```python
# In __init__:
from app.services.gemini import GeminiService
self.gemini_service = GeminiService(gemini_api_key)

# In ingest_document():
# Replace embed_texts() calls with self.gemini_service.embed_texts()
```

---

## 9. Files to Create

```
backend/app/services/gemini.py
```

---

## 10. Files to Change

```
backend/app/core/exceptions.py      (add Gemini exceptions)
backend/app/utils/embedder.py       (refactor to use GeminiService)
backend/app/services/search.py      (refactor to use GeminiService)
backend/app/services/ingestion.py   (refactor to use GeminiService)
```

---

## 11. Dependencies

All in `requirements.txt`:
- `google-genai>=1.0.0` — Gemini SDK (new, updated)

---

## 12. Rules for Implementation

- **Single source of truth**: `GeminiService` is the ONLY place that imports from `google.genai`
- **No direct SDK usage elsewhere**: All other modules go through `GeminiService` or the refactored `embedder.py` utilities
- **Sync SDK, async service**: All SDK calls wrapped in `asyncio.to_thread()`
- **Retry on transient errors**: 429, 500, 502, 503 get up to 3 retries
- **Fail fast on client errors**: 400, 401, 403, 404 raise immediately
- **Exponential backoff**: Wait 1s, then 2s, then 4s between retries
- **Structured logging**: Log model, task_type, tokens used, latency for every call
- **Custom exceptions**: Raise specific GeminiAPIError subclasses, not generic exceptions
- **No hardcoded model names**: Use class constants (EMBEDDING_MODEL, GENERATION_MODEL)
- **Default configs**: Each method has sensible defaults matching the model configuration table
- **API key from constructor**: Service initialized once with API key, no need to pass it per call

---

## 13. Gemini SDK Usage Reference

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    GEMINI SDK USAGE (Inside GeminiService ONLY)                      │
│                                                                                      │
│  Embeddings:                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  from google import genai                                                    │    │
│  │  from google.genai import types                                              │    │
│  │                                                                              │    │
│  │  client = genai.Client(api_key="...")                                        │    │
│  │                                                                              │    │
│  │  result = client.models.embed_content(                                        │    │
│  │      model="gemini-embedding-001",                                           │    │
│  │      contents=["text1", "text2"],                                            │    │
│  │      config=types.EmbedContentConfig(                                         │    │
│  │          task_type="RETRIEVAL_DOCUMENT",                                      │    │
│  │          output_dimensionality=768,                                           │    │
│  │      ),                                                                      │    │
│  │  )                                                                           │    │
│  │                                                                              │    │
│  │  # result.embeddings is a list; each has .values (list[float])               │    │
│  │  embeddings = [e.values for e in result.embeddings]                          │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  Text Generation:                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  response = client.models.generate_content(                                    │    │
│  │      model="gemini-2.5-flash",                                                │    │
│  │      contents="Your prompt here",                                             │    │
│  │      config=types.GenerateContentConfig(                                       │    │
│  │          temperature=0.3,                                                     │    │
│  │          max_output_tokens=1024,                                              │    │
│  │          top_p=0.95,                                                          │    │
│  │      ),                                                                      │    │
│  │  )                                                                           │    │
│  │  text = response.text                                                        │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  Streaming Generation:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  for chunk in client.models.generate_content_stream(                           │    │
│  │      model="gemini-2.5-flash",                                                │    │
│  │      contents="Your prompt here",                                             │    │
│  │      config=types.GenerateContentConfig(...),                                  │    │
│  │  ):                                                                          │    │
│  │      if chunk.text:                                                           │    │
│  │          yield chunk.text                                                     │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 14. Expected Behavior

### Service initialization:
1. `GeminiService(api_key="...")` creates a `genai.Client` instance
2. No API call is made on initialization — lazy, on first use

### Successful embedding:
1. `embed_texts(["text1", "text2"])` called
2. Single API call with both texts batched
3. Returns `[[0.012, -0.034, ...], [0.008, 0.021, ...]]`
4. Each inner list has exactly 768 floats

### Retry on failure:
1. First attempt fails with 503
2. Logs warning: "Gemini API error (attempt 1/3): 503 Service Unavailable. Retrying in 1s..."
3. Waits 1 second, retries
4. Succeeds on second attempt
5. Logs info: "Gemini API call succeeded after 1 retry"

### All retries exhausted:
1. Three attempts all fail
2. Raises `GeminiEmbeddingError` with details about all attempts
3. Original error available in `exception.original_error`

### Classification:
1. `classify("What is remote work policy?", history=[])` called
2. Internal prompt built, sent to `gemini-2.5-flash`
3. Returns `"hr_question"`

### Query rewriting:
1. `rewrite_query("explain that more", history=[...])` called
2. Internal prompt built with conversation context
3. Returns `"Explain the remote work policy in more detail"`

---

## 15. Error Handling Expectations

| Scenario | Exception | Behavior |
|----------|-----------|----------|
| Invalid API key | `GeminiConfigurationError` | Raised on first API call with 401/403 |
| Rate limit exceeded | `GeminiRateLimitError` | After 3 retries with backoff |
| Embedding fails | `GeminiEmbeddingError` | After 3 retries, includes original error |
| Generation fails | `GeminiGenerationError` | After 3 retries, includes original error |
| Network timeout | `GeminiAPIError` | After 3 retries |
| Invalid model name | `GeminiConfigurationError` | Raised immediately (400) |
| Empty texts list | `ValueError` | Raised immediately, no API call |

---

## 16. Logging Standards

```text
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                    LOGGING FORMAT                                                     │
│                                                                                      │
│  All GeminiService methods must log:                                                 │
│                                                                                      │
│  INFO level (success):                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  f"Gemini embedding: {len(texts)} texts, model={model}, task={task_type},   │    │
│  │     dims={dims}, time={elapsed_ms}ms"                                        │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  WARNING level (retry):                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  f"Gemini API retry {attempt}/{max_retries}: {error}. Waiting {wait}s..."    │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  ERROR level (final failure):                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  f"Gemini API failed after {max_retries} attempts: {error}"                  │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│  DEBUG level (request details):                                                      │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  f"Gemini request: model={model}, temp={temp}, max_tokens={max_tok},        │    │
│  │     prompt_length={len(prompt)}"                                             │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 17. Verification Steps

```python
# Test script (can be run manually or as part of testing)

import asyncio
from app.services.gemini import GeminiService
from app.config import settings

async def test_gemini_service():
    service = GeminiService(settings.GEMINI_API_KEY)
    
    # 1. Test embedding
    embedding = await service.embed_single("Test query", task_type="RETRIEVAL_QUERY")
    assert len(embedding) == 768, f"Expected 768 dimensions, got {len(embedding)}"
    print(f"✅ Embedding: {len(embedding)} dimensions")
    
    # 2. Test batch embedding
    embeddings = await service.embed_texts(
        ["Text 1", "Text 2", "Text 3"],
        task_type="RETRIEVAL_DOCUMENT"
    )
    assert len(embeddings) == 3
    assert all(len(e) == 768 for e in embeddings)
    print(f"✅ Batch embedding: {len(embeddings)} vectors of {len(embeddings[0])} dims")
    
    # 3. Test generation
    response = await service.generate(
        prompt="Say 'Hello, world!' and nothing else.",
        temperature=0.1,
        max_output_tokens=50
    )
    assert "Hello" in response
    print(f"✅ Generation: {response[:50]}...")
    
    # 4. Test classification
    classification = await service.classify(
        message="What is the remote work policy?",
        conversation_history=[]
    )
    assert classification in ["greeting_only", "bot_question", "out_of_domain", "follow_up", "hr_question"]
    print(f"✅ Classification: {classification}")
    
    # 5. Test query rewriting
    rewritten = await service.rewrite_query(
        follow_up_message="explain that more",
        conversation_history=[
            {"role": "user", "content": "What is remote work policy?"},
            {"role": "assistant", "content": "Our remote work policy allows..."}
        ]
    )
    assert len(rewritten) > 10
    print(f"✅ Query rewriting: {rewritten}")
    
    # 6. Test streaming
    print("✅ Streaming: ", end="")
    async for token in service.generate_stream(
        prompt="Count from 1 to 5:",
        temperature=0.1,
        max_output_tokens=50
    ):
        print(token, end="")
    print()

asyncio.run(test_gemini_service())
```

---

## 18. Definition of Done

- [ ] `GeminiService` class exists in `app/services/gemini.py`
- [ ] Service handles all Gemini interactions (embedding, generation, streaming)
- [ ] `embed_texts()` generates 768-dim vectors for multiple texts
- [ ] `embed_single()` generates single 768-dim vector
- [ ] `generate()` returns text response (non-streaming)
- [ ] `generate_stream()` yields tokens asynchronously
- [ ] `classify()` returns valid classification string
- [ ] `rewrite_query()` returns rewritten standalone question
- [ ] Retry logic works: 3 retries with exponential backoff
- [ ] Retryable errors (429, 500, 502, 503) are retried
- [ ] Non-retryable errors (400, 401, 403, 404) fail immediately
- [ ] Custom exceptions raised for different error types
- [ ] All SDK calls wrapped in `asyncio.to_thread()`
- [ ] Model names are class constants, not hardcoded strings
- [ ] Default configs match the model configuration table
- [ ] `app/utils/embedder.py` refactored to use `GeminiService`
- [ ] `app/services/search.py` refactored to use `GeminiService`
- [ ] `app/services/ingestion.py` refactored to use `GeminiService`
- [ ] No other module imports from `google.genai` directly
- [ ] Structured logging at INFO, WARNING, ERROR, DEBUG levels
- [ ] Verification script passes all 6 tests
- [ ] Gemini API key from config works with the new SDK
- [ ] `output_dimensionality=768` explicitly set for all embeddings