from pathlib import Path

from config.settings import Settings
from hunt_copilot.conversation_host import ConversationHost
from hunt_copilot.conversation_router import ConversationRouter
from hunt_copilot.schemas import CopilotSession, CopilotState, HuntStrategy
from hunt_copilot.service import HuntCopilotService
from hunt_copilot.store import HuntCopilotStore


def _settings(tmp_path: Path | None = None):
    values = {"hunt_copilot_llm_enabled": False}
    if tmp_path:
        values.update({"hunts_dir": str(tmp_path / "hunts"), "automation_queue_db_path": str(tmp_path / "queue.db")})
    return Settings(**values)


def _session() -> CopilotSession:
    return CopilotSession(
        session_id="s1",
        state=CopilotState.COLLECTING_REQUIREMENTS,
        strategy=HuntStrategy(),
        created_at="2026-07-27T00:00:00+00:00",
        updated_at="2026-07-27T00:00:00+00:00",
    )


def test_router_keeps_general_question_out_of_strategy_planner():
    route = ConversationRouter(_settings()).route("1+1=几", _session())

    assert route.intent == "general_question"
    assert route.should_call_planner is False
    assert route.should_update_strategy is False


def test_router_routes_search_requirement_to_strategy_planner():
    route = ConversationRouter(_settings()).route("我要找越南牙科学校，排除普通牙科诊所", _session())

    assert route.intent == "search_requirement"
    assert route.should_call_planner is True
    assert route.should_update_strategy is True


def test_host_answers_simple_math_naturally():
    route = ConversationRouter(_settings()).route("1+1=几", _session())
    message = ConversationHost().reply(route, _session(), "1+1=几")

    assert "1+1=2" in message
    assert "目标" in message or "搜索任务" in message


def test_service_does_not_mutate_strategy_for_general_question(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, assistant = service.start("1+1=几")

    assert "1+1=2" in assistant
    assert session.strategy.raw_requirement == ""
    assert session.last_user_intent == "general_question"


def test_service_explains_capability_without_mutating_strategy(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, assistant = service.start("你能做什么")

    assert "获客" in assistant
    assert "候选池" in assistant
    assert session.strategy.raw_requirement == ""
    assert session.last_user_intent == "capability_help"


def test_service_records_conversation_memory_for_strategy_patch(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, _ = service.start("我要找越南牙科学校，排除普通牙科诊所")

    assert session.last_user_intent == "search_requirement"
    assert session.conversation_summary
    assert session.recent_strategy_changes


def test_country_commands_reproduce_and_fix_brazil_conversation(tmp_path):
    store = HuntCopilotStore(str(tmp_path / "sessions.json"))
    service = HuntCopilotService(store=store, settings=_settings(tmp_path))
    session = _session()
    session.strategy.target_regions = ["Brazil", "Mexico", "Spain"]
    session.strategy.customer_types = ["medical distributor"]
    session.strategy.product_keywords = ["sterilization indicator"]
    store.save(session)

    session, _ = service.send("s1", "只要brazil")
    assert session.strategy.target_regions == ["Brazil"]

    session.strategy.target_regions = ["Brazil", "Mexico", "Spain"]
    store.save(session)
    session, _ = service.send("s1", "地区不要mexico和spain")
    assert session.strategy.target_regions == ["Brazil"]
    assert {"Mexico", "Spain"}.issubset(set(session.strategy.exclusions))

    before = session.strategy.model_dump()
    session, assistant = service.send("s1", "最终策略卡是什么")
    assert session.strategy.model_dump() == before
    assert "Brazil" in assistant
    assert session.last_user_intent == "strategy_query"


def test_target_region_field_assignment_replaces_instead_of_union(tmp_path):
    store = HuntCopilotStore(str(tmp_path / "sessions.json"))
    service = HuntCopilotService(store=store, settings=_settings(tmp_path))
    session = _session()
    session.strategy.target_regions = ["Mexico", "Spain"]
    store.save(session)

    session, _ = service.send("s1", "目标地区：brazil")

    assert session.strategy.target_regions == ["Brazil"]


def test_plain_approval_does_not_confirm_strategy():
    route = ConversationRouter(_settings()).route("没问题", _session())

    assert route.action != "confirm_strategy"
