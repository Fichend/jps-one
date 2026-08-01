"""Allowed-action state machine for Hunt Copilot."""

from __future__ import annotations

from hunt_copilot.schemas import CopilotSession, CopilotState
from hunt_copilot.validator import ValidationResult


def choose_state(session: CopilotSession, validation: ValidationResult, *, intent: str = "") -> CopilotState:
    if intent == "cancel_session":
        return CopilotState.CANCELLED
    if session.state in {CopilotState.RUNNING_FULL_SEARCH, CopilotState.COMPLETED, CopilotState.FAILED, CopilotState.CANCELLED}:
        return session.state
    if validation.can_confirm_strategy:
        if session.strategy.strategy_confirmed:
            return CopilotState.WAITING_EXECUTION_CONFIRMATION if session.preview else CopilotState.WAITING_STRATEGY_CONFIRMATION
        return CopilotState.STRATEGY_READY
    return CopilotState.COLLECTING_REQUIREMENTS


def allowed_actions(session: CopilotSession, validation: ValidationResult) -> list[str]:
    actions = ["restart_session", "cancel_session"]
    if validation.can_confirm_strategy and not session.strategy.strategy_confirmed:
        actions.append("confirm_strategy")
    if session.strategy.strategy_confirmed and not session.preview:
        actions.append("check_channels")
    if session.preview and session.strategy.strategy_confirmed and not session.automation_job_id:
        actions.append("confirm_execution")
    return actions
