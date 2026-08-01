"""Safe public capability registry for search tools."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from config.settings import Settings, get_settings
from hunt_copilot.schemas import ToolCapability, ToolStatus


REGISTRY_PATH = Path(__file__).resolve().parent / "tool_registry.json"


@lru_cache(maxsize=1)
def list_tool_capabilities() -> list[ToolCapability]:
    raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    tools = raw.get("tools", []) if isinstance(raw, dict) else []
    return [ToolCapability.model_validate(item) for item in tools]


def get_tool_capability(tool_id: str) -> ToolCapability | None:
    for capability in list_tool_capabilities():
        if capability.id == tool_id:
            return capability
    return None


def list_tool_status(settings: Settings | None = None) -> list[ToolStatus]:
    settings = settings or get_settings()
    return [_status_for(capability, settings) for capability in list_tool_capabilities()]


def _status_for(capability: ToolCapability, settings: Settings) -> ToolStatus:
    configured = _configured(capability, settings)
    return ToolStatus(
        capability=capability,
        configured=configured,
        status="ok" if configured else ("not_execution_tested" if capability.id == "jina_reader" else "missing_config"),
        message=_message(capability, configured),
    )


def _configured(capability: ToolCapability, settings: Settings) -> bool:
    if capability.requires_any:
        return any(_setting_value(env_key, settings) for env_key in capability.requires_any)
    if capability.requires:
        return all(_setting_value(env_key, settings) for env_key in capability.requires)
    return True


def _setting_value(env_key: str, settings: Settings) -> str:
    mapping = {
        "TAVILY_API_KEY": settings.tavily_api_key,
        "SERPER_API_KEY": settings.serper_api_key,
        "APIFY_TOKEN": settings.apify_token,
        "META_ACCESS_TOKEN": getattr(settings, "meta_access_token", ""),
        "JINA_API_KEY": settings.jina_api_key,
    }
    return str(mapping.get(env_key, "") or "").strip()


def _message(capability: ToolCapability, configured: bool) -> str:
    if configured:
        return "已配置，可用于" + "、".join(capability.best_for[:2]) + "。"
    required = capability.requires or capability.requires_any
    return "缺少配置：" + " 或 ".join(required) + "。"
