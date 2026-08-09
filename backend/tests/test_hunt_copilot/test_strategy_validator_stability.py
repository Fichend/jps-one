from config.settings import Settings
from hunt_copilot.schemas import HuntStrategy
from hunt_copilot.validator import StrategyValidator


def _valid_strategy(**updates):
    strategy = HuntStrategy(
        target_regions=["Brazil"],
        customer_types=["medical distributor"],
        product_keywords=["sterilization indicator"],
        hard_filters={"require_website": True},
    )
    for key, value in updates.items():
        setattr(strategy, key, value)
    return strategy


def test_validator_blocks_multi_country_execution_strategy():
    result = StrategyValidator(Settings(hunt_copilot_llm_enabled=False)).validate(
        _valid_strategy(target_regions=["Brazil", "Mexico"])
    )
    assert any("单国家" in item for item in result.blocking_errors)


def test_validator_blocks_region_exclusion_conflict_and_country_product_keyword():
    result = StrategyValidator(Settings(hunt_copilot_llm_enabled=False)).validate(
        _valid_strategy(exclusions=["巴西"], product_keywords=["Brazil"])
    )
    assert any("目标地区与排除地区" in item for item in result.blocking_errors)
    assert any("真实产品" in item for item in result.blocking_errors)
