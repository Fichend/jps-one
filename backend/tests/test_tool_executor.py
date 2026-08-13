from config.settings import Settings
from hunt_copilot.schemas import HuntStrategy, ToolPlanStep
from tool_executor import ToolExecutor, build_tool_plan


def test_tool_plan_builds_unified_mcp_tool_steps():
    strategy = HuntStrategy(
        target_regions=["Vietnam"],
        customer_types=["dental distributor"],
        product_keywords=["dental simulator"],
    )
    plan = build_tool_plan(strategy)

    tools = [step.tool for step in plan.steps]

    assert "web.search.tavily" in tools
    assert "local.search.google_maps" in tools
    assert "social.search.instagram.apify" in tools
    assert "social.search.facebook.apify" in tools
    assert "evidence.search.opensearch" in tools
    assert all(step.execution_mode == "search_phase" for step in plan.steps if step.tool in {"web.search.tavily", "local.search.google_maps"})
    assert all(step.execution_mode == "candidate_enrichment" for step in plan.steps if step.tool.startswith("social.search."))
    assert not any(step.tool.startswith("social.search.") and step.execution_mode == "search_phase" for step in plan.steps)
    assert plan.requires_user_confirmation is True
    assert plan.plan_hash
    assert "候选池" in plan.summary
    assert "补全工具" in plan.summary


def test_tool_plan_uses_target_type_templates_for_dental_school_thailand():
    strategy = HuntStrategy(
        target_regions=["Thailand"],
        customer_types=["dental school", "dental training center"],
        product_keywords=["dental simulator"],
    )

    queries = [step.query for step in build_tool_plan(strategy).steps if step.execution_mode == "search_phase"]
    joined = "\n".join(queries)

    assert "Thailand dental simulation training center" in joined
    assert "Thailand faculty of dentistry dental simulator" in joined
    assert "คณะทันตแพทยศาสตร์ dental simulator" in joined


def test_tool_plan_uses_medical_cssd_templates_without_dental_leakage():
    strategy = HuntStrategy(
        target_regions=["Brazil"],
        customer_types=["medical consumables distributor", "medical consumables importer", "CSSD supplier"],
        product_keywords=["sterilization indicator tape", "chemical indicator"],
        product_department="medical_consumables",
        product_category="cssd_sterilization",
        application_scenarios=["CSSD"],
    )

    queries = [step.query for step in build_tool_plan(strategy).steps if step.execution_mode == "search_phase"]
    joined = "\n".join(queries).lower()

    assert "brazil medical consumables distributor" in joined
    assert "brazil medical consumables importer" in joined
    assert "brazil cssd supplier" in joined
    assert "hospital sterilization products distributor" in joined
    assert "dental equipment distributor" not in joined
    assert "dental simulation" not in joined


def test_tool_plan_is_stable_for_reordered_strategy_terms():
    first = HuntStrategy(
        target_regions=["Vietnam"],
        customer_types=["dental school", "dental equipment distributor"],
        product_keywords=["phantom head", "dental simulator"],
    )
    second = HuntStrategy(
        target_regions=["Vietnam"],
        customer_types=["dental equipment distributor", "dental school"],
        product_keywords=["dental simulator", "phantom head"],
    )

    assert build_tool_plan(first).plan_hash == build_tool_plan(second).plan_hash
    assert [step.query for step in build_tool_plan(first).steps] == [step.query for step in build_tool_plan(second).steps]


def test_tool_plan_keeps_contact_and_social_terms_out_of_discovery_queries():
    strategy = HuntStrategy(
        target_regions=["Vietnam"],
        customer_types=["dental school", "dental equipment distributor"],
        product_keywords=["dental simulator"],
    )
    strategy.hard_filters.require_instagram = True
    strategy.hard_filters.require_facebook = True
    strategy.hard_filters.require_email = True
    strategy.hard_filters.require_phone = True

    plan = build_tool_plan(strategy)
    search_steps = [step for step in plan.steps if step.tool != "evidence.search.opensearch"]

    assert search_steps
    for step in search_steps:
        query = step.query.lower()
        assert "email" not in query
        assert "phone" not in query
        assert "instagram" not in query
        assert "facebook" not in query


def test_tool_executor_preview_checks_required_config():
    settings = Settings(tavily_api_key="", apify_token="apify")
    executor = ToolExecutor(settings)

    tavily = executor.preview_step(ToolPlanStep(tool="web.search.tavily", query="x"))
    instagram = executor.preview_step(
        ToolPlanStep(
            tool="social.search.instagram.apify",
            query="x",
            phase="enrichment",
            execution_mode="candidate_enrichment",
        )
    )

    assert tavily.status == "missing_config"
    assert instagram.status == "ready"
    assert instagram.phase == "enrichment"
    assert instagram.execution_mode == "candidate_enrichment"
