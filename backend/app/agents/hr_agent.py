"""HR domain agent — thin configuration-only subclass of BaseAgent (Feature 12).

No method overrides — only class-level attribute assignments.  All pipeline
logic is inherited from :class:`BaseAgent`.

Reference: ``.claude/specs/12-refactor-hr-agent-into-base-agent.md``
"""

from __future__ import annotations

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


class HRAgent(BaseAgent):
    """HR domain agent.

    Only defines agent-specific attributes.  All pipeline logic is
    inherited from :class:`BaseAgent`.  No method overrides needed.
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
