from pathlib import Path

from config.settings import Settings
from hunt_copilot.schemas import ConfirmExecutionRequest, CopilotState
from hunt_copilot.service import HuntCopilotService
from hunt_copilot.store import HuntCopilotStore


def _settings(tmp_path: Path, **overrides):
    values = {
        "hunts_dir": str(tmp_path / "hunts"),
        "automation_queue_db_path": str(tmp_path / "queue.db"),
        "tavily_api_key": "tvly",
        "serper_api_key": "serper",
        "apify_token": "apify",
        "jina_api_key": "jina",
        "hunt_copilot_llm_enabled": False,
        **overrides,
    }
    return Settings(**values)


def test_copilot_collects_then_checks_channels(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, _ = service.start("找 Vietnam dental school distributor")

    assert session.state == CopilotState.COLLECTING_REQUIREMENTS
    assert session.selected_skill is not None

    for message in (
        "目标地区 Vietnam，客户类型 dental school distributor，产品 dental simulator",
        "必须有 Instagram 邮箱 电话",
        "预检 0.1 USD 正式 1 USD 候选 40 最终 10",
        "启用硬过滤，缺少必需字段先待补全再拒绝",
    ):
        session, _ = service.send(session.session_id, message)

    assert session.state == CopilotState.STRATEGY_READY

    session, assistant = service.confirm_strategy(session.session_id)
    assert session.strategy.strategy_confirmed is True
    assert "策略卡已确认" in assistant

    session, assistant = service.check_channels(session.session_id)
    assert session.state == CopilotState.WAITING_EXECUTION_CONFIRMATION
    assert "通道健康检查通过" in assistant
    assert session.preview is not None
    assert session.tool_plan is not None
    assert any(step.tool == "web.search.tavily" for step in session.tool_plan.steps)
    assert session.tool_execution_preview


def test_execute_enqueues_automation_job(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, _ = service.start("Vietnam dental distributor dental simulator Instagram email phone top 5 candidate 20")
    session, _ = service.update_strategy(session.session_id, session.strategy)
    session, _ = service.confirm_strategy(session.session_id)
    session, _ = service.check_channels(session.session_id)

    session, job = service.confirm_execution(session.session_id, ConfirmExecutionRequest())

    assert session.state == CopilotState.RUNNING_FULL_SEARCH
    assert session.automation_job_id
    assert job["job_id"] == session.automation_job_id
    assert job["payload"]["search_sources"] == ["web", "google_maps", "instagram", "facebook"]
    assert job["payload"]["tool_plan"]["steps"]
    assert job["payload"]["search_budget"]["candidate_pool_enabled"] is True


def test_copilot_history_and_duplicate_session(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, _ = service.start("Vietnam dental distributor Instagram email phone top 5 candidate 20")

    history = service.list_history()
    assert history[0].session_id == session.session_id
    assert history[0].max_candidates == 20

    duplicated, assistant = service.duplicate_session(session.session_id)

    assert duplicated.session_id != session.session_id
    assert duplicated.strategy.customer_types == session.strategy.customer_types
    assert duplicated.strategy.strategy_confirmed is False
    assert "已复制历史策略" in assistant


def test_copilot_surfaces_similar_history(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    first, _ = service.start("Vietnam dental school dental simulator Instagram email phone top 10 candidate 40")
    second, _ = service.start("越南牙科学校，必须有 Instagram 邮箱 电话，最终 10 候选 40")

    assert second.strategy_hash
    assert any(item["session_id"] == first.session_id for item in second.similar_history)


def test_copilot_selects_medical_consumables_skill(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, _ = service.start("寻找泰国医疗耗材经销商，产品是手术衣、灭菌袋、医用胶带")

    assert session.selected_skill is not None
    assert session.selected_skill.skill.id == "medical_consumables_distributor_search"


def test_copilot_replaces_keywords_when_user_says_only(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, _ = service.start("泰国牙科学校和牙科设备经销商，排除普通牙科诊所，必须有 Instagram 邮箱 电话")
    assert session.strategy.product_keywords == []
    assert "dental simulator" in session.strategy.product_knowledge_summary

    session, assistant = service.send(session.session_id, "只要 dental simulator")

    assert session.strategy.product_keywords == ["dental simulator"]
    assert "策略卡" in assistant or "核心策略" in assistant


def test_confirm_strategy_returns_business_summary(tmp_path):
    service = HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))
    session, _ = service.start("泰国牙科学校和牙科设备经销商，排除普通牙科诊所，只要 dental simulator，必须有 Instagram 邮箱 电话")

    session, assistant = service.confirm_strategy(session.session_id)

    assert session.strategy.strategy_confirmed is True
    assert "策略卡已确认" in assistant
    assert "dental simulator" in assistant
    assert "Instagram" in assistant
