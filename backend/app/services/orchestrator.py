"""Agent Orchestrator service — routes queries to the appropriate domain agent.

Provides the core routing logic for Feature 14.  Maintains an agent registry,
pre-classifies queries for routing, handles session-based follow-up routing,
and aggregates agent health checks.

Reference: ``.claude/specs/14-agent-orchestrator.md``

.. deprecated::
    Use :mod:`app.graph` (LangGraph StateGraphs) instead.
    ``OrchestratorService`` is kept for health checks and backward
    compatibility.  New features should use the graph-based pipeline.
"""

from __future__ import annotations

import logging
import warnings
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.hr_agent import HRAgent
from app.agents.it_agent import ITAgent
from app.core.exceptions import NotFoundException
from app.models.models import User
from app.repositories.message import MessageRepository
from app.services.classifier import ClassifierService
from app.services.gemini import GeminiService

logger = logging.getLogger(__name__)

warnings.warn(
    "OrchestratorService is deprecated. "
    "Use app.graph.orchestrator_graph + app.graph.agent_graph instead.",
    DeprecationWarning,
    stacklevel=2,
)


class OrchestratorService:
    """Routes user queries to the most appropriate domain agent.

    Maintains a registry of available agents and uses the existing
    :class:`ClassifierService` (Feature 7) to determine intent before
    delegating to the chosen agent.

    Adding a new agent requires **only** adding one entry to
    :attr:`AGENT_REGISTRY` — no other code changes needed.

    Usage::

        orch = OrchestratorService(db, gemini_api_key=settings.GEMINI_API_KEY)
        agent, agent_name = await orch.route_query(
            query="How do I reset my password?",
            user=current_user,
        )
        async for event in agent.process_query(query, user):
            ...
    """

    # ------------------------------------------------------------------
    # Agent registry (extend when adding new agents)
    # ------------------------------------------------------------------

    AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
        "hr": HRAgent,
        "it": ITAgent,
    }

    # Classification → agent_name mapping for direct routing
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

    # ------------------------------------------------------------------
    # Constructor
    # ------------------------------------------------------------------

    def __init__(self, db: AsyncSession, gemini_api_key: str) -> None:
        """Initialise the orchestrator with database session and API key.

        Creates its own :class:`ClassifierService` for pre-classification
        and :class:`MessageRepository` for session-based follow-up routing.
        """
        self.db = db
        self.gemini_api_key = gemini_api_key
        self.classifier = ClassifierService(GeminiService(gemini_api_key))
        self.message_repo = MessageRepository(db)

    # ------------------------------------------------------------------
    # Public — routing
    # ------------------------------------------------------------------

    async def route_query(
        self,
        query: str,
        user: User,
        session_id: Optional[UUID] = None,
        requested_agent: Optional[str] = None,
    ) -> tuple[BaseAgent, str]:
        """Determine which agent should handle *query* and return an instance.

        As a side effect, caches the classification result on the agent so
        it skips the redundant second classification call in its pipeline.

        Args:
            query: Raw user message.
            user: Authenticated user ORM object.
            session_id: Existing session UUID for follow-up context.
            requested_agent: If provided, bypasses classification and routes
                directly to this agent (e.g. ``"hr"``, ``"it"``).

        Returns:
            ``(agent_instance, agent_name)`` tuple.

        Raises:
            ValueError: If *requested_agent* is not in the registry.
        """
        # 1. Explicit override — bypass classification entirely
        if requested_agent:
            agent_name = requested_agent.lower().strip()
            if agent_name not in self.AGENT_REGISTRY:
                valid = list(self.AGENT_REGISTRY.keys())
                raise ValueError(
                    f"Unknown agent '{requested_agent}'. "
                    f"Valid agents: {valid}"
                )
            logger.info(
                "Orchestrator routing: explicit override → %s", agent_name
            )
            agent = self._create_agent(agent_name)
            return agent, agent_name

        # 2. Pre-classify for routing
        classification_result = await self._quick_classify(query, session_id)
        classification = classification_result["classification"]
        agent_name = await self._classification_to_agent(
            classification, session_id
        )
        logger.info(
            "Orchestrator routing: %s → %s", classification, agent_name
        )
        agent = self._create_agent(agent_name)
        # Cache classification so the agent's pipeline skips re-classifying
        agent._cached_classification = classification_result
        return agent, agent_name

    # ------------------------------------------------------------------
    # Public — agent discovery
    # ------------------------------------------------------------------

    def get_available_agents(self) -> list[dict]:
        """Return metadata for all registered agents.

        Used by ``GET /api/v1/orchestrator/agents`` to power the agent
        discovery / picker UI.
        """
        return [
            {
                "name": name,
                "display_name": cls.display_name,
                "description": self.AGENT_DESCRIPTIONS.get(
                    name, f"{cls.display_name} agent"
                ),
                "collection_name": cls.collection_name,
            }
            for name, cls in self.AGENT_REGISTRY.items()
        ]

    # ------------------------------------------------------------------
    # Public — health
    # ------------------------------------------------------------------

    async def health_check(self) -> dict:
        """Aggregate health of all registered agents.

        Returns a summary with per-agent health details and an overall
        status string.
        """
        agents_health: dict[str, dict] = {}
        overall = "healthy"

        for name, cls in self.AGENT_REGISTRY.items():
            try:
                agent = cls.create(
                    db=self.db, gemini_api_key=self.gemini_api_key
                )
                result = await agent.health_check()
                agents_health[name] = result
                if result.get("status") == "degraded":
                    overall = "degraded"
            except Exception:
                logger.exception(
                    "Health check failed for agent '%s'", name
                )
                agents_health[name] = {"status": "error"}
                overall = "degraded"

        return {
            "status": overall,
            "agents": agents_health,
            "default_agent": self.DEFAULT_AGENT,
        }

    # ------------------------------------------------------------------
    # Private — classification for routing
    # ------------------------------------------------------------------

    async def _quick_classify(
        self, query: str, session_id: Optional[UUID]
    ) -> dict:
        """Classify *query* using :class:`ClassifierService`.

        Fetches conversation history if a *session_id* is provided so the
        classifier can detect follow-ups.

        Returns:
            Full classification dict from :class:`ClassifierService.classify`.
        """
        history: list[dict] = []
        if session_id:
            try:
                history_msgs = await self.message_repo.get_conversation_history(
                    session_id, limit=6
                )
                history = [
                    {"role": m.role, "content": m.content}
                    for m in history_msgs
                ]
            except Exception:
                logger.warning(
                    "Could not load history for session %s — "
                    "classifying without context",
                    session_id,
                )

        result = await self.classifier.classify(query, history)
        return result

    async def _classification_to_agent(
        self, classification: str, session_id: Optional[UUID]
    ) -> str:
        """Map a classification label to an agent name."""
        # Direct mapping for domain-specific questions
        if classification in self.CLASSIFICATION_AGENT_MAP:
            return self.CLASSIFICATION_AGENT_MAP[classification]

        # Follow-ups route to the same agent as the last message
        if classification == "follow_up":
            return await self._get_session_agent(session_id)

        # greeting_only, bot_question, out_of_domain → default
        return self.DEFAULT_AGENT

    async def _get_session_agent(
        self, session_id: Optional[UUID]
    ) -> str:
        """Look up which agent handled the last assistant message in this
        session.

        Returns:
            Agent name string or :attr:`DEFAULT_AGENT` if no history.
        """
        if not session_id:
            return self.DEFAULT_AGENT
        try:
            last_agent = await self.message_repo.get_last_agent_name(
                session_id
            )
            if last_agent:
                logger.debug(
                    "Follow-up routing: session %s → %s",
                    session_id,
                    last_agent,
                )
                return last_agent
        except Exception:
            logger.exception(
                "Failed to look up last agent for session %s", session_id
            )

        return self.DEFAULT_AGENT

    # ------------------------------------------------------------------
    # Private — agent instantiation
    # ------------------------------------------------------------------

    def _create_agent(self, agent_name: str) -> BaseAgent:
        """Instantiate an agent by name using its ``create()`` factory.

        Args:
            agent_name: Registered agent name (e.g. ``"hr"``, ``"it"``).

        Returns:
            A fully-initialised :class:`BaseAgent` subclass instance.

        Raises:
            NotFoundException: If *agent_name* is not in the registry.
        """
        agent_cls = self.AGENT_REGISTRY.get(agent_name)
        if agent_cls is None:
            raise NotFoundException(
                f"Unknown agent: '{agent_name}'. "
                f"Valid agents: {list(self.AGENT_REGISTRY.keys())}"
            )
        return agent_cls.create(
            db=self.db, gemini_api_key=self.gemini_api_key
        )
