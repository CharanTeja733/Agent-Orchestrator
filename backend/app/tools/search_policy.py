"""SearchPolicyTool — RAG search for HR policy documents (Feature 16).

Wraps the existing :class:`~app.services.search.SearchService` so the LLM
can request a policy-document search via Gemini native function calling.
"""

from __future__ import annotations

from app.tools.base import BaseTool, ToolResult


class SearchPolicyTool(BaseTool):
    """Search the HR policy knowledge base for relevant documents.

    This tool performs a pgvector similarity search over the agent's
    document collection, returning the most relevant policy chunks.
    """

    name = "search_policy"
    description = (
        "Search the HR policy knowledge base for information about company "
        "policies, benefits rules, leave eligibility, remote work guidelines, "
        "payroll procedures, and other HR topics. Use this when the user asks "
        "about general policies or procedures."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to find relevant policy documents",
            },
        },
        "required": ["query"],
    }

    def __init__(self, search_service) -> None:
        """Initialise with an existing :class:`SearchService` instance."""
        self._search_service = search_service

    async def execute(self, **params: object) -> ToolResult:
        """Execute a policy search.

        Expected *params* (injected by :meth:`ToolRegistry.execute_tool`):
            query (str): Search query string.
            user_role (str): Authenticated user's role for access filtering.
            db: Database session (unused here — search_service has its own).
            gemini_api_key: API key (unused here — search_service has its own).
            collection_name: Document collection name (unused here).
        """
        query = str(params.get("query", ""))
        user_role = str(params.get("user_role", "employee"))

        if not query.strip():
            return ToolResult(
                tool_name=self.name,
                error="search_policy requires a non-empty query",
            )

        try:
            search_result = await self._search_service.search(
                query=query.strip(),
                user_role=user_role,
                top_k=5,
                min_score=0.3,
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                error=f"Policy search failed: {exc}",
            )

        results = search_result.get("results", [])
        return ToolResult(
            tool_name=self.name,
            data={
                "label": "POLICY SEARCH RESULTS",
                "results": results,
                "total_found": len(results),
                "overall_confidence": search_result.get("overall_confidence", "low"),
                "formatted": self._format_results(results),
            },
        )

    @staticmethod
    def _format_results(results: list[dict]) -> str:
        """Format search results for prompt injection."""
        if not results:
            return "(No relevant policy documents found.)"

        lines: list[str] = []
        for i, r in enumerate(results, 1):
            source = r.get("source", "Unknown")
            page = r.get("page", "N/A")
            section = r.get("section", "")
            content = r.get("content", "")
            score = r.get("score", 0)
            section_str = f", Section: {section}" if section else ""
            lines.append(
                f"[{i}] Source: {source}, Page {page}{section_str} "
                f"(relevance: {score:.0%})\n{content[:500]}"
            )
        return "\n\n".join(lines)
