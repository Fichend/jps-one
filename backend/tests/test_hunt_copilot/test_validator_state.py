from pathlib import Path

from config.settings import Settings
from hunt_copilot.patch_merger import StrategyPatchMerger
from hunt_copilot.schemas import HuntStrategy
from hunt_copilot.state_machine import allowed_actions
from hunt_copilot.validator import StrategyValidator


def _settings(tmp_path: Path, **overrides):
    return Settings(hunts_dir=str(tmp_path / "hunts"), automation_queue_db_path=str(tmp_path / "queue.db"), hunt_copilot_llm_enabled=False, **overrides)


def test_validator_blocks_excluded_target_and_missing_keywords(tmp_path):
    strategy = HuntStrategy(customer_types=["general dental clinic"], exclusions=["general dental clinic"])
    result = StrategyValidator(_settings(tmp_path)).validate(strategy)

    assert "product_keywords" in result.missing_fields
    assert result.detected_conflicts
    assert result.blocking_errors


def test_patch_merger_normalizes_jps_targets_and_required_fields():
    strategy = StrategyPatchMerger().merge(
        HuntStrategy(),
        {
            "target_regions": ["越南"],
            "customer_types": ["牙科学校", "普通牙科诊所"],
            "exclusions": ["普通牙科诊所"],
            "hard_filters": {"require_instagram": True, "require_email": True, "require_phone": True},
        },
        raw_message="我需要越南牙科学校，排除普通牙科诊所，必须有 Instagram、邮箱和电话",
    )

    assert "dental school" in strategy.customer_types
    assert "general dental clinic" in strategy.exclusions
    assert "general dental clinic" not in strategy.customer_types
    assert strategy.required_fields == ["Instagram", "邮箱", "电话"]
    assert strategy.product_keywords == []
    assert "dental simulator" in strategy.product_knowledge_summary


def test_allowed_actions_require_strategy_confirmation(tmp_path):
    strategy = HuntStrategy(
        target_regions=["Vietnam"],
        customer_types=["dental school"],
        product_keywords=["dental simulator"],
    )
    strategy.hard_filters.require_instagram = True
    result = StrategyValidator(_settings(tmp_path, apify_token="apify")).validate(strategy)
    session = type("Session", (), {"strategy": strategy, "preview": None, "automation_job_id": ""})()

    actions = allowed_actions(session, result)

    assert "confirm_strategy" in actions
    assert "check_channels" not in actions
