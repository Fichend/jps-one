from pathlib import Path

import pytest

from config.settings import Settings
from hunt_copilot.conversation_router import ConversationRouter
from hunt_copilot.schemas import CopilotSession, CopilotState, HuntStrategy
from hunt_copilot.service import HuntCopilotService
from hunt_copilot.store import HuntCopilotStore
from hunt_copilot.strategy_commands import parse_strategy_command


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        hunt_copilot_llm_enabled=False,
        hunts_dir=str(tmp_path / "hunts"),
        automation_queue_db_path=str(tmp_path / "queue.db"),
    )


def _service(tmp_path: Path) -> HuntCopilotService:
    return HuntCopilotService(store=HuntCopilotStore(str(tmp_path / "sessions.json")), settings=_settings(tmp_path))


def _session() -> CopilotSession:
    return CopilotSession(
        session_id="s1",
        state=CopilotState.COLLECTING_REQUIREMENTS,
        strategy=HuntStrategy(),
        created_at="2026-08-10T00:00:00+00:00",
        updated_at="2026-08-10T00:00:00+00:00",
    )


def test_routes_complete_requirement_patch_and_query_separately(tmp_path):
    router = ConversationRouter(_settings(tmp_path))

    requirement = router.route("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱", _session())
    patch = router.route("产品去掉 Brazil", _session())
    query = router.route("当前策略是什么？", _session())

    assert requirement.intent == "search_requirement"
    assert requirement.should_call_planner is True
    assert patch.intent == "strategy_command"
    assert patch.should_call_planner is False
    assert query.intent == "strategy_query"
    assert query.should_update_strategy is False


@pytest.mark.parametrize("message", ["可以", "好的", "没问题", "就这样", "确认", "确认策略"])
def test_ambiguous_approval_never_confirms_or_changes_strategy(tmp_path, message):
    service = _service(tmp_path)
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")
    before = session.strategy.model_dump(mode="json")

    session, assistant = service.send(session.session_id, message)

    assert session.strategy.model_dump(mode="json") == before
    assert session.strategy.strategy_confirmed is False
    assert "不会确认" in assistant


def test_only_exact_confirmation_text_confirms_strategy(tmp_path):
    service = _service(tmp_path)
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")

    session, _ = service.send(session.session_id, "确认当前策略")

    assert session.strategy.strategy_confirmed is True


def test_read_only_query_preserves_existing_confirmation_and_version(tmp_path):
    service = _service(tmp_path)
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")
    session, _ = service.send(session.session_id, "确认当前策略")
    before = session.strategy.model_dump(mode="json")

    session, _ = service.send(session.session_id, "当前策略是什么？")

    assert session.strategy.model_dump(mode="json") == before
    assert session.strategy.strategy_confirmed is True


@pytest.mark.parametrize("message", ["当前策略是什么？", "候选数量是多少？", "巴西市场难不难", "精准度怎么看"])
def test_read_only_messages_preserve_all_strategy_state(tmp_path, message):
    service = _service(tmp_path)
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")
    before = session.strategy.model_dump(mode="json")

    session, _ = service.send(session.session_id, message)

    assert session.strategy.model_dump(mode="json") == before


def test_complete_requirement_is_saved_without_catalogue_keyword_pollution(tmp_path):
    service = _service(tmp_path)

    session, assistant = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")
    persisted = service.get(session.session_id)

    assert persisted.strategy.target_regions == ["Brazil"]
    assert persisted.strategy.customer_types == ["medical consumables distributor", "CSSD supplier"]
    assert persisted.strategy.product_department == "medical_consumables"
    assert persisted.strategy.product_category == "cssd_sterilization"
    assert persisted.strategy.product_keywords == ["灭菌耗材"]
    assert persisted.strategy.exclusions == ["clinic"]
    assert persisted.strategy.hard_filters.require_email is True
    assert persisted.strategy.hard_filters.require_website is True
    assert "当前已记录" in assistant


def test_cssd_business_context_is_not_product_keyword(tmp_path):
    service = _service(tmp_path)

    session, assistant = service.start("客户是cssd的潜在客户，例如经销商 代理商")

    assert session.strategy.customer_types == ["medical consumables distributor", "CSSD supplier"]
    assert session.strategy.product_department == "medical_consumables"
    assert session.strategy.product_category == "cssd_sterilization"
    assert session.strategy.application_scenarios == ["CSSD"]
    assert session.strategy.product_keywords == []
    assert any("cssd" in note.lower() for note in session.strategy.business_notes)
    assert "CSSD" in assistant
    assert "产品关键词" in assistant or "JPS 产品" in assistant


def test_medical_consumables_cssd_task_locks_department_and_exclusions(tmp_path):
    service = _service(tmp_path)

    session, _ = service.start(
        "我要找巴西医疗耗材经销商和进口商，产品是 Sterilization Indicator Tapes、Indicator Labels、Chemical Indicators、Sterilization Reels、Crepe Paper、Nonwoven Wrapping Materials，应用场景是 CSSD 和医院消毒供应中心，排除牙科学校、牙科诊所和牙科设备经销商。候选池 80 个，最终推荐 20 个。"
    )

    assert session.strategy.product_department == "medical_consumables"
    assert session.strategy.product_category == "cssd_sterilization"
    assert session.strategy.customer_types == ["medical consumables distributor", "medical consumables importer", "CSSD supplier"]
    assert session.strategy.exclusions == ["dental school", "dental equipment distributor", "general dental clinic"]
    assert "distributor" not in session.strategy.exclusions
    assert session.strategy.budget.max_candidates == 80
    assert session.strategy.budget.final_leads == 20
    assert "dental simulator" not in session.strategy.product_keywords


