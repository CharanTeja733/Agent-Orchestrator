"""Request and response schemas for the RAG query endpoints (Feature 8).

Reference: ``.claude/specs/08-rag-pipeline.md`` Section 4.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """Incoming query for the RAG pipeline."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's question or message",
    )
    session_id: Optional[UUID] = Field(
        default=None,
        description="Existing session ID for conversation continuity; "
        "a new session is created when omitted",
    )


# ---------------------------------------------------------------------------
# Shared detail objects
# ---------------------------------------------------------------------------


class SourceDetail(BaseModel):
    """A cited source returned with every assistant response."""

    document: str = Field(..., description="Document filename or title")
    page: Optional[int] = Field(default=None, description="Page number if available")
    section: Optional[str] = Field(default=None, description="Section heading if available")
    excerpt: str = Field(..., description="Relevant excerpt from the source (truncated)")


class RetrievedChunkDetail(BaseModel):
    """Detailed chunk metadata returned by the test/debug endpoint."""

    chunk_id: UUID = Field(..., description="Unique chunk identifier")
    content: str = Field(..., description="Full chunk text")
    source: str = Field(..., description="Source document name")
    page: Optional[int] = Field(default=None)
    section: Optional[str] = Field(default=None)
    score: float = Field(..., description="Cosine similarity score")
    confidence: str = Field(..., description="Per-chunk confidence label")


class PipelineSteps(BaseModel):
    """Per-step timing breakdown for performance monitoring."""

    classification_ms: Optional[float] = Field(default=None)
    rewriting_ms: Optional[float] = Field(default=None)
    retrieval_ms: Optional[float] = Field(default=None)
    generation_ms: Optional[float] = Field(default=None)
    storage_ms: Optional[float] = Field(default=None)


# ---------------------------------------------------------------------------
# Test / debug endpoint response (spec §4.B)
# ---------------------------------------------------------------------------


class QueryTestResponse(BaseModel):
    """Complete, non-streaming debug response from the RAG pipeline."""

    query: str = Field(..., description="Original user query")
    rewritten_query: Optional[str] = Field(
        default=None,
        description="Rewritten standalone question (follow-ups only)",
    )
    classification: str = Field(..., description="Classifier category")
    classification_confidence: float = Field(..., description="Classifier confidence 0-1")
    retrieved_chunks: list[RetrievedChunkDetail] = Field(
        default_factory=list, description="Chunks retrieved by vector search"
    )
    retrieval_count: int = Field(
        default=0, description="Number of chunks above the minimum score threshold"
    )
    overall_confidence: str = Field(
        default="no_match", description="Pipeline confidence tier"
    )
    answer: str = Field(..., description="Full generated or fallback answer")
    sources: list[SourceDetail] = Field(
        default_factory=list, description="Cited sources"
    )
    tokens_used: int = Field(default=0, description="Estimated tokens consumed")
    processing_time_ms: float = Field(
        default=0.0, description="Total pipeline processing time (ms)"
    )
    pipeline_steps: PipelineSteps = Field(
        default_factory=PipelineSteps, description="Per-step timing breakdown"
    )


# ---------------------------------------------------------------------------
# Health-check response (spec §4.C)
# ---------------------------------------------------------------------------


class QueryHealthResponse(BaseModel):
    """Health status of every component the RAG pipeline depends on."""

    status: str = Field(..., description="Overall health: healthy | degraded")
    components: dict = Field(
        ...,
        description="Per-component status: classifier, search, gemini, database",
    )
    documents_indexed: int = Field(
        default=0, description="Total document chunks in the vector store"
    )
    active_sessions: int = Field(
        default=0, description="Sessions active in the last hour"
    )
    agent: str | None = Field(
        default=None, description="Agent name (e.g. 'hr', 'it')"
    )
