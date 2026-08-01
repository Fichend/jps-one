from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from config.settings import get_settings
from workflows.framework_status import get_framework_status


def test_framework_status_shape() -> None:
    status = get_framework_status()

    assert status["product_name"] == "JPS One"
    assert status["domain"] == "jps-one.com"
    assert status["runtime"]["python_env"] == "conda:ai-hunter"
    assert {layer["id"] for layer in status["layers"]} >= {
        "api",
        "workflows",
        "connectors",
        "business",
        "knowledge",
        "mcp",
        "skills",
    }
    assert any(tool["name"] == "product_catalog.search" for tool in status["mcp_tools"])
    assert any(module["path"] == "/foundation" for module in status["frontend_modules"])


@pytest.mark.asyncio
async def test_framework_status_route_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setenv("API_ACCESS_TOKEN", "secret-token")
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/api/v1/jps-one/framework/status")
        authorized = await client.get(
            "/api/v1/jps-one/framework/status",
            headers={"X-API-Key": "secret-token"},
        )

    get_settings.cache_clear()
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["product_name"] == "JPS One"