def test_excluded_country_does_not_become_target_region(tmp_path):
    service = _service(tmp_path)

    session, _ = service.start("巴西 cssd sterilization 经销商代理商 排除 Spain")

    assert session.strategy.target_regions == ["Brazil"]
    assert "Spain" in session.strategy.exclusions
    assert session.strategy.application_scenarios == ["CSSD"]
    assert "sterilization" in session.strategy.product_keywords


def test_catalogue_only_recommends_when_user_did_not_supply_product(tmp_path):
    service = _service(tmp_path)

    session, _ = service.start("找泰国牙科学校，必须有官网邮箱")

    assert session.strategy.product_keywords == []
    assert "建议关键词" in session.strategy.product_knowledge_summary


def test_uncertain_fields_clear_after_missing_slots_are_filled(tmp_path):
    service = _service(tmp_path)

    session, _ = service.start("找泰国牙科学校，必须有官网邮箱")
    assert "product_keywords" in session.strategy.uncertain_fields

    session, _ = service.send(session.session_id, "只要 dental simulator")

    assert session.strategy.product_keywords == ["dental simulator"]
    assert "product_keywords" not in session.strategy.uncertain_fields


@pytest.mark.parametrize(
    ("message", "field", "operation", "values"),
    [
        ("目标地区增加 Brasil", "target_regions", "add", ["Brazil"]),
        ("目标客户去掉医院", "customer_types", "remove", ["医院"]),
        ("产品关键词替换为 sterilization", "product_keywords", "replace", ["sterilization"]),
        ("排除对象只保留诊所", "exclusions", "keep_only", ["诊所"]),
        ("清空产品关键词", "product_keywords", "clear", []),
        ("清空目标地区", "target_regions", "clear", []),
        ("邮箱必须有", "hard_filters", "add", ["require_email"]),
        ("硬条件只保留邮箱", "hard_filters", "keep_only", ["require_email"]),
        ("优先字段增加 Instagram", "preferred_fields", "add", ["require_instagram"]),
        ("清空优先字段", "preferred_fields", "clear", []),
        ("候选改成 80", "budget.max_candidates", "replace", ["80"]),
        ("当前策略是什么？", "", "query", []),
        ("撤销刚才的修改", "", "undo", []),
    ],
)
def test_commands_use_one_structured_contract(message, field, operation, values):
    command = parse_strategy_command(message)

    assert command is not None
    assert command.as_dict() == {"field": field, "operation": operation, "values": values}


def test_ambiguous_edit_asks_one_question_and_does_not_guess(tmp_path):
    service = _service(tmp_path)
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")
    before = session.strategy.model_dump(mode="json")

    session, assistant = service.send(session.session_id, "去掉医院")

    assert session.strategy.model_dump(mode="json") == before
    assert "请明确要修改的字段" in assistant


def test_command_response_comes_from_persisted_result_and_reports_no_match(tmp_path):
    service = _service(tmp_path)
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")
    version = session.strategy.strategy_version

    session, assistant = service.send(session.session_id, "产品去掉 Brazil")

    assert session.strategy.product_keywords == ["灭菌耗材"]
    assert session.strategy.target_regions == ["Brazil"]
    assert session.strategy.strategy_version == version
    assert "没有找到 brazil" in assistant
    assert "本次没有修改策略" in assistant


def test_changed_command_is_saved_reloaded_and_can_be_undone(tmp_path):
    service = _service(tmp_path)
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")
    original = session.strategy.model_dump(mode="json")

    session, assistant = service.send(session.session_id, "产品关键词增加 chemical indicator")
    assert service.get(session.session_id).strategy.product_keywords == ["灭菌耗材", "chemical indicator"]
    assert "产品关键词：灭菌耗材 → 灭菌耗材、chemical indicator" in assistant

    session, assistant = service.send(session.session_id, "撤销刚才的修改")
    assert session.strategy.product_keywords == original["product_keywords"]
    assert session.strategy.strategy_version > original["strategy_version"]
    assert "已撤销刚才的修改" in assistant


def test_save_verification_blocks_false_success_reply(tmp_path):
    class CorruptingStore(HuntCopilotStore):
        def save(self, session):
            super().save(session)
            if "chemical indicator" in session.strategy.product_keywords:
                corrupted = super().get(session.session_id)
                corrupted.strategy.product_keywords = ["unexpected backend value"]
                super().save(corrupted)

    store = CorruptingStore(str(tmp_path / "sessions.json"))
    service = HuntCopilotService(store=store, settings=_settings(tmp_path))
    session, _ = service.start("找巴西灭菌耗材经销商，排除诊所，必须有官网邮箱")

    with pytest.raises(RuntimeError, match="保存校验失败"):
        service.send(session.session_id, "产品关键词增加 chemical indicator")
