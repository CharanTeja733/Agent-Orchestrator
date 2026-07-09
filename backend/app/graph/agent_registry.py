"""Agent configuration registry.

Extracts all class-level attributes from ``BaseAgent`` subclasses into flat
config dicts used by LangGraph state.  The existing ``HRAgent`` / ``ITAgent``
classes remain untouched — they are imported and introspected.

Adding a new agent requires:
  1. A prompt module in ``app/prompts/``
  2. A ``BaseAgent`` subclass with class-level attributes
  3. One entry in ``AGENT_CONFIGS`` (inside ``_load_configs()``)
"""

from __future__ import annotations

from typing import Any

from app.config import settings


# ---------------------------------------------------------------------------
# Config extractor
# ---------------------------------------------------------------------------


def _extract_agent_config(agent_cls: type) -> dict[str, Any]:
    """Extract all class-level attributes from a ``BaseAgent`` subclass.

    Returns a flat dict containing every prompt template, response text,
    threshold, and metadata — unpacked into ``AgentState`` at runtime.
    """
    return {
        # Identity
        "agent_name": agent_cls.agent_name,
        "display_name": agent_cls.display_name,
        "collection_name": agent_cls.collection_name,
        # Generation prompts
        "system_prompt": agent_cls.system_prompt,
        "user_prompt_template": agent_cls.user_prompt_template,
        # Formatting templates
        "context_chunk_template": agent_cls.context_chunk_template,
        "history_entry_template": agent_cls.history_entry_template,
        "history_empty": agent_cls.history_empty,
        # Confidence notes
        "confidence_note_medium": agent_cls.confidence_note_medium,
        "low_confidence_disclaimer": agent_cls.low_confidence_disclaimer,
        # Fallback responses
        "hard_fallback_response": agent_cls.hard_fallback_response,
        "soft_fallback_template": agent_cls.soft_fallback_template,
        # Direct responses
        "greeting_template": agent_cls.greeting_template,
        "thanks_response": agent_cls.thanks_response,
        "bye_response": agent_cls.bye_response,
        "greeting_back_response": agent_cls.greeting_back_response,
        "bot_question_response": agent_cls.bot_question_response,
        "out_of_domain_response": agent_cls.out_of_domain_response,
        # Thresholds (with defaults from subclass or settings)
        "top_k_retrieval": getattr(
            agent_cls, "top_k_retrieval", settings.TOP_K_RETRIEVAL
        ),
        "min_retrieval_score": getattr(
            agent_cls, "min_retrieval_score", settings.MIN_RETRIEVAL_SCORE
        ),
        "high_confidence_threshold": getattr(
            agent_cls, "high_confidence_threshold", settings.HIGH_CONFIDENCE_THRESHOLD
        ),
        "medium_confidence_threshold": getattr(
            agent_cls,
            "medium_confidence_threshold",
            settings.MEDIUM_CONFIDENCE_THRESHOLD,
        ),
        "low_confidence_threshold": getattr(
            agent_cls, "low_confidence_threshold", settings.LOW_CONFIDENCE_THRESHOLD
        ),
        "max_conversation_history": getattr(
            agent_cls, "max_conversation_history", settings.MAX_CONVERSATION_HISTORY
        ),
        "max_completion_tokens": getattr(
            agent_cls, "max_completion_tokens", settings.MAX_COMPLETION_TOKENS
        ),
        "response_temperature": getattr(
            agent_cls, "response_temperature", settings.RESPONSE_TEMPERATURE
        ),
    }


# ---------------------------------------------------------------------------
# Agent config registry (lazy-loaded)
# ---------------------------------------------------------------------------

AGENT_CONFIGS: dict[str, dict[str, Any]] = {}


def _load_configs() -> None:
    """Lazy-load agent configs so import order does not matter.

    Called once on first access — subsequent calls are a no-op.
    """
    if AGENT_CONFIGS:
        return
    # Deferred imports to avoid circular dependencies at module level
    from app.agents.hr_agent import HRAgent  # noqa: E402
    from app.agents.it_agent import ITAgent  # noqa: E402

    AGENT_CONFIGS["hr"] = _extract_agent_config(HRAgent)
    AGENT_CONFIGS["it"] = _extract_agent_config(ITAgent)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_agent_config(agent_name: str) -> dict[str, Any]:
    """Return the full config dict for a named agent.

    Args:
        agent_name: Registered agent key (e.g. ``"hr"``, ``"it"``).

    Returns:
        A **copy** of the config dict — safe to mutate.

    Raises:
        KeyError: If *agent_name* is not in the registry.
    """
    _load_configs()
    if agent_name not in AGENT_CONFIGS:
        raise KeyError(
            f"Unknown agent '{agent_name}'. "
            f"Valid agents: {list(AGENT_CONFIGS.keys())}"
        )
    return AGENT_CONFIGS[agent_name].copy()


def get_available_agents() -> list[dict[str, Any]]:
    """Return metadata for all registered agents.

    Used by ``GET /orchestrator/agents`` for the agent discovery / picker UI.
    """
    _load_configs()
    return [
        {
            "name": name,
            "display_name": cfg["display_name"],
            "description": AGENT_DESCRIPTIONS.get(name, f"{cfg['display_name']} agent"),
            "collection_name": cfg["collection_name"],
        }
        for name, cfg in AGENT_CONFIGS.items()
    ]


# ---------------------------------------------------------------------------
# Routing constants
# ---------------------------------------------------------------------------

# Classification → agent_name mapping (same as OrchestratorService)
CLASSIFICATION_AGENT_MAP: dict[str, str] = {
    "hr_question": "hr",
    "it_question": "it",
}

# Fallback agent for non-domain queries (greetings, bot_questions, etc.)
DEFAULT_AGENT: str = "hr"

# Human-readable descriptions for the agent discovery endpoint
AGENT_DESCRIPTIONS: dict[str, str] = {
    "hr": (
        "Answers HR-related questions about company policies, leave, "
        "benefits, remote work, and more"
    ),
    "it": (
        "Helps with technical issues including VPN, laptops, software, "
        "passwords, email, and network problems"
    ),
}
