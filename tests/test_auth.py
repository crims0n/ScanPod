import pytest
from httpx import AsyncClient


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
