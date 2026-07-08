"""Document ingestion endpoints — thin route handlers.

All endpoints require JWT authentication **and** the ``hr_admin`` role.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_admin_user
from app.database import get_db
from app.models import User
from app.schemas.document import (
    BulkUploadResponse,
    BulkUploadResult,
    DocumentDeleteResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentStatsResponse,
    DocumentUploadResponse,
)
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/documents", tags=["Documents"])

MAX_BULK_FILES = 5


# ---------------------------------------------------------------------------
# Dependency factory
# ---------------------------------------------------------------------------


def get_ingestion_service(
    db: AsyncSession = Depends(get_db),
) -> IngestionService:
    """Create an ingestion service wired with the current DB session."""
    return IngestionService(db=db, gemini_api_key=settings.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    access_level: str = Form("all"),
    agent_type: str = Form("hr"),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and ingest a single document (PDF/DOCX/TXT).

    Set *agent_type* to ``"it"`` to store in the IT knowledge base
    (default ``"hr"`` for the HR knowledge base).
    """
    collection_name = f"{agent_type}_documents"
    service = IngestionService(
        db=db,
        gemini_api_key=settings.GEMINI_API_KEY,
        collection_name=collection_name,
    )
    contents = await file.read()

    if len(contents) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum of {settings.MAX_FILE_SIZE_MB}MB",
        )

    result = await service.ingest_document(contents, file.filename, access_level)
    return DocumentUploadResponse(**result)


@router.post("/upload-bulk", status_code=status.HTTP_201_CREATED)
async def upload_documents_bulk(
    files: list[UploadFile] = File(...),
    access_level: str = Form("all"),
    agent_type: str = Form("hr"),
    _admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and ingest up to 5 documents at once.

    Set *agent_type* to ``"it"`` for IT knowledge base (default ``"hr"``).
    """
    collection_name = f"{agent_type}_documents"
    service = IngestionService(
        db=db,
        gemini_api_key=settings.GEMINI_API_KEY,
        collection_name=collection_name,
    )
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_BULK_FILES} files allowed per request",
        )

    # Read all files into memory before processing (so one bad read
    # doesn't leave partial work)
    file_data: list[tuple[bytes, str]] = []
    for f in files:
        contents = await f.read()
        if len(contents) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{f.filename}' exceeds maximum of {settings.MAX_FILE_SIZE_MB}MB",
            )
        file_data.append((contents, f.filename))

    if not file_data:
        return BulkUploadResponse(
            message="0 document(s) ingested successfully",
            results=[],
            total_chunks=0,
        )

    result = await service.ingest_multiple(file_data, access_level)
    results = [
        BulkUploadResult(**r) for r in result["results"]
    ]
    return BulkUploadResponse(
        message=result["message"],
        results=results,
        total_chunks=result["total_chunks"],
    )


# ---------------------------------------------------------------------------
# Listing & detail
# ---------------------------------------------------------------------------


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    _admin: User = Depends(get_current_admin_user),
    service: IngestionService = Depends(get_ingestion_service),
):
    """List all ingested documents grouped by source."""
    result = await service.list_documents()
    return DocumentListResponse(**result)


# IMPORTANT: /stats MUST be defined before /{source} to prevent
# FastAPI from matching "stats" as a source name.
@router.get("/stats", response_model=DocumentStatsResponse)
async def get_document_stats(
    _admin: User = Depends(get_current_admin_user),
    service: IngestionService = Depends(get_ingestion_service),
):
    """Return aggregated ingestion statistics."""
    result = await service.get_stats()
    return DocumentStatsResponse(**result)


@router.get("/{source}", response_model=DocumentDetailResponse)
async def get_document(
    source: str,
    _admin: User = Depends(get_current_admin_user),
    service: IngestionService = Depends(get_ingestion_service),
):
    """Return all chunks for a specific document."""
    result = await service.get_document(source)
    return DocumentDetailResponse(**result)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{source}", response_model=DocumentDeleteResponse)
async def delete_document(
    source: str,
    _admin: User = Depends(get_current_admin_user),
    service: IngestionService = Depends(get_ingestion_service),
):
    """Delete all chunks for a specific document."""
    result = await service.delete_document(source)
    return DocumentDeleteResponse(**result)
