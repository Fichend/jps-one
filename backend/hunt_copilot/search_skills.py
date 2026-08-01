"""Search skill definitions for JPS-One Hunt Copilot."""

from __future__ import annotations

from hunt_copilot.schemas import SearchSkill


SEARCH_SKILLS: list[SearchSkill] = [
    SearchSkill(
        id="dental_distributor_search",
        name="牙科设备经销商搜索",
        description="寻找销售牙科设备、牙科耗材或牙科教学设备的经销商。",
        applicable_intents=["dental distributor", "dental dealer", "牙科经销商", "牙科设备经销商"],
        target_company_types=["dental equipment distributor", "dental distributor", "dental supplier"],
        default_product_categories=["dental equipment", "dental unit", "dental consumables"],
        recommended_channels=["tavily", "google_maps"],
        optional_channels=["instagram", "facebook"],
        default_filters=["exclude general dental clinics", "exclude individual dentists"],
        required_fields=["target_regions", "product_keywords"],
        planner_instructions="优先寻找有官网、电话、地址、产品目录或代理品牌信息的牙科经销商。",
        risk_notes=["普通牙科诊所不应作为经销商目标。"],
    ),
    SearchSkill(
        id="dental_school_search",
        name="牙科学校/培训中心搜索",
        description="寻找牙科学校、牙科学院、口腔培训中心和教学实验室采购场景。",
        applicable_intents=["dental school", "dental college", "牙科学校", "牙科培训", "口腔院校"],
        target_company_types=["dental school", "dental college", "dental training center"],
        default_product_categories=["dental simulator", "phantom head", "dental teaching equipment"],
        recommended_channels=["tavily"],
        optional_channels=["google_maps", "instagram", "facebook"],
        default_filters=["exclude general dental clinics"],
        required_fields=["target_regions", "product_keywords"],
        planner_instructions="优先匹配 preclinical lab、simulation center、dental faculty 等教学采购信号。",
        risk_notes=["学校类客户的 Instagram 覆盖率可能低于经销商。"],
    ),
    SearchSkill(
        id="medical_consumables_distributor_search",
        name="医疗耗材经销商搜索",
        description="寻找销售或分销一次性医疗耗材、伤口护理、灭菌包装和医院用品的企业。",
        applicable_intents=["medical consumables", "medical disposables", "医疗耗材", "医用耗材", "医院耗材"],
        target_company_types=["medical consumables distributor", "medical supplies distributor", "hospital supplies wholesaler"],
        default_product_categories=["medical consumables", "surgical gown", "sterilization pouch", "wound dressing", "medical adhesive tape"],
        recommended_channels=["tavily", "google_maps"],
        optional_channels=["facebook", "instagram"],
        default_filters=["exclude manufacturers when searching for distributors", "exclude B2C-only stores"],
        required_fields=["target_regions", "product_keywords"],
        planner_instructions="优先寻找医疗耗材进口商、医院用品分销商、药房批发商和有产品目录的供应链公司。",
        risk_notes=["社媒账号不是医疗耗材经销商的稳定硬条件，官网、电话、产品目录和资质证据更重要。"],
    ),
    SearchSkill(
        id="social_required_search",
        name="社媒硬条件搜索约束",
        description="当用户明确要求 Instagram 或 Facebook 时叠加的搜索约束。",
        applicable_intents=["instagram", "facebook", "ins", "社媒", "脸书"],
        target_company_types=[],
        default_product_categories=[],
        recommended_channels=["instagram", "facebook"],
        optional_channels=["tavily", "google_maps"],
        default_filters=["public profiles only", "no login-only or private data"],
        required_fields=["social_profiles"],
        planner_instructions="社媒仅处理公开主页或已授权资产，缺失社媒时进入待补全或拒绝规则。",
        risk_notes=["把社媒设置为硬条件会减少最终可入库客户数量。"],
    ),
    SearchSkill(
        id="general_b2b_search",
        name="通用 B2B 客户搜索",
        description="用于暂未匹配到明确牙科或医疗耗材场景的 B2B 搜索任务。",
        applicable_intents=["general", "b2b", "客户", "经销商"],
        target_company_types=["distributor", "supplier", "importer"],
        default_product_categories=[],
        recommended_channels=["tavily", "google_maps"],
        optional_channels=["instagram", "facebook"],
        default_filters=["exclude unrelated end users"],
        required_fields=["target_regions", "customer_types", "product_keywords"],
        planner_instructions="先补齐产品和客户类型，再进入正式搜索。",
        risk_notes=["目标过泛时需要先收窄产品和客户类型。"],
    ),
]


def list_search_skills() -> list[SearchSkill]:
    return SEARCH_SKILLS


def get_search_skill(skill_id: str) -> SearchSkill | None:
    for skill in SEARCH_SKILLS:
        if skill.id == skill_id:
            return skill
    return None
