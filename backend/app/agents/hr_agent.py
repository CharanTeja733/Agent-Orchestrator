"""HR domain agent — tool-enabled subclass of BaseAgent (Features 12 + 16).

Overrides ``_run_tool_hooks()`` and ``create()`` to support Gemini-native
function calling for leave balance queries and policy searches.

Reference: ``.claude/specs/12-refactor-hr-agent-into-base-agent.md``,
           ``.claude/specs/16-personal-leave-balance-with-tool-use.md``
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.prompts.hr_agent import (
    BOT_QUESTION_RESPONSE,
    BYE_RESPONSE,
    CONFIDENCE_NOTE_MEDIUM,
    CONTEXT_CHUNK_TEMPLATE,
    GREETING_BACK_RESPONSE,
    GREETING_TEMPLATE,
    HARD_FALLBACK_RESPONSE,
    HISTORY_EMPTY,
    HISTORY_ENTRY_TEMPLATE,
    LOW_CONFIDENCE_DISCLAIMER,
    OUT_OF_DOMAIN_RESPONSE,
    SOFT_FALLBACK_TEMPLATE,
    SYSTEM_PROMPT,
    THANKS_RESPONSE,
    USER_PROMPT_TEMPLATE,
)
from app.services.classifier import ClassifierService
from app.services.gemini import GeminiService
from app.services.search import SearchService

logger = logging.getLogger(__name__)


class HRAgent(BaseAgent):
    """HR domain agent with tool-use support (Feature 16).

    Uses Gemini native function calling to decide whether to query
    personal leave balances, search policy documents, or both.
    """

    # -- Agent metadata --------------------------------------------------
    agent_name = "hr"
    display_name = "HR Agent"
    collection_name = "hr_documents"

    # -- Answer-generation prompts ---------------------------------------
    system_prompt = SYSTEM_PROMPT
    user_prompt_template = USER_PROMPT_TEMPLATE

    # -- Formatting templates --------------------------------------------
    context_chunk_template = CONTEXT_CHUNK_TEMPLATE
    history_entry_template = HISTORY_ENTRY_TEMPLATE
    history_empty = HISTORY_EMPTY

    # -- Confidence notes ------------------------------------------------
    confidence_note_medium = CONFIDENCE_NOTE_MEDIUM
    low_confidence_disclaimer = LOW_CONFIDENCE_DISCLAIMER

    # -- Fallback responses ----------------------------------------------
    hard_fallback_response = HARD_FALLBACK_RESPONSE
    soft_fallback_template = SOFT_FALLBACK_TEMPLATE

    # -- Direct (non-retrieval) responses --------------------------------
    greeting_template = GREETING_TEMPLATE
    thanks_response = THANKS_RESPONSE
    bye_response = BYE_RESPONSE
    greeting_back_response = GREETING_BACK_RESPONSE
    bot_question_response = BOT_QUESTION_RESPONSE
    out_of_domain_response = OUT_OF_DOMAIN_RESPONSE

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
    def create(cls, db: AsyncSession, gemini_api_key: str) -> "HRAgent":
        """Factory — creates service instances, builds tool registry."""
        from app.repositories.leave import LeaveRepository
        from app.tools import (
            GetLeaveBalanceTool,
            SearchPolicyTool,
            ToolRegistry,
        )

        gemini = GeminiService(gemini_api_key)
        classifier = ClassifierService(gemini)
        search = SearchService(
            db, gemini_api_key, collection_name=cls.collection_name
        )

        registry = ToolRegistry()
        registry.register(SearchPolicyTool(search))
        registry.register(GetLeaveBalanceTool(LeaveRepository(db)))

        return cls(db, gemini, classifier, search, registry)

    # ------------------------------------------------------------------
    # Tool hooks (Feature 16)
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
