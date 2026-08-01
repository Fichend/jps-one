"""Quality summary for candidate pools and final lead selection."""

from __future__ import annotations

from typing import Any

from candidate_pool.ranking import enabled_required_fields, has_field


def build_candidate_quality_summary(
    *,
    candidates: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    rejected_candidates: list[dict[str, Any]] | None = None,
    target_final_leads: int = 10,
    hard_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rejected = rejected_candidates or []
    selected = _top_candidates(candidates, target_final_leads)
    final_leads = _top_candidates(leads, target_final_leads)
    preferred = _required_labels(hard_filters or {})
    grade_counts = _grade_counts(candidates)
    selected_grade_counts = _grade_counts(selected)
    coverage = {field: _coverage(selected, field) for field in preferred}
    channel_counts = _channel_counts(candidates)
    status_counts = _status_counts(candidates)
    selected_ready = sum(1 for item in selected if _meets_required(item, preferred))
    lead_ready = sum(1 for item in final_leads if _meets_required(item, preferred))
    gaps = _gaps(preferred, coverage, selected_ready, target_final_leads, channel_counts)
    return {
        "status": _status(selected_ready, target_final_leads, gaps),
        "total_candidates": len(candidates),
        "selected_candidates": len(selected),
        "target_final_leads": target_final_leads,
        "final_leads": len(final_leads),
        "selected_ready_count": selected_ready,
        "final_ready_count": lead_ready,
        "rejected_count": len(rejected),
        "recommended_count": status_counts.get("recommended", 0),
        "backup_count": status_counts.get("backup", 0),
        "needs_enrichment_count": status_counts.get("needs_enrichment", 0),
        "low_confidence_count": status_counts.get("low_confidence", 0),
        "excluded_by_rule_count": status_counts.get("excluded_by_rule", 0),
        "status_counts": status_counts,
        "grade_counts": grade_counts,
        "selected_grade_counts": selected_grade_counts,
        "required_fields": preferred,
        "required_coverage": coverage,
        "preferred_fields": preferred,
        "preferred_coverage": coverage,
        "channel_counts": channel_counts,
        "gaps": gaps,
        "recommendations": _recommendations(gaps, preferred, channel_counts),
        "summary_text": _summary_text(selected_ready, target_final_leads, grade_counts, coverage, gaps),
    }


def _top_candidates(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(
        [item for item in items if isinstance(item, dict)],
        key=lambda item: (
            int(item.get("ranking_score", 0) or 0),
            int(item.get("jps_score", 0) or 0),
            float(item.get("confidence", item.get("fit_score", 0)) or 0),
        ),
        reverse=True,
    )[: max(1, int(limit or 10))]


def _grade_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for item in items:
        grade = str(item.get("lead_grade") or "D").upper()[:1]
        counts[grade if grade in counts else "D"] += 1
    return counts


def _required_labels(hard_filters: dict[str, Any]) -> list[str]:
    return enabled_required_fields(hard_filters)


def _coverage(items: list[dict[str, Any]], field: str) -> dict[str, Any]:
    count = sum(1 for item in items if _has_field(item, field))
    total = len(items)
    return {"count": count, "total": total, "rate": round(count / total, 3) if total else 0.0}


def _has_field(item: dict[str, Any], field: str) -> bool:
    return has_field(item, field)


def _social(item: dict[str, Any], provider: str) -> str:
    social = item.get("social_media") if isinstance(item.get("social_media"), dict) else {}
    return str(social.get(provider) or social.get(provider.title()) or "").strip()


def _meets_required(item: dict[str, Any], required: list[str]) -> bool:
    return all(_has_field(item, field) for field in required)


def _channel_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        sources = item.get("source_channels") if isinstance(item.get("source_channels"), list) else []
        source = str(item.get("source") or "").strip()
        for channel in [*sources, source]:
            clean = str(channel or "").strip()
            if clean:
                counts[clean] = counts.get(clean, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: pair[1], reverse=True))


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("candidate_status") or "unclassified").strip() or "unclassified"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: pair[1], reverse=True))


def _gaps(required: list[str], coverage: dict[str, dict[str, Any]], ready: int, target: int, channels: dict[str, int]) -> list[str]:
    gaps: list[str] = []
    if ready < target:
        gaps.append(f"重点字段覆盖完整的 Top 候选为 {ready}/{target} 个")
    for field in required:
        stat = coverage.get(field, {})
        if float(stat.get("rate", 0) or 0) < 0.8:
            gaps.append(f"{_label(field)} 覆盖不足：{int(stat.get('count', 0) or 0)}/{int(stat.get('total', 0) or 0)}")
    if "instagram" in required and not any("instagram" in key for key in channels):
        gaps.append("Instagram 通道没有贡献候选")
    if "facebook" in required and not any("facebook" in key for key in channels):
        gaps.append("Facebook 通道没有贡献候选")
    return gaps


def _recommendations(gaps: list[str], required: list[str], channels: dict[str, int]) -> list[str]:
    recs: list[str] = []
    if any("Instagram" in gap or "instagram" in gap for gap in gaps):
        recs.append("优先检查 Apify Instagram Actor 是否实际返回账号主页，并提高候选池数量。")
    if any("邮箱" in gap or "email" in gap for gap in gaps):
        recs.append("增加官网/目录页补全；邮箱缺失的候选保留在候补池并降权排序。")
    if any("电话" in gap or "phone" in gap for gap in gaps):
        recs.append("优先使用 Google Maps 和公开官网 Contact 页面补电话。")
    if not recs and required:
        recs.append("当前重点字段覆盖较好，可以进入人工复核或客户池导入。")
    if not channels:
        recs.append("未看到来源通道统计，请确认任务是否已完成搜索阶段。")
    return recs[:4]


def _summary_text(ready: int, target: int, grades: dict[str, int], coverage: dict[str, dict[str, Any]], gaps: list[str]) -> str:
    if not grades and not coverage:
        return "候选池质量信息暂未生成。"
    grade_text = f"A/B/C/D = {grades.get('A', 0)}/{grades.get('B', 0)}/{grades.get('C', 0)}/{grades.get('D', 0)}"
    if gaps:
        return f"重点字段覆盖完整 {ready}/{target}；{grade_text}；主要缺口：{gaps[0]}。"
    return f"重点字段覆盖完整 {ready}/{target}；{grade_text}；候选质量达到当前策略要求。"


def _status(ready: int, target: int, gaps: list[str]) -> str:
    if ready >= target and not gaps:
        return "good"
    if ready > 0:
        return "needs_review"
    return "insufficient"


def _label(field: str) -> str:
    return {
        "instagram": "Instagram",
        "facebook": "Facebook",
        "email": "邮箱",
        "phone": "电话",
        "website": "官网",
        "address": "地址",
    }.get(field, field)
