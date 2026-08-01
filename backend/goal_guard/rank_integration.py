"""Helpers that apply GoalGuard before candidate ranking."""

from __future__ import annotations

from typing import Any

from goal_guard.classifier import classify_candidates
from goal_guard.types import TargetTypeContext


def apply_goal_guard(
    candidates: list[dict[str, Any]],
    *,
    customer_types: list[str] | None = None,
    product_keywords: list[str] | None = None,
    target_regions: list[str] | None = None,
    exclusions: list[str] | None = None,
) -> list[dict[str, Any]]:
    context = TargetTypeContext(
        customer_types=[str(item) for item in (customer_types or []) if str(item or "").strip()],
        product_keywords=[str(item) for item in (product_keywords or []) if str(item or "").strip()],
        target_regions=[str(item) for item in (target_regions or []) if str(item or "").strip()],
        exclusions=[str(item) for item in (exclusions or []) if str(item or "").strip()],
    )
    return classify_candidates(candidates, context)
