"""Framework status service for the JPS One foundation.

This module gives the frontend and operators a single read-only view of the new
architecture skeleton. It deliberately avoids external calls and secrets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_tools.schemas.tool_contracts import list_tool_contracts


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent


FRAMEWORK_LAYERS: list[dict[str, Any]] = [
    {
        "id": "api",
        "name": "API",
        "path": "backend/api",
        "status": "active-compatible",
        "description": "FastAPI routes remain compatible while new JPS One routes are added.",
    },
    {
        "id": "workflows",
        "name": "Workflow",
        "path": "backend/workflows",
        "status": "foundation",
        "description": "Long-running orchestration layer for hunts, matching, email, quote, and integration sync.",
    },
    {
        "id": "agents",
        "name": "Agent",
        "path": "backend/agents",
        "status": "active-migration",
        "description": "Existing AI agents stay active and will gradually move to JPS One structured outputs.",
    },
    {
        "id": "connectors",
        "name": "Connector",
        "path": "backend/connectors",
        "status": "foundation",
        "description": "External providers and deterministic adapters: search, web reader, Meta, WhatsApp, email, files.",
    },
    {
        "id": "business",
        "name": "Business",
        "path": "backend/business",
        "status": "foundation",
        "description": "JPS-specific lead, product, matching, quote, and CRM rules.",
    },
    {
        "id": "knowledge",
        "name": "Knowledge / RAG",
        "path": "backend/knowledge",
        "status": "foundation",
        "description": "RAG schemas, ingestion, retrieval, stores, and citation contracts.",
    },
    {
        "id": "mcp",
        "name": "MCP Tools",
        "path": "backend/mcp_tools",
        "status": "foundation",
        "description": "Agent-facing tool contracts for products, leads, knowledge, integrations, matching, and quotes.",
    },
    {
        "id": "skills",
        "name": "Skill Runtime",
        "path": "backend/skills_runtime",
        "status": "foundation",
        "description": "Project-local skill playbooks for cloud ops, lead hunting, matching, email, quote, and diagnostics.",
    },
]


FRONTEND_MODULES: list[dict[str, str]] = [
    {"id": "dashboard", "name": "任务看板", "path": "/", "status": "active"},
    {"id": "hunts", "name": "新建任务", "path": "/hunts/new", "status": "active"},
    {"id": "foundation", "name": "系统框架", "path": "/foundation", "status": "foundation"},
    {"id": "leads", "name": "客户池", "path": "/leads", "status": "foundation"},
    {"id": "products", "name": "产品库", "path": "/products", "status": "foundation"},
    {"id": "matches", "name": "匹配中心", "path": "/matches", "status": "foundation"},
    {"id": "quotes", "name": "报价中心", "path": "/quotes", "status": "foundation"},
    {"id": "knowledge", "name": "知识库", "path": "/knowledge", "status": "foundation"},
    {"id": "integrations", "name": "配置中心", "path": "/integration-center", "status": "active-foundation"},
    {"id": "settings", "name": "系统设置", "path": "/settings", "status": "active"},
]


def _readme_exists(relative_path: str) -> bool:
    return (PROJECT_ROOT / relative_path / "README.md").is_file() or (BACKEND_ROOT / relative_path.replace("backend/", "", 1) / "README.md").is_file()


def get_framework_status() -> dict[str, Any]:
    layers = []
    for layer in FRAMEWORK_LAYERS:
        item = dict(layer)
        item["readme"] = _readme_exists(str(layer["path"]))
        layers.append(item)

    return {
        "product_name": "JPS One",
        "domain": "jps-one.com",
        "positioning": "JPS 医疗外贸智能获客、客户匹配、报价与跟进工作台",
        "execution_strategy": "旁路搭建、逐步迁移、回归验证、再替换入口",
        "runtime": {"python_env": "conda:ai-hunter", "backend_entry": "api.app:app"},
        "layers": layers,
        "frontend_modules": FRONTEND_MODULES,
        "mcp_tools": list_tool_contracts(),
        "next_steps": [
            "完成 CURRENT_STATE.md，冻结线上和本地差异。",
            "将 README 改成 JPS One 专属说明。",
            "逐步把旧 tools/agents/api 迁移到新边界。",
            "先实现只读 RAG/MCP 工具，再开放写操作。",
        ],
    }
