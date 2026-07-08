"""Vector search service — orchestrates embedding + pgvector similarity search."""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import HRDocument, ITDocument
from app.repositories.document import DocumentRepository
from app.services.gemini import GeminiService


def _get_document_model(collection_name: str) -> type:
    """Map a collection name string to the corresponding ORM model class."""
    mapping: dict[str, type] = {
        "hr_documents": HRDocument,
        "it_documents": ITDocument,
    }
    return mapping.get(collection_name, HRDocument)


class SearchService:
    """Stateless service that orchestrates the vector search pipeline.

    Uses Gemini for query embedding and pgvector for cosine similarity
    search, with role-based access control filtering at the database level.
    """

    def __init__(
        self,
        db: AsyncSession,
        gemini_api_key: str,
        collection_name: str = "hr_documents",
    ) -> None:
        self.db = db
        self.gemini_service = GeminiService(gemini_api_key)
        model = _get_document_model(collection_name)
        self.document_repo = DocumentRepository(db, model_class=model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        user_role: str,
        top_k: int = 5,
        access_levels: list[str] | None = None,
        min_score: float = 0.5,
    ) -> dict:
        """Run the full search pipeline and return ranked results.

        1. Resolve access levels from *user_role* (if not explicitly given).
        2. Generate a ``RETRIEVAL_QUERY`` embedding for *query*.
        3. Perform cosine similarity search via pgvector.
        4. Assign confidence labels to each result.
        5. Compute an overall confidence score.
        """
        start_time = time.time()

        # 1. Determine allowed access levels
        if access_levels is None:
            access_levels = self._get_access_levels_for_role(user_role)

        # 2. Generate query embedding (RETRIEVAL_QUERY task type for search)
        query_embedding = await self.gemini_service.embed_single(
            query,
            task_type="RETRIEVAL_QUERY",
        )

        # 3. Similarity search (access control enforced in SQL)
        results = await self.document_repo.search_similar(
            query_embedding=query_embedding,
            access_levels=access_levels,
            top_k=top_k,
            min_score=min_score,
        )

        # 4. Assign per-result confidence
        results = self._assign_confidence(results)

        # 5. Map DB field names to schema field names
        results = self._format_results(results)

        # 6. Overall confidence
        overall_confidence = self._calculate_overall_confidence(results)
        elapsed_ms = (time.time() - start_time) * 1000

        return {
            "query": query,
            "results": results,
            "total_found": len(results),
            "search_time_ms": round(elapsed_ms, 2),
            "overall_confidence": overall_confidence,
        }

    async def health_check(self) -> dict:
        """Return operational status of the vector search subsystem."""
        index_exists = await self.document_repo.check_vector_index_exists()
        total_docs = await self.document_repo.get_total_indexed_count()

        healthy = index_exists and total_docs > 0
        return {
            "status": "healthy" if healthy else "degraded",
            "vector_index_exists": index_exists,
            "total_documents_indexed": total_docs,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_access_levels_for_role(role: str) -> list[str]:
        """Map a user role to the list of access levels they may search."""
        role_access_map = {
            "employee": ["all"],
            "manager": ["all", "manager"],
            "hr_admin": ["all", "manager", "hr_admin"],
        }
        return role_access_map.get(role, ["all"])

    @staticmethod
    def _assign_confidence(results: list[dict]) -> list[dict]:
        """Tag each result with a confidence label based on its similarity score.

        Thresholds:
        - ``>= 0.75`` → ``"high"``
        - ``>= 0.50`` → ``"medium"``
        - ``< 0.50``  → ``"low"``
        """
        for result in results:
            score = result["score"]
            if score >= 0.75:
                result["confidence"] = "high"
            elif score >= 0.50:
                result["confidence"] = "medium"
            else:
                result["confidence"] = "low"
        return results

    @staticmethod
    def _format_results(results: list[dict]) -> list[dict]:
        """Rename DB column names to schema field names (``id`` → ``chunk_id``)."""
        for r in results:
            r["chunk_id"] = r.pop("id")
        return results

    @staticmethod
    def _calculate_overall_confidence(results: list[dict]) -> str:
        """Derive an overall confidence label from the result set.

        Returns ``"no_match"`` when there are no results, otherwise averages
        the scores and applies the same thresholds as ``_assign_confidence``.
        """
        if not results:
            return "no_match"

        avg_score = sum(r["score"] for r in results) / len(results)

        if avg_score >= 0.75:
            return "high"
        elif avg_score >= 0.50:
            return "medium"
        else:
            return "low"
