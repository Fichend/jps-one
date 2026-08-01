"""Apply JPS scoring to API response objects when stored rows predate scoring."""

from __future__ import annotations

from typing import Any

from scoring.lead_scorer import apply_score


def ensure_jps_score(item: dict[str, Any]) -> dict[str, Any]:
    """Return a scored copy, preserving existing explicit score fields."""

    scored = dict(item)
    has_score = isinstance(scored.get("jps_score"), (int, float)) and str(scored.get("lead_grade") or "").strip()
    if has_score and isinstance(scored.get("score_breakdown"), dict) and scored.get("score_breakdown"):
        return scored
    return apply_score(scored)


def ensure_jps_scores(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [ensure_jps_score(item) if isinstance(item, dict) else item for item in items]
