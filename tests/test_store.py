from datetime import datetime, timedelta, timezone

from app import store as store_module
from app.models import JobStatus, ScanRequest, new_job
from app.store import JobStore


def _job(status=JobStatus.pending, completed_at=None):
    job = new_job(ScanRequest(targets="127.0.0.1"))
    updates = {}
    if status is not JobStatus.pending:
        updates["status"] = status
    if completed_at is not None:
        updates["completed_at"] = completed_at
    return job.model_copy(update=updates) if updates else job


def test_add_respects_cap(monkeypatch):
    monkeypatch.setattr(store_module.settings, "max_jobs", 2)
    monkeypatch.setattr(store_module.settings, "job_ttl_seconds", 0)
    s = JobStore()
    assert s.add(_job()) is True
    assert s.add(_job()) is True
    assert s.add(_job()) is False  # at capacity


def test_cap_zero_disables_limit(monkeypatch):
    monkeypatch.setattr(store_module.settings, "max_jobs", 0)
    monkeypatch.setattr(store_module.settings, "job_ttl_seconds", 0)
    s = JobStore()
    for _ in range(50):
        assert s.add(_job()) is True


def test_ttl_evicts_expired_terminal_jobs(monkeypatch):
    monkeypatch.setattr(store_module.settings, "max_jobs", 0)
    monkeypatch.setattr(store_module.settings, "job_ttl_seconds", 60)
    s = JobStore()
    old = _job(
        JobStatus.completed,
        completed_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    s.add(old)
    assert s.get(old.job_id) is None  # swept on access
    assert s.list_all() == []


def test_ttl_keeps_fresh_and_active_jobs(monkeypatch):
    monkeypatch.setattr(store_module.settings, "max_jobs", 0)
    monkeypatch.setattr(store_module.settings, "job_ttl_seconds", 60)
    s = JobStore()
    fresh = _job(JobStatus.completed, completed_at=datetime.now(timezone.utc))
    running = _job(JobStatus.running)  # no completed_at — never evicted
    s.add(fresh)
    s.add(running)
    ids = {j.job_id for j in s.list_all()}
    assert fresh.job_id in ids
    assert running.job_id in ids


def test_ttl_zero_disables_eviction(monkeypatch):
    monkeypatch.setattr(store_module.settings, "max_jobs", 0)
    monkeypatch.setattr(store_module.settings, "job_ttl_seconds", 0)
    s = JobStore()
    old = _job(
        JobStatus.completed,
        completed_at=datetime.now(timezone.utc) - timedelta(days=365),
    )
    s.add(old)
    assert s.get(old.job_id) is not None


def test_clear_terminal_removes_only_finished(monkeypatch):
    monkeypatch.setattr(store_module.settings, "max_jobs", 0)
    monkeypatch.setattr(store_module.settings, "job_ttl_seconds", 0)
    s = JobStore()
    now = datetime.now(timezone.utc)
    pending = _job(JobStatus.pending)
    running = _job(JobStatus.running)
    completed = _job(JobStatus.completed, completed_at=now)
    failed = _job(JobStatus.failed, completed_at=now)
    cancelled = _job(JobStatus.cancelled, completed_at=now)
    for j in (pending, running, completed, failed, cancelled):
        s.add(j)

    assert s.clear_terminal() == 3
    remaining = {j.job_id for j in s.list_all()}
    assert remaining == {pending.job_id, running.job_id}
    # Idempotent — nothing terminal left to remove.
    assert s.clear_terminal() == 0


def test_cap_frees_space_after_ttl_sweep(monkeypatch):
    monkeypatch.setattr(store_module.settings, "max_jobs", 1)
    monkeypatch.setattr(store_module.settings, "job_ttl_seconds", 60)
    s = JobStore()
    old = _job(
        JobStatus.completed,
        completed_at=datetime.now(timezone.utc) - timedelta(seconds=120),
    )
    assert s.add(old) is True
    # Store is "full" (1 job) but the sole job is expired, so add() sweeps
    # it first and then succeeds.
    assert s.add(_job()) is True
    assert s.get(old.job_id) is None
