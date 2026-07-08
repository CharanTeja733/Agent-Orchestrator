"""IT domain agent — thin configuration-only subclass of BaseAgent (Feature 13).

No method overrides — only class-level attribute assignments.  All pipeline
logic is inherited from :class:`BaseAgent`.

Reference: ``.claude/specs/13-it-agent.md``
"""

from __future__ import annotations

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


class ITAgent(BaseAgent):
    """IT support domain agent.

    Only defines agent-specific attributes.  All pipeline logic is
    inherited from :class:`BaseAgent`.  No method overrides needed.
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
