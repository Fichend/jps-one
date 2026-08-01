from hunt_copilot.product_context import JpsProductContextBuilder
from hunt_copilot.response_builder import CopilotResponseBuilder
from hunt_copilot.schemas import CopilotSession, CopilotState, HuntStrategy
from hunt_copilot.validator import ValidationResult


def test_product_context_recommends_jps_dental_keywords_for_school_and_distributor():
    strategy = HuntStrategy(
        target_regions=["Vietnam"],
        customer_types=["dental school", "dental equipment distributor"],
        exclusions=["general dental clinic"],
    )

    context = JpsProductContextBuilder().build(strategy, message="越南牙科学校和牙科设备经销商，排除普通牙科诊所")

    assert "dental simulator" in context.recommended_keywords
    assert "phantom head" in context.recommended_keywords
    assert "Dental Teaching and Lab Products" in context.matched_families
    assert "general dental clinic" in context.normalized_exclusions


def test_response_builder_mentions_jps_catalogue_context():
    strategy = HuntStrategy(
        target_regions=["Vietnam"],
        customer_types=["dental school", "dental equipment distributor"],
        product_keywords=["dental simulator", "phantom head"],
        product_knowledge_summary="匹配产品线：Dental Teaching and Lab Products；建议关键词：dental simulator、phantom head",
    )
    session = CopilotSession(
        session_id="s1",
        state=CopilotState.STRATEGY_READY,
        strategy=strategy,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
    )

    message = CopilotResponseBuilder().build(session, ValidationResult([], [], [], []))

    assert "基于 JPS 产品目录" in message
    assert "dental simulator" in message
    assert "先找 40 个候选" in message
