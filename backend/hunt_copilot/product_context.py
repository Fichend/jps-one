"""JPS catalogue context for Hunt Copilot planning and replies."""

from __future__ import annotations

from dataclasses import dataclass, field

from hunt_copilot.schemas import HuntStrategy
from product_knowledge import JpsProductRecommender


@dataclass(frozen=True)
class ProductContext:
    recommended_keywords: list[str] = field(default_factory=list)
    matched_families: list[str] = field(default_factory=list)
    normalized_customer_types: list[str] = field(default_factory=list)
    normalized_exclusions: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    summary_zh: str = ""

    def as_prompt_context(self) -> dict[str, object]:
        return {
            "recommended_keywords": self.recommended_keywords,
            "matched_families": self.matched_families,
            "normalized_customer_types": self.normalized_customer_types,
            "normalized_exclusions": self.normalized_exclusions,
            "reasons": self.reasons,
            "summary_zh": self.summary_zh,
        }


class JpsProductContextBuilder:
    def __init__(self, recommender: JpsProductRecommender | None = None) -> None:
        self.recommender = recommender or JpsProductRecommender()

    def build(self, strategy: HuntStrategy, *, message: str = "") -> ProductContext:
        requirement = "\n".join(part for part in [strategy.raw_requirement, message] if part.strip())
        recommendation = self.recommender.recommend(
            customer_types=strategy.customer_types,
            exclusions=strategy.exclusions,
            product_keywords=strategy.product_keywords,
            user_requirement=requirement,
        )
        summary = self._summary(recommendation.recommended_keywords, recommendation.matched_families, recommendation.reasons)
        return ProductContext(
            recommended_keywords=recommendation.recommended_keywords,
            matched_families=recommendation.matched_families,
            normalized_customer_types=recommendation.normalized_customer_types,
            normalized_exclusions=recommendation.normalized_exclusions,
            reasons=recommendation.reasons,
            summary_zh=summary,
        )

    @staticmethod
    def _summary(keywords: list[str], families: list[str], reasons: list[str]) -> str:
        parts: list[str] = []
        if families:
            parts.append("匹配产品线：" + "、".join(families[:3]))
        if keywords:
            parts.append("建议关键词：" + "、".join(keywords[:5]))
        if reasons:
            parts.append(reasons[0])
        return "；".join(parts)
