from hunt_copilot.planner import infer_strategy, render_strategy_card


def test_infer_strategy_extracts_required_social_and_contact_fields():
    strategy = infer_strategy(
        "我需要越南牙科学校和牙科设备经销商，必须有 Instagram、邮箱和电话，最终要 10 个客户，候选 40，预算 1 USD，排除普通诊所"
    )

    assert "越南" in strategy.target_regions
    assert strategy.hard_filters.require_instagram is True
    assert strategy.hard_filters.require_email is True
    assert strategy.hard_filters.require_phone is True
    assert strategy.budget.final_leads == 10
    assert strategy.budget.max_candidates == 40
    assert strategy.budget.total_usd == 1
    assert strategy.search_sources == ["web", "google_maps", "instagram", "facebook"]


def test_render_strategy_card_mentions_candidate_pool():
    strategy = infer_strategy("Thailand distributor email phone Instagram dental simulator top 5 candidate 20")
    card = render_strategy_card(strategy)

    assert "Hunt Copilot 策略卡" in card
    assert "candidate_pool" in card
    assert "业务员无需选择" in card


def test_planner_uses_jps_catalog_keywords_and_excludes_clinic_targets():
    strategy = infer_strategy(
        "我需要越南牙科学校和牙科设备经销商，必须有 Instagram、邮箱和电话，最终要 10 个客户，候选池先找 40 个，预算 1 美元，排除普通牙科诊所。"
    )

    assert "dental school" in strategy.customer_types
    assert "dental equipment distributor" in strategy.customer_types
    assert "general dental clinic" in strategy.exclusions
    assert "general dental clinic" not in strategy.customer_types
    assert "dental simulator" in strategy.product_keywords
    assert "dental teaching equipment" in strategy.product_keywords
    assert strategy.hard_filters.require_instagram is True
    assert strategy.hard_filters.require_email is True
    assert strategy.hard_filters.require_phone is True
