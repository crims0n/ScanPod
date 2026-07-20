import logging

import pytest
from httpx import AsyncClient

from app.main import app, lifespan


@pytest.mark.asyncio
async def test_missing_api_key_is_rejected(client: AsyncClient):
    resp = await client.get("/scans")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(client: AsyncClient):
    resp = await client.get("/scans", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_api_key_returns_200(client: AsyncClient, api_key: str):
    resp = await client.get("/scans", headers={"X-API-Key": api_key})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_default_api_key_warns_at_startup(monkeypatch, caplog):
    monkeypatch.setattr("app.main.settings.api_key", "changeme")
    with caplog.at_level(logging.WARNING):
        async with lifespan(app):
            pass
    assert any("default 'changeme'" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_custom_api_key_no_startup_warning(monkeypatch, caplog):
    monkeypatch.setattr("app.main.settings.api_key", "a-strong-secret")
    with caplog.at_level(logging.WARNING):
        async with lifespan(app):
            pass
    assert not any("changeme" in r.message for r in caplog.records)
