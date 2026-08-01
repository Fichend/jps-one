"""GoalGuard target-customer enforcement for JPS-One lead hunts."""

from goal_guard.classifier import classify_candidate, classify_candidates
from goal_guard.types import TargetType, TargetTypeAssessment, TargetTypeContext

__all__ = [
    "TargetType",
    "TargetTypeAssessment",
    "TargetTypeContext",
    "classify_candidate",
    "classify_candidates",
]
