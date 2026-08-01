"""Authoritative validation for Hunt Copilot strategy and execution gates."""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from hunt_copilot.schemas import HuntStrategy


@dataclass(frozen=True)
class ValidationResult:
    missing_fields: list[str]
    detected_conflicts: list[str]
    blocking_errors: list[str]
    warnings: list[str]

    @property
    def can_confirm_strategy(self) -> bool:
        return not self.missing_fields and not self.blocking_errors


class StrategyValidator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate(self, strategy: HuntStrategy) -> ValidationResult:
        missing: list[str] = []
        conflicts: list[str] = []
        blocking: list[str] = []
        warnings: list[str] = []
        if not strategy.target_regions:
            missing.append("target_regions")
        if not strategy.customer_types:
            missing.append("customer_types")
        if not strategy.product_keywords:
            missing.append("product_keywords")
        if not strategy.hard_filters.enabled_labels():
            missing.append("required_fields")
        exclusions = {item.lower().strip() for item in strategy.exclusions}
        bad_targets = [item for item in strategy.customer_types if any(item.lower().strip() == ex or item.lower().strip() in ex or ex in item.lower().strip() for ex in exclusions)]
        if bad_targets:
            conflicts.append("排除对象不能进入目标客户：" + "、".join(bad_targets))
            blocking.append("请先移除与排除对象冲突的目标客户。")
        if strategy.budget.final_leads > strategy.budget.max_candidates:
            blocking.append("最终客户数不能大于候选池数量。")
        if strategy.budget.preview_total_usd > strategy.budget.total_usd:
            blocking.append("预检预算不能大于正式预算。")
        if strategy.hard_filters.require_instagram and not self.settings.apify_token:
            warnings.append("Instagram 是硬条件，Apify Token 未配置时会阻断通道检查。")
        if strategy.hard_filters.require_facebook and not self.settings.apify_token:
            warnings.append("Facebook 是硬条件，Apify Token 未配置时会阻断通道检查。")
        return ValidationResult(missing, conflicts, blocking, warnings)

    def can_check_channels(self, strategy: HuntStrategy) -> tuple[bool, str]:
        result = self.validate(strategy)
        if not strategy.strategy_confirmed:
            return False, "策略卡尚未确认，不能检查通道。"
        if not result.can_confirm_strategy:
            return False, "策略卡仍有缺失或冲突，不能检查通道。"
        return True, ""

    def can_execute(self, strategy: HuntStrategy, *, preview_ready: bool, automation_job_id: str = "") -> tuple[bool, str]:
        if automation_job_id:
            return False, "同一个 Copilot session 已经创建过正式 Hunt 任务。"
        if not strategy.strategy_confirmed:
            return False, "策略卡尚未确认，不能正式执行。"
        if not preview_ready:
            return False, "预检未完成，不能正式执行。"
        return True, ""
