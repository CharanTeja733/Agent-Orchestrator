"""Document ingestion service — orchestrates the full pipeline.

Parse → detect sections → chunk → embed → store.

All public methods manage their own transaction boundaries.
The private ``_ingest_internal`` method performs the pipeline but does
**not** commit — callers decide when to commit or roll back.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    DocumentNotFoundError,
    EmbeddingGenerationError,
    EmptyDocumentError,
    UnsupportedFileTypeError,
)
from app.repositories.document import DocumentRepository
from app.utils.chunker import (
    _find_page_markers,
    assign_page_to_chunks,
    assign_sections_to_chunks,
    chunk_text,
    detect_sections,
)
from app.utils.embedder import embed_texts
from app.utils.parser import extract_text, validate_file_type

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates document ingestion: parse, chunk, embed, store."""

    def __init__(self, db: AsyncSession, gemini_api_key: str) -> None:
        self.db = db
        self.gemini_api_key = gemini_api_key
        self.document_repo = DocumentRepository(db)

    # ------------------------------------------------------------------
    # Private pipeline (no commit / rollback)
    # ------------------------------------------------------------------

    async def _ingest_internal(
        self,
        file_bytes: bytes,
        filename: str,
        access_level: str = "all",
    ) -> dict:
        """Run the full pipeline for a single file.

        Does **not** commit — the caller owns the transaction.
        """
        # 1. Validate file type
        if not validate_file_type(filename):
            ext = filename.rsplit(".", 1)[-1] if "." in filename else "unknown"
            raise UnsupportedFileTypeError(
                file_type=f".{ext}",
                allowed=settings.ALLOWED_FILE_TYPES,
            )

        # 2. Parse
        try:
            text = extract_text(file_bytes, filename)
        except ValueError as exc:
            raise EmptyDocumentError() from exc

        if not text or not text.strip():
            raise EmptyDocumentError()

        total_chars = len(text)

        # 3. Detect sections & page markers
        sections = detect_sections(text)
        page_markers = _find_page_markers(text)

        # 4. Chunk
        chunks = chunk_text(
            text,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )

        # 5. Assign metadata
        chunks = assign_sections_to_chunks(chunks, sections)
        chunks = assign_page_to_chunks(chunks, page_markers)

        # 6. Filter tiny chunks (re-index after)
        chunks = [c for c in chunks if len(c["content"]) >= 100]
        if not chunks:
            raise EmptyDocumentError()

        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i

        # 7. Embed
        try:
            contents = [c["content"] for c in chunks]
            embeddings = await embed_texts(
                contents,
                api_key=self.gemini_api_key,
                model=settings.EMBEDDING_MODEL,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=settings.EMBEDDING_DIMENSIONS,
                batch_size=settings.EMBEDDING_BATCH_SIZE,
            )
        except EmbeddingGenerationError:
            raise
        except Exception as exc:
            logger.exception("Unexpected embedding failure")
            raise EmbeddingGenerationError(attempts=3) from exc

        # 8. Build DB-ready chunk dicts
        db_chunks: list[dict] = []
        for chunk, embedding in zip(chunks, embeddings):
            db_chunks.append({
                "content": chunk["content"],
                "embedding": embedding,
                "source": filename,
                "page": chunk.get("page"),
                "section": chunk.get("section"),
                "chunk_index": chunk["chunk_index"],
                "access_level": access_level,
            })

        # 9. Replace old chunks with new (within same transaction)
        await self.document_repo.delete_by_source(filename)
        await self.document_repo.insert_chunks(db_chunks)

        logger.info(
            "Ingested '%s': %d chunks, %d chars",
            filename,
            len(db_chunks),
            total_chars,
        )

        return {
            "message": "Document ingested successfully",
            "source": filename,
            "chunks_created": len(db_chunks),
            "total_chars": total_chars,
            "access_level": access_level,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        file_bytes: bytes,
        filename: str,
        access_level: str = "all",
    ) -> dict:
        """Ingest a single document and commit."""
        result = await self._ingest_internal(file_bytes, filename, access_level)
        await self.db.commit()
        return result

    async def ingest_multiple(
        self,
        files: list[tuple[bytes, str]],
        access_level: str = "all",
    ) -> dict:
        """Ingest multiple files atomically — all or nothing."""
        results: list[dict] = []
        total_chunks = 0

        try:
            for file_bytes, filename in files:
                result = await self._ingest_internal(
                    file_bytes, filename, access_level
                )
                results.append({
                    "source": filename,
                    "chunks_created": result["chunks_created"],
                    "status": "success",
                })
                total_chunks += result["chunks_created"]

            await self.db.commit()

        except Exception:
            logger.exception("Bulk ingestion failed — rolling back all files")
            await self.db.rollback()
            raise

        return {
            "message": f"{len(results)} document(s) ingested successfully",
            "results": results,
            "total_chunks": total_chunks,
        }

    async def list_documents(self) -> dict:
        """Return all ingested documents grouped by source."""
        rows = await self.document_repo.list_documents()
        total_chunks = sum(r["chunk_count"] for r in rows)
        return {
            "documents": rows,
            "total_documents": len(rows),
            "total_chunks": total_chunks,
        }

    async def get_document(self, source: str) -> dict:
        """Return all chunks for *source*."""
        chunks = await self.document_repo.get_by_source(source)
        if not chunks:
            raise DocumentNotFoundError(source)

        return {
            "source": source,
            "access_level": chunks[0].access_level,
            "chunks": [
                {
                    "chunk_index": c.chunk_index,
                    "content": c.content,
                    "page": c.page,
                    "section": c.section,
                }
                for c in chunks
            ],
            "total_chunks": len(chunks),
        }

    async def delete_document(self, source: str) -> dict:
        """Delete all chunks for *source*."""
        if not await self.document_repo.source_exists(source):
            raise DocumentNotFoundError(source)

        deleted = await self.document_repo.delete_by_source(source)
        await self.db.commit()

        logger.info("Deleted document '%s': %d chunks removed", source, deleted)

        return {
            "message": "Document deleted successfully",
            "source": source,
            "chunks_deleted": deleted,
        }

    async def get_stats(self) -> dict:
        """Return aggregated ingestion statistics."""
        return await self.document_repo.get_document_stats()
