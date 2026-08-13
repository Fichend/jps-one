from pathlib import Path

from config.settings import Settings
from hunt_copilot.service import HuntCopilotService
from hunt_copilot.store import HuntCopilotStore
from hunt_copilot.strategy_renderer import render_strategy_card


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        hunt_copilot_llm_enabled=False,
        hunts_dir=str(tmp_path / "hunts"),
        automation_queue_db_path=str(tmp_path / "queue.db"),
    )


def _service(tmp_path: Path) -> HuntCopilotService:
    return HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))


def test_semantic_copilot_extracts_required_social_and_contact_fields(tmp_path):
    service = _service(tmp_path)

    session, _ = service.start(
        "我需要越南牙科学校和牙科设备经销商，必须有 Instagram、邮箱和电话，最终要 10 个客户，候选 40，预算 1 USD，排除普通诊所"
    )

    assert session.strategy.target_regions == ["Vietnam"]
    assert session.strategy.hard_filters.require_instagram is True
    assert session.strategy.hard_filters.require_email is True
    assert session.strategy.hard_filters.require_phone is True
    assert session.strategy.budget.final_leads == 10
    assert session.strategy.budget.max_candidates == 40
    assert session.strategy.budget.total_usd == 1
    assert session.strategy.search_sources == ["web", "google_maps", "instagram", "facebook"]


def test_render_strategy_card_mentions_candidate_pool(tmp_path):
    service = _service(tmp_path)
    session, _ = service.start("Thailand distributor dental simulator email phone Instagram top 5 candidate 20")

    card = render_strategy_card(session.strategy)

    assert "Hunt Copilot 策略卡" in card
    assert "candidate_pool" in card
    assert "业务员无需选择" in card


def test_semantic_copilot_uses_jps_catalog_and_excludes_clinic_targets(tmp_path):
    service = _service(tmp_path)

    session, _ = service.start(
        "我需要越南牙科学校和牙科设备经销商，必须有 Instagram、邮箱和电话，最终要 10 个客户，候选池先找 40 个，预算 1 美元，排除普通牙科诊所。"
    )

    assert "dental school" in session.strategy.customer_types
    assert "dental equipment distributor" in session.strategy.customer_types
    assert "general dental clinic" in session.strategy.exclusions
    assert "general dental clinic" not in session.strategy.customer_types
    assert session.strategy.product_keywords == []
    assert "dental simulator" in session.strategy.product_knowledge_summary
    assert session.strategy.hard_filters.require_instagram is True
    assert session.strategy.hard_filters.require_email is True
    assert session.strategy.hard_filters.require_phone is True
