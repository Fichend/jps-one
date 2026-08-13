"""Contextual assistant messages for Hunt Copilot."""

from __future__ import annotations

from hunt_copilot.conversation_guide import missing_field_labels
from hunt_copilot.schemas import CopilotSession, CopilotState
from hunt_copilot.validator import ValidationResult
from product_knowledge.taxonomy import UNCLEAR, direction_summary


class CopilotResponseBuilder:
    def build(self, session: CopilotSession, validation: ValidationResult, *, fallback: str = "") -> str:
        strategy = session.strategy
        if fallback.strip():
            return _with_validation_hint(fallback.strip(), validation)
        if session.state == CopilotState.STRATEGY_READY:
            return self._strategy_ready(session)
        if session.state == CopilotState.WAITING_STRATEGY_CONFIRMATION:
            return "策略已经确认。下一步请点击通道检查，我会先验证 Tavily、Google Maps、Instagram、Facebook 和网页补全通道。"
        if session.state == CopilotState.PREVIEW_COMPLETED:
            return "通道已经通过，预检计划也准备好了。确认正式执行后，系统会先汇总候选池，再按多源证据和 JPS 评分筛 Top N。"
        if validation.missing_fields:
            return self._collecting(session, validation)
        if strategy.product_keywords and strategy.customer_types and strategy.target_regions:
            return self._nearly_ready(session)
        return "我会先按目标、硬条件、数量预算、执行规则这 4 步整理策略；确认前不会调用搜索 API。"

    def _collecting(self, session: CopilotSession, validation: ValidationResult) -> str:
        strategy = session.strategy
        parts = []
        if strategy.target_regions:
            parts.append("地区：" + "、".join(strategy.target_regions))
        if strategy.customer_types:
            parts.append("客户：" + "、".join(strategy.customer_types))
        if strategy.exclusions:
            parts.append("排除：" + "、".join(strategy.exclusions))
        if strategy.application_scenarios:
            parts.append("应用场景：" + "、".join(strategy.application_scenarios))
        understood = "；".join(parts) if parts else "我还需要先理解你的目标市场和客户类型"
        missing = "、".join(missing_field_labels(validation))
        if "target_regions" in validation.missing_fields or "customer_types" in validation.missing_fields:
            missing_targets = []
            if "target_regions" in validation.missing_fields:
                missing_targets.append("目标地区")
            if "customer_types" in validation.missing_fields:
                missing_targets.append("客户类型")
            return f"已理解：{understood}。还需要先确认{'和'.join(missing_targets)}；有了目标后，我再帮你确认产品和硬条件。"
        if "product_keywords" in validation.missing_fields and strategy.customer_types:
            suggested = _keyword_text(strategy)
            catalogue = "基于 JPS 产品目录，" if suggested else ""
            return f"已理解：{understood}。{catalogue}还需要确认产品关键词；建议先用 {suggested or 'dental simulator、phantom head、dental teaching equipment'}。"
        if "required_fields" in validation.missing_fields:
            return f"已理解：{understood}。现在请确认硬条件：哪些字段没有就不能入选，例如 Instagram、邮箱、电话。"
        return f"已理解：{understood}。还需要确认：{missing}。"

    def _strategy_ready(self, session: CopilotSession) -> str:
        strategy = session.strategy
        required = strategy.hard_filters.enabled_labels()
        skill = session.selected_skill.skill.name if session.selected_skill else "通用 B2B 搜索"
        product_note = _product_note(strategy)
        direction = _direction_note(strategy)
        history_note = f"我也找到了 {len(session.similar_history)} 条相似历史会话，可在左侧复用参考。" if session.similar_history else ""
        return (
            "策略卡已整理好。"
            f"{product_note}"
            f"{direction}"
            f"目标地区 {', '.join(strategy.target_regions)}，"
            f"目标客户 {', '.join(strategy.customer_types)}，"
            f"应用场景 {', '.join(strategy.application_scenarios) if strategy.application_scenarios else '未设置'}，"
            f"硬条件 {', '.join(required) if required else '未设置'}。"
            f"我会先找 {strategy.budget.max_candidates} 个候选，再按 JPS 评分筛 Top {strategy.budget.final_leads}。"
            f"{history_note}当前使用 {skill}，请在右侧确认策略卡。"
        )

    def _nearly_ready(self, session: CopilotSession) -> str:
        strategy = session.strategy
        exclusions = f"排除 {', '.join(strategy.exclusions)}。" if strategy.exclusions else ""
        return (
            "核心策略已经齐了。"
            f"{_product_note(strategy)}"
            f"{_direction_note(strategy)}"
            f"{exclusions}右侧策略卡已经同步更新；确认后我会先检查通道，不会直接消耗正式预算。"
        )


def _keyword_text(strategy) -> str:
    values = strategy.product_keywords or []
    if not values and strategy.product_knowledge_summary:
        values = strategy.product_knowledge_summary.split("建议关键词：")[-1].split("；")[0].split("、")
    return "、".join([str(item).strip() for item in values[:5] if str(item).strip()])


def _product_note(strategy) -> str:
    if not strategy.product_knowledge_summary:
        return ""
    return "基于 JPS 产品目录，" + strategy.product_knowledge_summary + "。"


def _direction_note(strategy) -> str:
    if strategy.product_department == UNCLEAR and strategy.product_category == UNCLEAR:
        return ""
    return "搜索方向已锁定为 " + direction_summary(strategy.product_department, strategy.product_category) + "。"


def _with_validation_hint(message: str, validation: ValidationResult) -> str:
    hints: list[str] = []
    if validation.missing_fields:
        hints.append("还需要确认" + "、".join(missing_field_labels(validation)) + "。")
    if validation.detected_conflicts:
        hints.append("需要处理冲突：" + "；".join(validation.detected_conflicts) + "。")
    if validation.blocking_errors:
        hints.append("阻断项：" + "；".join(validation.blocking_errors) + "。")
    if not hints:
        return message
    normalized = message.rstrip("。.!！") + "。"
    for hint in hints:
        if hint not in normalized:
            normalized += hint
    return normalized
