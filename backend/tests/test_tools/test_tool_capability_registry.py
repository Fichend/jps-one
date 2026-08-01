from config.settings import Settings
from search_tools import list_tool_capabilities, list_tool_status


def test_tool_registry_does_not_expose_secret_values(tmp_path):
    capabilities = list_tool_capabilities()

    assert any(item.id == "instagram" for item in capabilities)
    assert all("apify_api_" not in str(item.model_dump()).lower() for item in capabilities)


def test_tool_status_marks_missing_apify(tmp_path):
    settings = Settings(
        hunts_dir=str(tmp_path / "hunts"),
        automation_queue_db_path=str(tmp_path / "queue.db"),
        tavily_api_key="tvly",
        serper_api_key="serper",
        apify_token="",
    )
    status = {item.capability.id: item for item in list_tool_status(settings)}

    assert status["tavily"].status == "ok"
    assert status["instagram"].status == "missing_config"
