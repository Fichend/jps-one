"""Natural-language responses for the semantic Hunt Copilot."""

from __future__ import annotations

from hunt_copilot.schemas import HuntStrategy
from product_knowledge.taxonomy import CATEGORY_LABELS, DEPARTMENT_LABELS, UNCLEAR


class SemanticResponseComposer:
    def compose(
        self,
        *,
        strategy: HuntStrategy,
        changed: bool,
        recent_changes: list[str],
        missing_fields: list[str],
        detected_conflicts: list[str],
        rejected_fields: dict[str, list[str]],
    ) -> str:
        if not changed and not detected_conflicts:
            return self._no_change(strategy, missing_fields)

        lines: list[str] = []
        if strategy.target_regions or strategy.customer_types or strategy.application_scenarios:
            lines.append("已理解，我先把你的需求整理成可执行的搜索策略。")
        else:
            lines.append("我理解了，但这句话里还没有足够的搜索条件。")

        summary = self._summary_lines(strategy)
        if summary:
            lines.append("当前已记录：")
            lines.extend(summary)

        if rejected_fields.get("product_keywords"):
            lines.append("我已拦截一处字段误写：这些内容不像 JPS 产品关键词，已改放到业务说明/应用场景里。")

        if detected_conflicts:
            lines.append("需要注意：" + "；".join(detected_conflicts))

        next_step = self._next_step(missing_fields, strategy)
        if next_step:
            lines.append(next_step)
        elif recent_changes:
            lines.append("右侧策略卡已同步更新，可以继续确认策略。")
        return "\n".join(lines)

    @staticmethod
    def _summary_lines(strategy: HuntStrategy) -> list[str]:
        rows: list[str] = []
        if strategy.target_regions:
            rows.append("- 地区：" + _join(strategy.target_regions))
        if strategy.customer_types:
            rows.append("- 客户：" + _join(strategy.customer_types))
        if strategy.application_scenarios:
            rows.append("- 应用场景：" + _join(strategy.application_scenarios))
        if strategy.product_keywords:
            rows.append("- JPS 产品：" + _join(strategy.product_keywords))
        if strategy.product_department != UNCLEAR or strategy.product_category != UNCLEAR:
            rows.append(
                "- 搜索方向："
                + DEPARTMENT_LABELS.get(strategy.product_department, strategy.product_department)
                + " / "
                + CATEGORY_LABELS.get(strategy.product_category, strategy.product_category)
            )
        if strategy.exclusions:
            rows.append("- 排除：" + _join(strategy.exclusions))
        required = strategy.hard_filters.enabled_labels()
        if required:
            rows.append("- 重点补全：" + _join(required))
        return rows

    @staticmethod
    def _next_step(missing_fields: list[str], strategy: HuntStrategy) -> str:
        if "target_regions" in missing_fields and "product_keywords" in missing_fields:
            return "还需要确认目标地区和 JPS 产品关键词。你可以直接说：地区是 Brazil，产品是 sterilization indicator。"
        if "target_regions" in missing_fields:
            return "还需要确认目标地区。你可以直接说：地区是 Brazil。"
        if "customer_types" in missing_fields:
            return "还需要确认客户类型，例如 distributor、agent、dental school 或 training center。"
        if "product_keywords" in missing_fields:
            if strategy.application_scenarios:
                return "还需要确认具体 JPS 产品关键词。比如 CSSD 场景可以用 sterilization indicator、sterilization pouch、sterilizer。"
            return "还需要确认 JPS 产品关键词，例如 dental simulator、sterilization indicator 或 medical consumables。"
        if "required_fields" in missing_fields:
            return "还需要确认重点补全字段，例如官网、邮箱、电话、Instagram。"
        return ""

    @staticmethod
    def _no_change(strategy: HuntStrategy, missing_fields: list[str]) -> str:
        next_step = SemanticResponseComposer._next_step(missing_fields, strategy)
        if next_step:
            return "这句话没有写入新的策略字段。" + next_step
        return "这句话没有改变右侧策略卡。你可以继续补充产品、客户类型、地区、数量或预算。"


def _join(values: list[str]) -> str:
    return "、".join(str(item) for item in values if str(item).strip())
