from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "config.secure_config_store.get_settings",
        lambda: type("S", (), {"hunts_dir": str(tmp_path / "hunts")})(),
    )
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_meta_config_is_saved_with_masked_secrets(client):
    resp = await client.patch(
        "/api/admin/integrations/meta_instagram",
        json={
            "enabled": True,
            "config": {
                "graph_version": "v25.0",
                "app_id": "12345",
                "app_secret": "super-secret-value",
                "access_token": "token-secret-value",
                "instagram_account_id": "1789",
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["app_secret"] == "supe****alue"
    assert data["config"]["access_token"] == "toke****alue"
    assert data["secret_status"] == {"app_secret": True, "access_token": True}

    saved = await client.get("/api/admin/integrations/meta_instagram")
    assert saved.status_code == 200
    assert "super-secret-value" not in saved.text
    assert "token-secret-value" not in saved.text


@pytest.mark.asyncio
async def test_meta_connection_test_updates_status(client):
    await client.patch(
        "/api/admin/integrations/meta_instagram",
        json={"enabled": True, "config": {"access_token": "token-secret-value"}},
    )

    with patch("business.integrations.meta_service.MetaGraphClient.test_connection", new_callable=AsyncMock) as mock_test:
        mock_test.return_value = {"me": {"id": "1", "name": "JPS"}, "assets": {"instagram": {"id": "1789"}}}
        resp = await client.post("/api/admin/integrations/meta_instagram/test")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    saved = (await client.get("/api/admin/integrations/meta_instagram")).json()
    assert saved["last_test_status"] == "ok"
    assert saved["status"] == "connected"


@pytest.mark.asyncio
async def test_social_enrich_uses_meta_connector_and_hides_raw_response(client):
    await client.patch(
        "/api/admin/integrations/meta_instagram",
        json={"enabled": True, "config": {"access_token": "token-secret-value"}},
    )

    raw = {
        "provider": "instagram",
        "handle": "jpsmedical",
        "profile": {
            "id": "1789",
            "username": "jpsmedical",
            "followers_count": 120,
            "access_token": "must-not-leak",
        },
    }
    with patch("business.integrations.meta_service.MetaGraphClient.enrich", new_callable=AsyncMock) as mock_enrich:
        mock_enrich.return_value = raw
        resp = await client.post("/api/v1/social/enrich", json={"profile_url": "https://instagram.com/jpsmedical"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["profile"]["username"] == "jpsmedical"
    assert "must-not-leak" not in resp.text
