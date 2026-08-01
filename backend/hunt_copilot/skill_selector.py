"""Rule-first Search Skill selector for Hunt Copilot."""

from __future__ import annotations

from hunt_copilot.schemas import HuntStrategy, SearchSkillSelection
from hunt_copilot.search_skills import get_search_skill, list_search_skills


class SearchSkillSelector:
    """Select a JPS-specific search skill without spending LLM tokens."""

    def select(self, *, text: str = "", strategy: HuntStrategy | None = None) -> SearchSkillSelection:
        strategy = strategy or HuntStrategy()
        haystack = "\n".join(
            [
                text or "",
                strategy.raw_requirement or "",
                " ".join(strategy.customer_types),
                " ".join(strategy.product_keywords),
                " ".join(strategy.exclusions),
            ]
        ).lower()

        scores: dict[str, int] = {skill.id: 0 for skill in list_search_skills()}
        for skill in list_search_skills():
            for signal in [*skill.applicable_intents, *skill.target_company_types, *skill.default_product_categories]:
                clean = signal.lower().strip()
                if clean and clean in haystack:
                    scores[skill.id] += 3

        if any(term in haystack for term in ("medical consumables", "medical disposables", "医疗耗材", "医用耗材", "医院耗材", "手术衣", "灭菌袋", "医用胶带", "纱布")):
            scores["medical_consumables_distributor_search"] += 8
        if any(term in haystack for term in ("dental school", "dental college", "牙科学校", "牙科培训", "口腔院校", "phantom head", "dental simulator")):
            scores["dental_school_search"] += 8
        if any(term in haystack for term in ("dental distributor", "dental dealer", "牙科设备经销商", "牙科经销商", "dental equipment distributor")):
            scores["dental_distributor_search"] += 8

        primary_id = max(scores, key=scores.get)
        if scores[primary_id] <= 0:
            primary_id = "general_b2b_search"
        primary = get_search_skill(primary_id) or get_search_skill("general_b2b_search")
        overlays = []
        if strategy.hard_filters.require_instagram or strategy.hard_filters.require_facebook or any(term in haystack for term in ("instagram", "facebook", "ins", "fb", "社媒", "脸书")):
            social = get_search_skill("social_required_search")
            if social and social.id != primary.id:
                overlays.append(social)

        reason = f"根据目标客户、产品关键词和原始需求选择 {primary.name}。"
        if overlays:
            reason += " 同时叠加社媒硬条件约束。"
        return SearchSkillSelection(skill=primary, overlays=overlays, reason=reason)
