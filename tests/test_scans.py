from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models import JobStatus


def _fake_port_scanner():
    """Return a mock PortScanner that produces deterministic results."""
    nm = MagicMock()
    nm.all_hosts.return_value = ["127.0.0.1"]
    nm.command_line.return_value = "nmap -oX - 127.0.0.1 -p 22,80"
    nm.__getitem__ = lambda self, host: nm._host_data

    nm._host_data.state.return_value = "up"
    nm._host_data.all_protocols.return_value = ["tcp"]
    nm._host_data.__getitem__ = lambda self, proto: {
        22: {"state": "open", "name": "ssh"},
        80: {"state": "open", "name": "http"},
    }

    return nm


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_scan_returns_202(client: AsyncClient, api_key: str):
    with patch("app.scanner.nmap.PortScanner", return_value=_fake_port_scanner()):
        resp = await client.post(
            "/scans",
            json={"targets": "127.0.0.1", "ports": "22,80"},
            headers={"X-API-Key": api_key},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == JobStatus.pending


@pytest.mark.asyncio
async def test_get_scan_not_found(client: AsyncClient, api_key: str):
    resp = await client.get(
        "/scans/nonexistent",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_scans_empty(client: AsyncClient, api_key: str):
    resp = await client.get("/scans", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_scan_lifecycle(client: AsyncClient, api_key: str):
    """POST a scan, then GET by job_id to confirm it was stored."""
    with patch("app.scanner.nmap.PortScanner", return_value=_fake_port_scanner()):
        create_resp = await client.post(
            "/scans",
            json={"targets": "127.0.0.1", "ports": "22,80"},
            headers={"X-API-Key": api_key},
        )
    job_id = create_resp.json()["job_id"]

    resp = await client.get(
        f"/scans/{job_id}",
        headers={"X-API-Key": api_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["request"]["targets"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_scan_completes_with_results(client: AsyncClient, api_key: str):
    """Verify the background scan thread populates results."""
    import asyncio

    with patch("app.scanner.nmap.PortScanner", return_value=_fake_port_scanner()):
        create_resp = await client.post(
            "/scans",
            json={"targets": "127.0.0.1", "ports": "22,80"},
            headers={"X-API-Key": api_key},
        )
        job_id = create_resp.json()["job_id"]

        # Give the background thread time to finish
        for _ in range(20):
            await asyncio.sleep(0.1)
            resp = await client.get(
                f"/scans/{job_id}",
                headers={"X-API-Key": api_key},
            )
            body = resp.json()
            if body["status"] in (JobStatus.completed, JobStatus.failed):
                break

    assert body["status"] == JobStatus.completed
    assert body["result"] is not None
    assert len(body["result"]["hosts"]) == 1
    assert body["result"]["hosts"][0]["host"] == "127.0.0.1"
    assert len(body["result"]["hosts"][0]["ports"]) == 2
