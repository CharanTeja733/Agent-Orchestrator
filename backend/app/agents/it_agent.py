"""IT domain agent — tool-enabled subclass of BaseAgent (Features 13 + 17).

Overrides ``_run_tool_hooks()`` and ``create()`` to support Gemini-native
function calling for Jira ticket queries.

Reference: ``.claude/specs/13-it-agent.md``,
           ``.claude/specs/17-jira-integration.md``
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.prompts.it_agent import (
    IT_BOT_QUESTION_RESPONSE,
    IT_BYE_RESPONSE,
    IT_CONFIDENCE_NOTE_MEDIUM,
    IT_CONTEXT_CHUNK_TEMPLATE,
    IT_GREETING_BACK_RESPONSE,
    IT_GREETING_TEMPLATE,
    IT_HARD_FALLBACK_RESPONSE,
    IT_HISTORY_EMPTY,
    IT_HISTORY_ENTRY_TEMPLATE,
    IT_LOW_CONFIDENCE_DISCLAIMER,
    IT_OUT_OF_DOMAIN_RESPONSE,
    IT_SOFT_FALLBACK_TEMPLATE,
    IT_SYSTEM_PROMPT,
    IT_THANKS_RESPONSE,
    IT_USER_PROMPT_TEMPLATE,
)
from app.services.classifier import ClassifierService
from app.services.gemini import GeminiService
from app.services.search import SearchService

logger = logging.getLogger(__name__)


class ITAgent(BaseAgent):
    """IT support domain agent with tool-use support (Feature 17).

    Uses Gemini native function calling to decide whether to query
    Jira for the user's open tickets.
    """

    # -- Agent metadata --------------------------------------------------
    agent_name = "it"
    display_name = "IT Support"
    collection_name = "it_documents"

    # -- Answer-generation prompts ---------------------------------------
    system_prompt = IT_SYSTEM_PROMPT
    user_prompt_template = IT_USER_PROMPT_TEMPLATE

    # -- Formatting templates --------------------------------------------
    context_chunk_template = IT_CONTEXT_CHUNK_TEMPLATE
    history_entry_template = IT_HISTORY_ENTRY_TEMPLATE
    history_empty = IT_HISTORY_EMPTY

    # -- Confidence notes ------------------------------------------------
    confidence_note_medium = IT_CONFIDENCE_NOTE_MEDIUM
    low_confidence_disclaimer = IT_LOW_CONFIDENCE_DISCLAIMER

    # -- Fallback responses ----------------------------------------------
    hard_fallback_response = IT_HARD_FALLBACK_RESPONSE
    soft_fallback_template = IT_SOFT_FALLBACK_TEMPLATE

    # -- Direct (non-retrieval) responses --------------------------------
    greeting_template = IT_GREETING_TEMPLATE
    thanks_response = IT_THANKS_RESPONSE
    bye_response = IT_BYE_RESPONSE
    greeting_back_response = IT_GREETING_BACK_RESPONSE
    bot_question_response = IT_BOT_QUESTION_RESPONSE
    out_of_domain_response = IT_OUT_OF_DOMAIN_RESPONSE

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(
        self,
        db: AsyncSession,
        gemini_service: GeminiService,
        classifier_service: ClassifierService,
        search_service: SearchService,
        tool_registry: Any = None,
    ) -> None:
        super().__init__(db, gemini_service, classifier_service, search_service)
        self.tool_registry = tool_registry

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, db: AsyncSession, gemini_api_key: str) -> "ITAgent":
        """Factory — creates service instances, builds tool registry.

        Jira tool registration is skipped gracefully when Jira is not
        configured (missing env vars). The agent remains fully functional
        for documentation queries.
        """
        from app.tools import GetMyTicketsTool, ToolRegistry
        from app.services.jira import JiraService
        from app.config import settings

        gemini = GeminiService(gemini_api_key)
        classifier = ClassifierService(gemini)
        search = SearchService(
            db, gemini_api_key, collection_name=cls.collection_name
        )

        registry = ToolRegistry()
        try:
            jira_service = JiraService(
                base_url=settings.JIRA_BASE_URL,
                email=settings.JIRA_BOT_EMAIL,
                api_token=settings.JIRA_API_TOKEN,
                timeout=settings.JIRA_REQUEST_TIMEOUT_SECONDS,
                max_results=settings.JIRA_MAX_RESULTS,
            )
            registry.register(GetMyTicketsTool(jira_service))
            logger.info("Jira ticket tool registered for IT Agent")
        except ValueError as exc:
            logger.info(
                "Jira not configured — IT Agent will run without ticket tool: %s",
                exc,
            )

        return cls(db, gemini, classifier, search, registry)

    # ------------------------------------------------------------------
    # Tool hooks (Feature 17)
    # ------------------------------------------------------------------

    async def _run_tool_hooks(
        self,
        query: str,
        user: Any,
        search_query: str,
        chunks: list[dict],
    ) -> list[dict] | None:
        """Use Gemini native function calling to decide and execute tools.

        Returns formatted tool result dicts for prompt injection, or
        ``None`` if no tools were needed / tool selection failed.
        """
        if not self.tool_registry:
            return None

        tool_declarations = self.tool_registry.get_tool_declarations()

        # Build a minimal prompt for tool selection
        tool_prompt = self._build_prompt(
            query=search_query,
            chunks=chunks,
            history_messages=[],
            confidence="high",
        )

        try:
            result = await self.gemini_service.generate_with_tools(
                prompt=tool_prompt,
                tools=tool_declarations,
                temperature=0.1,
                max_output_tokens=200,
            )
        except Exception:
            logger.warning("Tool selection LLM call failed — skipping tools")
            return None

        if result["type"] != "function_calls":
            return None  # Gemini decided no tools are needed

        tool_context = {
            "db": self.db,
            "user_id": str(user.id),
            "user_email": user.email,
            "user_role": user.role,
            "gemini_api_key": self.gemini_service.api_key,
            "collection_name": self.collection_name,
        }

        results: list[dict] = []
        for call in result.get("calls", []):
            try:
                tr = await self.tool_registry.execute_tool(
                    call["name"], call.get("args", {}), tool_context
                )
                results.append({
                    "tool_name": tr.tool_name,
                    "data": tr.data,
                    "error": tr.error,
                })
            except Exception as exc:
                logger.warning(
                    "Tool '%s' execution failed: %s", call.get("name"), exc
                )
                results.append({
                    "tool_name": call.get("name", "unknown"),
                    "data": {},
                    "error": str(exc),
                })

        return results if results else None
