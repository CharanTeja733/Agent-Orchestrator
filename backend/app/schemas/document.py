"""Document ingestion schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Existing (kept for backward compatibility)
# ---------------------------------------------------------------------------


class DocumentChunk(BaseModel):
    content: str
    source: str
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_index: int
    access_level: str = "all"


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


class DocumentUploadResponse(BaseModel):
    message: str
    source: str
    chunks_created: int
    total_chars: int
    access_level: str


class BulkUploadResult(BaseModel):
    source: str
    chunks_created: int
    status: str
    error: Optional[str] = None


class BulkUploadResponse(BaseModel):
    message: str
    results: list[BulkUploadResult]
    total_chunks: int


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class DocumentSummary(BaseModel):
    source: str
    chunk_count: int
    access_level: str
    ingested_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]
    total_documents: int
    total_chunks: int


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


class ChunkDetail(BaseModel):
    chunk_index: int
    content: str
    page: Optional[int] = None
    section: Optional[str] = None


class DocumentDetailResponse(BaseModel):
    source: str
    access_level: str
    chunks: list[ChunkDetail]
    total_chunks: int


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class DocumentDeleteResponse(BaseModel):
    message: str
    source: str
    chunks_deleted: int


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class AccessLevelDistribution(BaseModel):
    all: int = 0
    manager: int = 0
    hr_admin: int = 0


class DocumentStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_characters: int
    access_level_distribution: AccessLevelDistribution
    largest_document: Optional[str] = None
    last_ingested: Optional[datetime] = None
