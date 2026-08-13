"""Render Hunt strategies for execution payloads and audit notes."""

from __future__ import annotations

from hunt_copilot.schemas import HuntStrategy
from product_knowledge.taxonomy import UNCLEAR, direction_summary


def render_strategy_card(strategy: HuntStrategy) -> str:
    required = strategy.hard_filters.enabled_labels() or ["未指定硬条件"]
    return "\n".join(
        [
            "Hunt Copilot 策略卡",
            "",
            f"目标地区：{', '.join(strategy.target_regions) or '待确认'}",
            f"目标客户：{', '.join(strategy.customer_types) or '待确认'}",
            f"搜索方向：{direction_summary(strategy.product_department, strategy.product_category) if strategy.product_department != UNCLEAR or strategy.product_category != UNCLEAR else '待确认'}",
            f"产品关键词：{', '.join(strategy.product_keywords) or '待确认'}",
            f"应用场景：{', '.join(strategy.application_scenarios) or '无'}",
            f"业务说明：{'；'.join(strategy.business_notes[-3:]) or '无'}",
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
