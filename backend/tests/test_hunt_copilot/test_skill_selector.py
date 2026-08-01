from hunt_copilot.schemas import HuntStrategy
from hunt_copilot.skill_selector import SearchSkillSelector


def test_selects_medical_consumables_skill():
    strategy = HuntStrategy(customer_types=["medical consumables distributor"], product_keywords=["surgical gown"])
    selection = SearchSkillSelector().select(text="寻找泰国医疗耗材经销商", strategy=strategy)

    assert selection.skill.id == "medical_consumables_distributor_search"


def test_selects_dental_school_and_social_overlay():
    strategy = HuntStrategy(customer_types=["dental school"], product_keywords=["dental simulator"])
    strategy.hard_filters.require_instagram = True
    selection = SearchSkillSelector().select(text="越南牙科学校必须有 Instagram", strategy=strategy)

    assert selection.skill.id == "dental_school_search"
    assert [overlay.id for overlay in selection.overlays] == ["social_required_search"]
