"""Compile confirmed HuntStrategy into a stable internal tool plan.

The plan is intentionally deterministic. Similar confirmed strategies should
produce the same ordered discovery queries and the same ordered tools, so the
same business request does not drift between runs just because the LLM phrased a
field slightly differently.
"""

from __future__ import annotations

from hunt_copilot.schemas import HuntStrategy, ToolPlan, ToolPlanStep
from hunt_copilot.strategy_fingerprint import strategy_fingerprint
from product_knowledge.taxonomy import (
    CSSD_STERILIZATION,
    DENTAL,
    DENTAL_CONSUMABLES,
    DENTAL_EQUIPMENT,
    DENTAL_TEACHING_LAB,
    MEDICAL_CONSUMABLES,
    MEDICAL_PPE_CONSUMABLES,
    SURGICAL_PACKS,
)
from search_tools.locale_keyword_expander import LocaleKeywordExpander


class SearchPlanCompiler:
    def compile(self, strategy: HuntStrategy, *, created_by: str = "fallback") -> ToolPlan:
        queries = self._queries(strategy)
        per_tool_results = max(5, min(20, strategy.budget.max_candidates // 4 or 10))
        steps: list[ToolPlanStep] = []
        for query in queries:
            steps.extend(self._discovery_steps_for_query(query, per_tool_results))
        steps.extend(self._candidate_enrichment_steps(strategy))
        steps.append(
            ToolPlanStep(
                tool="evidence.search.opensearch",
                query=self._objective(strategy),
                max_results=min(20, strategy.budget.max_candidates),
                purpose="复用历史证据，减少重复搜索同一客户",
                phase="evidence",
                execution_mode="disabled",
            )
        )
        selected = steps[:32]
        return ToolPlan(
            objective=self._objective(strategy),
            steps=selected,
            estimated_max_results=sum(step.max_results for step in selected if step.execution_mode == "search_phase"),
            requires_user_confirmation=True,
            created_by="minimax" if created_by == "minimax" else "fallback",
            plan_hash=strategy_fingerprint(strategy),
            summary=self._summary(strategy, queries, selected),
        )

    def _discovery_steps_for_query(self, query: str, per_tool_results: int) -> list[ToolPlanStep]:
        clean_query = _clean_discovery_query(query)
        return [
            ToolPlanStep(
                tool="web.search.tavily",
                query=clean_query,
                max_results=per_tool_results,
                purpose="发现官网、目录和公开公司实体",
                phase="discovery",
                execution_mode="search_phase",
            ),
            ToolPlanStep(
                tool="local.search.google_maps",
                query=clean_query,
                max_results=per_tool_results,
                purpose="补充地图实体、地址、电话和官网",
                phase="discovery",
                execution_mode="search_phase",
            ),
        ]

    def _candidate_enrichment_steps(self, strategy: HuntStrategy) -> list[ToolPlanStep]:
        objective = self._objective(strategy)
        return [
            ToolPlanStep(
                tool="web.extract.tavily",
                query=objective,
                max_results=5,
                purpose="候选客户已有官网后，按官网抽取邮箱、电话、地址和社媒链接",
                phase="enrichment",
                execution_mode="candidate_enrichment",
            ),
            ToolPlanStep(
                tool="web.crawl.tavily",
                query=objective,
                max_results=5,
                purpose="候选客户已有官网后，按官网站内爬取联系页、关于页和社媒入口",
                phase="enrichment",
                execution_mode="candidate_enrichment",
            ),
            ToolPlanStep(
                tool="social.search.instagram.apify",
                query=objective,
                max_results=5,
                purpose="候选客户实体确认后，按公司名补充公开 Instagram 主页；不作为主发现渠道",
                phase="enrichment",
                execution_mode="candidate_enrichment",
            ),
            ToolPlanStep(
                tool="social.search.facebook.apify",
                query=objective,
                max_results=5,
                purpose="候选客户实体确认后，按公司名补充公开 Facebook Page；不作为主发现渠道",
                phase="enrichment",
                execution_mode="candidate_enrichment",
            ),
        ]

    def _queries(self, strategy: HuntStrategy) -> list[str]:
        regions = sorted(strategy.target_regions or [""])
        customers = sorted(strategy.customer_types or [""])
        products = sorted(strategy.product_keywords or [""])
        queries: list[str] = []
        queries.extend(
            _target_type_templates(
                regions,
                customers,
                products,
                department=strategy.product_department,
                category=strategy.product_category,
                scenarios=strategy.application_scenarios,
            )
        )
        for region in regions[:2]:
            for customer in customers[:2]:
                for product in products[:2]:
                    query = " ".join(part for part in (region, product, customer) if part).strip()
                    if query and query not in queries:
                        queries.append(query)
        base = queries or [strategy.raw_requirement or "JPS customer search"]
        # Contact/social fields are enrichment targets. They must not be injected
        # into entity discovery queries, because terms like "email phone
        # Instagram" push search tools toward generic social help pages instead
        # of real customer entities.
        return LocaleKeywordExpander().expand(
            base_keywords=base,
            target_regions=strategy.target_regions,
            customer_profile=" ".join(strategy.customer_types),
            product_keywords=strategy.product_keywords,
            hard_filters={},
            max_keywords=max(4, min(8, strategy.budget.max_candidates // 8 or 4)),
        )

    @staticmethod
    def _objective(strategy: HuntStrategy) -> str:
        parts = [", ".join(sorted(strategy.target_regions)), ", ".join(sorted(strategy.customer_types)), ", ".join(sorted(strategy.product_keywords))]
        return " | ".join(part for part in parts if part) or strategy.raw_requirement or "JPS lead search"

    @staticmethod
    def _summary(strategy: HuntStrategy, queries: list[str], steps: list[ToolPlanStep]) -> str:
        discovery_tools = sorted({step.tool for step in steps if step.execution_mode == "search_phase"})
        enrichment_tools = sorted({step.tool for step in steps if step.execution_mode == "candidate_enrichment"})
        return (
            f"{len(queries)} 组标准发现查询，{len(discovery_tools)} 类发现工具；"
            f"候选合并后再用 {len(enrichment_tools)} 类补全工具；"
            f"候选池 {strategy.budget.max_candidates}，最终 Top {strategy.budget.final_leads}。"
        )

_DISCOVERY_NOISE_TERMS = {
    "email",
    "e-mail",
    "mail",
    "phone",
    "telephone",
    "tel",
    "contact",
    "contacts",
    "instagram",
    "facebook",
    "linkedin",
    "whatsapp",
    "twitter",
    "x.com",
}


def _clean_discovery_query(query: str) -> str:
    parts = []
    for token in str(query or "").split():
        clean = token.strip().strip(",;:()[]{}\"'")
        if clean.lower() in _DISCOVERY_NOISE_TERMS or clean.lower().startswith("site:instagram") or clean.lower().startswith("site:facebook"):
            continue
        parts.append(token)
    return " ".join(parts).strip() or str(query or "").strip()


def _target_type_templates(
    regions: list[str],
    customers: list[str],
    products: list[str],
    *,
    department: str = "unclear",
    category: str = "unclear",
    scenarios: list[str] | None = None,
) -> list[str]:
    region = regions[0] if regions else ""
    product = products[0] if products else ""
    text = " ".join([*customers, *products, *(scenarios or [])]).lower()
    dental_context = any(marker in text for marker in ("dental", "dentist", "odont", "牙科", "口腔", "phantom"))
    queries: list[str] = []

    if department == MEDICAL_CONSUMABLES:
        if category == CSSD_STERILIZATION:
            templates = (
                (region, "medical consumables distributor", product),
                (region, "medical consumables importer", product),
                (region, "CSSD supplier", product),
                (region, "hospital sterilization products distributor", product or "sterilization products"),
                (region, "central sterile supply department supplier", product or "sterilization supplies"),
            )
        elif category == SURGICAL_PACKS:
            templates = (
                (region, "medical consumables distributor", product),
                (region, "hospital supplies distributor", product),
                (region, "medical supplies wholesaler", product or "surgical packs"),
            )
        elif category == MEDICAL_PPE_CONSUMABLES:
            templates = (
                (region, "medical consumables distributor", product),
                (region, "medical consumables importer", product),
                (region, "hospital PPE supplies distributor", product),
                (region, "medical supplies wholesaler", product),
            )
        else:
            templates = (
                (region, "medical consumables distributor", product),
                (region, "medical consumables importer", product),
                (region, "hospital supplies distributor", product),
                (region, "medical supplies wholesaler", product),
            )
        queries.extend(_join_query(parts) for parts in templates)
        return _dedupe_queries(queries)[:6]

    if department == DENTAL:
        if category == DENTAL_TEACHING_LAB or any(marker in text for marker in ("school", "university", "faculty", "college", "training", "学校", "大学", "学院", "培训")):
            queries.extend(
                _join_query(parts)
                for parts in (
                    (region, "dental simulation training center"),
                    (region, "faculty of dentistry", product),
                    (region, "dental school phantom head lab"),
                    (region, "preclinical dental lab", product),
                )
            )
            if _is_thailand(region):
                queries.extend([
                    _join_query(("คณะทันตแพทยศาสตร์", product)),
                    _join_query(("ศูนย์ฝึกอบรมทันตกรรม", product or "phantom head")),
                ])
        if category == DENTAL_CONSUMABLES:
            queries.extend(
                _join_query(parts)
                for parts in (
                    (region, "dental consumables distributor", product),
                    (region, "dental supplies importer", product),
                    (region, "dental disposable supplier", product),
                    (region, "dental burs supplier", product),
                )
            )
        elif category == DENTAL_EQUIPMENT or any(marker in text for marker in ("distributor", "dealer", "supplier", "importer", "wholesale", "agent", "经销", "代理", "进口", "批发")):
            queries.extend(
                _join_query(parts)
                for parts in (
                    (region, "dental equipment distributor", product),
                    (region, "dental supplies importer", product),
                    (region, "authorized dental dealer", product),
                    (region, "dental equipment wholesaler"),
                )
            )
            if _is_thailand(region):
                queries.append(_join_query(("ตัวแทนจำหน่าย อุปกรณ์ทันตกรรม", product)))
        return _dedupe_queries(queries)[:6]

    if any(marker in text for marker in ("school", "university", "faculty", "college", "training", "学校", "大学", "学院", "培训")):
        queries.extend(
            _join_query(parts)
            for parts in (
                (region, "dental simulation training center"),
                (region, "faculty of dentistry", product),
                (region, "dental school phantom head lab"),
                (region, "preclinical dental lab", product),
            )
        )
        if _is_thailand(region):
            queries.extend([
                _join_query(("คณะทันตแพทยศาสตร์", product)),
                _join_query(("ศูนย์ฝึกอบรมทันตกรรม", product or "phantom head")),
            ])
    if any(marker in text for marker in ("distributor", "dealer", "supplier", "importer", "wholesale", "agent", "经销", "代理", "进口", "批发")):
        templates = (
            ((region, "dental equipment distributor", product), (region, "dental supplies importer", product), (region, "authorized dental dealer", product), (region, "dental equipment wholesaler"))
            if dental_context
            else ((region, product, "distributor"), (region, product, "supplier"), (region, product, "importer"), (region, product, "wholesaler"))
        )
        queries.extend(_join_query(parts) for parts in templates)
        if _is_thailand(region):
            queries.append(_join_query(("ตัวแทนจำหน่าย อุปกรณ์ทันตกรรม", product)))
    return _dedupe_queries(queries)[:6]


def _dedupe_queries(queries: list[str]) -> list[str]:
    deduped: list[str] = []
    for query in queries:
        if query and query not in deduped:
            deduped.append(query)
    return deduped


def _join_query(parts: tuple[str, ...]) -> str:
    return " ".join(str(part or "").strip() for part in parts if str(part or "").strip())


def _is_thailand(region: str) -> bool:
    return str(region or "").strip().lower() in {"thailand", "thai", "泰国", "ประเทศไทย"}
