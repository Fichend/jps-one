"""Semantic orchestration layer for Hunt Copilot chat messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.settings import Settings, get_settings
from hunt_copilot.schemas import HuntStrategy
from hunt_copilot.validator import StrategyValidator
from hunt_copilot_ai.guardrails import SemanticGuardrails
from hunt_copilot_ai.response_composer import SemanticResponseComposer
from hunt_copilot_ai.schemas import SemanticExtraction
from hunt_copilot_ai.semantic_extractor import SemanticExtractor
from hunt_copilot_ai.strategy_composer import StrategyComposer


@dataclass
class OrchestratorResult:
    strategy: HuntStrategy
    assistant_message: str
    changed: bool
    detected_conflicts: list[str] = field(default_factory=list)
    recent_strategy_changes: list[str] = field(default_factory=list)
    extraction: SemanticExtraction | None = None


class CopilotAIOrchestrator:
    """Replace the old regex-first planner with a semantic slot pipeline."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.extractor = SemanticExtractor(self.settings)
        self.guardrails = SemanticGuardrails()
        self.composer = StrategyComposer()
        self.response = SemanticResponseComposer()
        self.validator = StrategyValidator(self.settings)

    def handle_message(
        self,
        message: str,
        strategy: HuntStrategy,
        *,
        state: str,
        recent_messages: list[dict[str, Any]] | None = None,
        conversation_summary: str = "",
        last_user_intent: str = "",
        last_ai_action: str = "",
        clarification_focus: str = "",
    ) -> OrchestratorResult:
        extraction = self.extractor.extract(
            message,
            strategy,
            state=state,
            recent_messages=recent_messages or [],
            conversation_summary=conversation_summary,
            clarification_focus=clarification_focus,
        )
        guardrail_result = self.guardrails.review(extraction.slots, raw_message=message)
        compose_result = self.composer.compose(strategy, guardrail_result, raw_message=message)
        next_strategy = compose_result.strategy
        validation = self.validator.validate(next_strategy)
        next_strategy.uncertain_fields = _dedupe(
            [field for field in extraction.uncertain_fields if field in validation.missing_fields]
            + validation.missing_fields
        )
        detected_conflicts = _dedupe([*guardrail_result.detected_conflicts, *validation.detected_conflicts, *validation.blocking_errors, *validation.warnings])
        assistant = extraction.assistant_message.strip()
        if not assistant or compose_result.changed or detected_conflicts:
            assistant = self.response.compose(
                strategy=next_strategy,
                changed=compose_result.changed,
                recent_changes=compose_result.recent_changes,
                missing_fields=validation.missing_fields,
                detected_conflicts=detected_conflicts,
                rejected_fields=guardrail_result.rejected_fields,
            )
        return OrchestratorResult(
            strategy=next_strategy,
            assistant_message=assistant,
            changed=compose_result.changed,
            detected_conflicts=detected_conflicts,
            recent_strategy_changes=compose_result.recent_changes,
            extraction=extraction,
        )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value or "").casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(str(value).strip())
    return result
