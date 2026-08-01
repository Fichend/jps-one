from pathlib import Path

from config.settings import Settings
from hunt_copilot.conversation_guide import suggested_replies
from hunt_copilot.schemas import CopilotSession, CopilotState, HuntStrategy
from hunt_copilot.service import HuntCopilotService
from hunt_copilot.store import HuntCopilotStore
from hunt_copilot.validator import StrategyValidator


def _settings(tmp_path: Path):
    return Settings(
        hunts_dir=str(tmp_path / "hunts"),
        automation_queue_db_path=str(tmp_path / "queue.db"),
        tavily_api_key="tvly",
        serper_api_key="serper",
        apify_token="apify",
        hunt_copilot_llm_enabled=False,
    )


def test_suggested_replies_offer_missing_hard_fields():
    settings = Settings(hunt_copilot_llm_enabled=False)
    strategy = HuntStrategy(target_regions=["Vietnam"], customer_types=["dental school"], product_keywords=["dental simulator"])
    validation = StrategyValidator(settings).validate(strategy)
    session = CopilotSession(
        session_id="s1",
        state=CopilotState.COLLECTING_REQUIREMENTS,
        strategy=strategy,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
    )

    replies = suggested_replies(session, validation)

    assert "Instagram、邮箱、电话作为硬条件" in replies


def test_suggested_replies_follow_requirement_order():
    settings = Settings(hunt_copilot_llm_enabled=False)
    strategy = HuntStrategy()
    validation = StrategyValidator(settings).validate(strategy)
    session = CopilotSession(
        session_id="s1",
        state=CopilotState.COLLECTING_REQUIREMENTS,
        strategy=strategy,
        created_at="2026-07-24T00:00:00+00:00",
        updated_at="2026-07-24T00:00:00+00:00",
    )

    replies = suggested_replies(session, validation)

    assert replies[0].startswith("目标地区")
    assert not any("硬条件" in item for item in replies)


def test_service_returns_suggested_replies_for_next_user_step(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, assistant = service.start("越南牙科学校和牙科设备经销商，排除普通牙科诊所")

    assert "已理解" in assistant
    assert session.suggested_replies
    assert any("硬条件" in item or "dental simulator" in item for item in session.suggested_replies)


def test_smalltalk_opens_without_collecting_hard_fields(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, assistant = service.start("hi")

    assert "你好" in assistant
    assert "硬条件" not in assistant
    assert not session.strategy.raw_requirement
    assert any(item.startswith("目标地区") for item in session.suggested_replies)
