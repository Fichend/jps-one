"""Deterministic requirement parsing and strategy-card rendering.

The first version intentionally keeps execution decisions deterministic. An LLM
can later be used to suggest fields, but backend validation remains the source
of truth for state transitions, budget caps, and Hunt creation.
"""

from __future__ import annotations

import re

from hunt_copilot.schemas import HardFilters, HuntStrategy, SearchBudget
from product_knowledge import JpsProductRecommender


FIELD_PATTERNS = {
    "require_instagram": ("instagram", "ins", "ig", "insta", "小红书"),
    "require_facebook": ("facebook", "fb", "脸书"),
    "require_email": ("email", "e-mail", "邮箱", "邮件", "mail"),
    "require_phone": ("phone", "电话", "手机号", "号码", "tel", "whatsapp"),
    "require_website": ("官网", "website", "official site", "site"),
    "require_address": ("地址", "address", "location", "maps", "地图"),
}

COMMON_REGIONS = (
    "Vietnam", "Thailand", "Indonesia", "Malaysia", "Philippines", "Singapore", "India",
    "Australia", "New Zealand", "United States", "USA", "Canada", "Mexico", "Brazil",
    "Germany", "France", "Italy", "Spain", "United Kingdom", "UK", "UAE", "Saudi Arabia",
    "Japan", "Korea", "South Korea", "越南", "泰国", "印尼", "马来西亚", "菲律宾", "新加坡",
    "印度", "澳大利亚", "美国", "加拿大", "德国", "法国", "意大利", "西班牙", "英国", "日本", "韩国",
)

EXCLUSION_MARKERS = ("排除", "不要", "不需要", "exclude", "not ", "without")


def infer_strategy(text: str, current: HuntStrategy | None = None) -> HuntStrategy:
    strategy = current.model_copy(deep=True) if current else HuntStrategy()
    clean_text = str(text or "").strip()
    if clean_text:
        strategy.raw_requirement = (strategy.raw_requirement + "\n" + clean_text).strip()

    lower = clean_text.lower()
    for region in COMMON_REGIONS:
        if region.lower() in lower or region in clean_text:
            if region not in strategy.target_regions:
                strategy.target_regions.append(region)

    for field, patterns in FIELD_PATTERNS.items():
        if any(pattern.lower() in lower for pattern in patterns):
            setattr(strategy.hard_filters, field, True)

    _merge_exclusions(strategy, clean_text)
    _merge_customer_and_product_knowledge(strategy, clean_text)
    _merge_keywords(strategy, clean_text)
    _remove_excluded_targets(strategy)
    _merge_budget(strategy, clean_text)
    return strategy.model_validate(strategy.model_dump())


def missing_groups(strategy: HuntStrategy) -> list[str]:
    missing: list[str] = []
    if not strategy.target_regions or not strategy.customer_types or not strategy.product_keywords:
        missing.append("target")
    if not strategy.hard_filters.enabled_labels():
        missing.append("required_fields")
    if strategy.budget.max_candidates <= 0 or strategy.budget.final_leads <= 0:
        missing.append("budget")
    return missing


def next_question(strategy: HuntStrategy, group: str) -> str:
    if group == "target":
        return (
            "第一组：请确认目标。请告诉我国家/地区、客户类型、JPS 产品关键词，以及需要排除的对象。"
            "我只做策略整理，暂不执行搜索。"
        )
    if group == "required_fields":
        return "第二组：请确认必需字段。Instagram、Facebook、邮箱、电话、官网、地址，哪些必须有才算合格客户？"
    if group == "budget":
        return "第三组：请确认预算和数量。预检预算、正式预算、最大候选数量、最终客户数量分别是多少？"
    return (
        "第四组：请确认执行规则。是否启用硬过滤？缺少必需字段时先进入待补全还是直接拒绝？"
        "确认后我会生成策略卡，等待你二次确认正式执行。"
    )


def render_strategy_card(strategy: HuntStrategy) -> str:
    required = strategy.hard_filters.enabled_labels() or ["未指定硬条件"]
    return "\n".join(
        [
            "Hunt Copilot 策略卡",
            "",
            f"目标地区：{', '.join(strategy.target_regions) or '待确认'}",
            f"目标客户：{', '.join(strategy.customer_types) or '待确认'}",
            f"产品关键词：{', '.join(strategy.product_keywords) or '待确认'}",
            f"排除对象：{', '.join(strategy.exclusions) or '无'}",
            "",
            f"必需字段：{', '.join(required)}",
            "搜索通道：默认启用 Web、Google Maps、Instagram、Facebook，业务员无需选择。",
            "",
            f"预检预算：{strategy.budget.preview_total_usd:g} USD",
            f"正式预算：{strategy.budget.total_usd:g} USD",
            f"最大候选：{strategy.budget.max_candidates}",
            f"最终客户：{strategy.budget.final_leads}",
            "",
            f"硬过滤：{'启用' if strategy.rules.hard_filter_enabled else '关闭'}",
            f"缺失字段处理：{'先待补全，补全失败拒绝' if strategy.rules.missing_required_action == 'pending_then_reject' else '直接拒绝'}",
            "候选池：先进入 candidate_pool，多源证据合并后再排序入库。",
        ]
    )


