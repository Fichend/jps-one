"""Semantic Hunt Copilot layer.

This package replaces the old regex-first strategy planner for conversational
requirement collection. It keeps the existing Hunt execution gates intact.
"""

from hunt_copilot_ai.orchestrator import CopilotAIOrchestrator, OrchestratorResult

__all__ = ["CopilotAIOrchestrator", "OrchestratorResult"]
