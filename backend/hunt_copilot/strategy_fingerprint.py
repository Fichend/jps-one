"""Stable strategy fingerprinting for repeatable Hunt Copilot execution."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from hunt_copilot.schemas import HuntStrategy


def strategy_fingerprint(strategy: HuntStrategy) -> str:
    payload = {
        "regions": _norm_list(strategy.target_regions),
        "customers": _norm_list(strategy.customer_types),
        "products": _norm_list(strategy.product_keywords),
        "department": strategy.product_department,
        "category": strategy.product_category,
        "exclusions": _norm_list(strategy.exclusions),
        "required": _norm_list(strategy.hard_filters.enabled_labels()),
        "final_leads": int(strategy.budget.final_leads),
        "max_candidates": int(strategy.budget.max_candidates),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def strategy_similarity(left: HuntStrategy, right: HuntStrategy) -> float:
    scores = [
        _jaccard(_norm_list(left.target_regions), _norm_list(right.target_regions)),
        _jaccard(_norm_list(left.customer_types), _norm_list(right.customer_types)),
        _jaccard(_norm_list(left.product_keywords), _norm_list(right.product_keywords)),
        1.0 if left.product_department == right.product_department else 0.0,
        1.0 if left.product_category == right.product_category else 0.0,
        _jaccard(_norm_list(left.hard_filters.enabled_labels()), _norm_list(right.hard_filters.enabled_labels())),
    ]
    weights = [0.24, 0.24, 0.2, 0.12, 0.08, 0.12]
    return round(sum(score * weight for score, weight in zip(scores, weights, strict=False)), 3)


def canonical_strategy_terms(strategy: HuntStrategy) -> dict[str, list[str]]:
    return {
        "regions": _norm_list(strategy.target_regions),
        "customers": _norm_list(strategy.customer_types),
        "products": _norm_list(strategy.product_keywords),
        "department": [strategy.product_department],
        "category": [strategy.product_category],
        "exclusions": _norm_list(strategy.exclusions),
        "required": _norm_list(strategy.hard_filters.enabled_labels()),
    }


def _norm_list(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "").strip().lower())
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return sorted(result)


def _jaccard(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)