def _merge_keywords(strategy: HuntStrategy, text: str) -> None:
    quoted = re.findall(r"[\"'“”‘’]([^\"'“”‘’]{2,80})[\"'“”‘’]", text)
    candidates = quoted[:]
    exclusive_match = re.search(r"(?:只要|只用|只保留|就用|only|use only)\s*([a-zA-Z][a-zA-Z0-9\-\s]{2,60})", text, flags=re.IGNORECASE)
    if exclusive_match:
        keyword = exclusive_match.group(1).strip(" 。.;；,，")
        if keyword:
            strategy.product_keywords = [keyword]
            return
    keyword_match = re.search(r"(?:产品关键词|关键词|产品|推广产品|product keywords?|products?)[:：是为]?\s*([^。\n]+)", text, flags=re.IGNORECASE)
    if keyword_match:
        parts = re.split(r"[,，;；、/]", keyword_match.group(1))
        candidates.extend(part.strip() for part in parts if 2 <= len(part.strip()) <= 60)
    for item in candidates:
        if not any(stop in item.lower() for stop in ("客户", "地区", "预算", "候选", "最终")):
            if item not in strategy.product_keywords:
                strategy.product_keywords.append(item)


def _merge_exclusions(strategy: HuntStrategy, text: str) -> None:
    lower = text.lower()
    if not any(marker in lower for marker in EXCLUSION_MARKERS):
        return
    parts = re.split(r"[,，;；、\n]", text)
    for part in parts:
        if any(marker in part.lower() for marker in EXCLUSION_MARKERS):
            item = re.sub(r"排除|不要|不需要|exclude|without|not", "", part, flags=re.IGNORECASE).strip()
            if item and item not in strategy.exclusions:
                strategy.exclusions.append(item)


def _merge_customer_and_product_knowledge(strategy: HuntStrategy, text: str) -> None:
    recommender = JpsProductRecommender()
    normalized_exclusions = recommender.normalize_exclusions(strategy.exclusions, text=text)
    normalized_targets = recommender.normalize_customer_types(strategy.customer_types, text=text)
    if normalized_exclusions:
        strategy.exclusions = normalized_exclusions
    if normalized_targets:
        strategy.customer_types = normalized_targets
    recommendation = recommender.recommend(
        customer_types=strategy.customer_types,
        exclusions=strategy.exclusions,
        product_keywords=strategy.product_keywords,
        user_requirement=text or strategy.raw_requirement,
    )
    if recommendation.normalized_customer_types:
        strategy.customer_types = recommendation.normalized_customer_types
    if recommendation.normalized_exclusions:
        strategy.exclusions = recommendation.normalized_exclusions
    # Catalogue matches are recommendations only. The authoritative
    # product_keywords field changes only after an explicit user instruction.


def _remove_excluded_targets(strategy: HuntStrategy) -> None:
    exclusions = {item.lower().strip() for item in strategy.exclusions}
    if not exclusions:
        return
    cleaned = []
    for item in strategy.customer_types:
        lower = item.lower().strip()
        if any(lower == excluded or lower in excluded or excluded in lower for excluded in exclusions):
            continue
        cleaned.append(item)
    strategy.customer_types = cleaned


def _merge_budget(strategy: HuntStrategy, text: str) -> None:
    lower = text.lower()
    money = [float(match) for match in re.findall(r"(\d+(?:\.\d+)?)\s*(?:usd|美金|美元|\$)", lower)]
    if money:
        if "预检" in text or "preview" in lower:
            strategy.budget.preview_total_usd = money[0]
            if len(money) > 1:
                strategy.budget.total_usd = money[1]
        else:
            strategy.budget.total_usd = money[-1]
            strategy.budget.apify_task_max_total_charge_usd = money[-1]
    final_match = re.search(r"(?:最终|入库|要|需要|top)\s*(\d+)\s*(?:个|条|家|leads|customers)?", lower)
    if final_match:
        strategy.budget.final_leads = int(final_match.group(1))
    candidate_match = re.search(r"(?:候选|比较|candidate|max candidates?)\s*(?:池|先找|客户|个|条|家)?\s*(\d+)", lower)
    if candidate_match:
        strategy.budget.max_candidates = int(candidate_match.group(1))
    if strategy.budget.max_candidates < strategy.budget.final_leads:
        strategy.budget.max_candidates = max(strategy.budget.final_leads * 4, strategy.budget.final_leads)
