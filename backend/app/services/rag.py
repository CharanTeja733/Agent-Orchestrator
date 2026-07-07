"""Thin backward-compatibility wrapper for the RAG pipeline (Feature 8, 12).

Preserves the ``RAGService`` import path so that existing code importing
from ``app.services.rag`` continues to work without changes.

All pipeline logic has moved to :class:`app.agents.base.BaseAgent` and
:class:`app.agents.hr_agent.HRAgent`.

Reference: ``.claude/specs/12-refactor-hr-agent-into-base-agent.md``
"""

from __future__ import annotations

from typing import AsyncIterator, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.hr_agent import HRAgent
from app.models.models import User


class RAGService:
    """Backward-compatible wrapper around :class:`HRAgent`.

    Accepts the same constructor arguments as before (``db`` + ``gemini_api_key``)
    and delegates all calls to an internal ``HRAgent`` instance.
    """

    def __init__(self, db: AsyncSession, gemini_api_key: str) -> None:
        self._agent = HRAgent.create(db=db, gemini_api_key=gemini_api_key)

    async def process_query(
        self,
        query: str,
        user: User,
        session_id: Optional[UUID] = None,
    ) -> AsyncIterator[dict]:
        """Delegate to :meth:`HRAgent.process_query`."""
        async for event in self._agent.process_query(query, user, session_id):
            yield event

    async def process_query_test(
        self,
        query: str,
        user: User,
        session_id: Optional[UUID] = None,
    ) -> dict:
        """Delegate to :meth:`HRAgent.process_query_test`."""
        return await self._agent.process_query_test(query, user, session_id)

    async def health_check(self) -> dict:
        """Delegate to :meth:`HRAgent.health_check`."""
        return await self._agent.health_check()
