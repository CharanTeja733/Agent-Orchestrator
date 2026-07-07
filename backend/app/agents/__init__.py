"""Agent abstraction layer — reusable base class and domain agent implementations.

Reference: ``.claude/specs/12-refactor-hr-agent-into-base-agent.md``
"""

from app.agents.base import BaseAgent
from app.agents.hr_agent import HRAgent

__all__ = ["BaseAgent", "HRAgent"]
