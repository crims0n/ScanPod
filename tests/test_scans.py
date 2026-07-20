from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models import (
    HostResult,
    JobStatus,
    ScanRequest,
    ScanResult,
    new_job,
)
from app.store import job_store


def _seed_job(status: JobStatus, **updates):
    """Add a job in a given state directly to the store, bypassing the scanner."""
    job = new_job(ScanRequest(targets="127.0.0.1"))
    if status is not JobStatus.pending or updates:
        job = job.model_copy(update={"status": status, **updates})
    job_store.add(job)
    return job.job_id


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


# --- cancel semantics ---

@pytest.mark.asyncio
async def test_cancel_pending_job(client: AsyncClient, api_key: str):
    job_id = _seed_job(JobStatus.pending)
    resp = await client.post(f"/scans/{job_id}/cancel", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.json()["status"] == JobStatus.cancelled


@pytest.mark.asyncio
async def test_cancel_completed_job_is_409_and_preserves_result(
    client: AsyncClient, api_key: str
):
    result = ScanResult(hosts=[HostResult(host="127.0.0.1", state="up")])
    job_id = _seed_job(JobStatus.completed, result=result)

    resp = await client.post(f"/scans/{job_id}/cancel", headers={"X-API-Key": api_key})
    assert resp.status_code == 409
    # Message uses the plain status value, not the enum repr.
    assert "'completed'" in resp.json()["detail"]

    # The completed result must survive an attempted cancel.
    detail = await client.get(f"/scans/{job_id}", headers={"X-API-Key": api_key})
    body = detail.json()
    assert body["status"] == JobStatus.completed
    assert body["result"]["hosts"][0]["host"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_cancel_failed_job_is_409(client: AsyncClient, api_key: str):
    job_id = _seed_job(JobStatus.failed, error="boom")
    resp = await client.post(f"/scans/{job_id}/cancel", headers={"X-API-Key": api_key})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_already_cancelled_job_is_409(client: AsyncClient, api_key: str):
    job_id = _seed_job(JobStatus.cancelled)
    resp = await client.post(f"/scans/{job_id}/cancel", headers={"X-API-Key": api_key})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_unknown_job_is_404(client: AsyncClient, api_key: str):
    resp = await client.post("/scans/nonexistent/cancel", headers={"X-API-Key": api_key})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_scan_returns_429_at_capacity(
    client: AsyncClient, api_key: str, monkeypatch
):
    monkeypatch.setattr("app.store.settings.max_jobs", 1)
    monkeypatch.setattr("app.store.settings.job_ttl_seconds", 0)
    with patch("app.scanner.nmap.PortScanner", return_value=_fake_port_scanner()):
        first = await client.post(
            "/scans", json={"targets": "127.0.0.1"}, headers={"X-API-Key": api_key}
        )
        second = await client.post(
            "/scans", json={"targets": "127.0.0.1"}, headers={"X-API-Key": api_key}
        )
    assert first.status_code == 202
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_purge_scans_removes_finished_only(client: AsyncClient, api_key: str):
    now = datetime.now(timezone.utc)
    active = _seed_job(JobStatus.running)
    _seed_job(JobStatus.completed, completed_at=now, result=ScanResult(hosts=[]))
    _seed_job(JobStatus.failed, completed_at=now, error="boom")

    resp = await client.delete("/scans", headers={"X-API-Key": api_key})
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 2}

    listing = await client.get("/scans", headers={"X-API-Key": api_key})
    remaining = [j["job_id"] for j in listing.json()]
    assert remaining == [active]


@pytest.mark.asyncio
async def test_purge_scans_frees_capacity(client: AsyncClient, api_key: str, monkeypatch):
    monkeypatch.setattr("app.store.settings.max_jobs", 1)
    monkeypatch.setattr("app.store.settings.job_ttl_seconds", 0)
    now = datetime.now(timezone.utc)
    _seed_job(JobStatus.completed, completed_at=now)

    # Store is full; a new scan is rejected...
    with patch("app.scanner.nmap.PortScanner", return_value=_fake_port_scanner()):
        rejected = await client.post(
            "/scans", json={"targets": "127.0.0.1"}, headers={"X-API-Key": api_key}
        )
    assert rejected.status_code == 429

    # ...until we purge, then it succeeds.
    await client.delete("/scans", headers={"X-API-Key": api_key})
    with patch("app.scanner.nmap.PortScanner", return_value=_fake_port_scanner()):
        accepted = await client.post(
            "/scans", json={"targets": "127.0.0.1"}, headers={"X-API-Key": api_key}
        )
    assert accepted.status_code == 202
