"""Deterministic strategy review for Hunt Copilot."""

from __future__ import annotations

from config.settings import Settings
from hunt_copilot.schemas import HuntStrategy, SearchSkillSelection, StrategyCriticNote
from hunt_copilot.validator import ValidationResult


class StrategyCritic:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def review(
        self,
        strategy: HuntStrategy,
        validation: ValidationResult,
        selected_skill: SearchSkillSelection | None = None,
    ) -> list[StrategyCriticNote]:
        notes: list[StrategyCriticNote] = []
        for field in validation.missing_fields:
            notes.append(
                StrategyCriticNote(
                    level="blocking",
                    title="缺少必填策略项",
                    message=f"{field} 还没有确认，不能进入通道检查或正式搜索。",
                    impact="避免任务在关键词或目标不清楚时消耗搜索预算。",
                    suggested_fix="在左侧补充需求，或直接编辑右侧策略卡。",
                )
            )
        for conflict in [*validation.detected_conflicts, *validation.blocking_errors]:
            notes.append(
                StrategyCriticNote(
                    level="blocking",
                    title="策略冲突",
                    message=conflict,
                    impact="冲突会导致目标客户和排除对象互相抵消。",
                    suggested_fix="保留真实目标客户，把不想要的客户放到排除对象。",
                )
            )

        hard_count = len(strategy.hard_filters.enabled_labels())
        if hard_count >= 4:
            notes.append(
                StrategyCriticNote(
                    level="warning",
                    title="硬条件较多",
                    message="当前必需字段较多，候选命中率会明显下降。",
                    impact="可能搜索到足够候选，但最终通过硬过滤的客户少于目标数量。",
                    suggested_fix="把非必须字段移到优先字段，正式排序时仍会加分。",
                )
            )
        if strategy.hard_filters.require_instagram and not self.settings.apify_token:
            notes.append(
                StrategyCriticNote(
                    level="blocking",
                    title="Instagram 通道未配置",
                    message="Instagram 是硬条件，但 Apify Token 未配置。",
                    impact="通道检查会失败，不能保证 Instagram 账号主页搜索。",
                    suggested_fix="在配置中心填写 Apify Token。",
                )
            )
        if strategy.hard_filters.require_facebook and not self.settings.apify_token:
            notes.append(
                StrategyCriticNote(
                    level="blocking",
                    title="Facebook 通道未配置",
                    message="Facebook 是硬条件，但 Apify Token 未配置。",
                    impact="通道检查会失败，不能保证 Facebook Page 搜索。",
                    suggested_fix="在配置中心填写 Apify Token。",
                )
            )
        if strategy.budget.max_candidates < strategy.budget.final_leads * 3:
            notes.append(
                StrategyCriticNote(
                    level="warning",
                    title="候选池偏小",
                    message="候选池数量建议至少是最终客户数的 3-4 倍。",
                    impact="候选太少时，多源合并和 JPS 评分排序没有足够比较空间。",
                    suggested_fix="例如最终 10 个客户时，候选池建议 40 个以上。",
                )
            )
        if strategy.budget.total_usd <= 1 and (strategy.hard_filters.require_instagram or strategy.hard_filters.require_facebook):
            notes.append(
                StrategyCriticNote(
                    level="info",
                    title="社媒预算提醒",
                    message="1 美元预算适合小样本验证，不适合大范围社媒主页补全。",
                    impact="Apify Actor 会受 maxItems 和费用上限保护，结果数量可能不足。",
                    suggested_fix="先跑预检，看候选质量后再提高正式预算。",
                )
            )
        if selected_skill and selected_skill.skill.risk_notes:
            notes.append(
                StrategyCriticNote(
                    level="info",
                    title="Skill 风险提示",
                    message="；".join(selected_skill.skill.risk_notes[:2]),
                    impact="这些限制会影响搜索结果覆盖率和字段完整度。",
                    suggested_fix="保持官网、地图、社媒多源合并，不用单一来源判断客户质量。",
                )
            )

        return _dedupe_notes(notes)[:8]


def _dedupe_notes(notes: list[StrategyCriticNote]) -> list[StrategyCriticNote]:
    seen: set[tuple[str, str]] = set()
    result: list[StrategyCriticNote] = []
    for note in notes:
        key = (note.level, note.message)
        if key in seen:
            continue
        seen.add(key)
        result.append(note)
    return result
