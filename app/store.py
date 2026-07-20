from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.models import JobStatus, ScanJobStatus

logger = logging.getLogger(__name__)

_TERMINAL = (JobStatus.completed, JobStatus.failed, JobStatus.cancelled)


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ScanJobStatus] = {}

    def _evict_expired_locked(self) -> None:
        """Drop terminal jobs older than the TTL. Assumes the lock is held."""
        ttl = settings.job_ttl_seconds
        if ttl <= 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl)
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in _TERMINAL
            and job.completed_at is not None
            and job.completed_at < cutoff
        ]
        for job_id in expired:
            del self._jobs[job_id]
        if expired:
            logger.info("Evicted %d expired job(s) past TTL", len(expired))

    def add(self, job: ScanJobStatus) -> bool:
        """Store a new job. Returns False if the store is at capacity."""
        with self._lock:
            self._evict_expired_locked()
            if settings.max_jobs > 0 and len(self._jobs) >= settings.max_jobs:
                return False
            self._jobs[job.job_id] = job
            return True

    def get(self, job_id: str) -> Optional[ScanJobStatus]:
        with self._lock:
            self._evict_expired_locked()
            return self._jobs.get(job_id)

    def update(self, job: ScanJobStatus) -> bool:
        """Update a job. Returns False if the job was cancelled and the update was skipped."""
        with self._lock:
            current = self._jobs.get(job.job_id)
            if current is not None and current.status == JobStatus.cancelled:
                return False
            self._jobs[job.job_id] = job
            return True

    def cancel(self, job_id: str) -> Optional[ScanJobStatus]:
        """Mark a pending or running job as cancelled and return it.

        Returns None if the job is not found or is already in a terminal state
        (completed, failed, or cancelled) — a finished job cannot be cancelled,
        and its result is left untouched.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status not in (JobStatus.pending, JobStatus.running):
                return None
            cancelled = job.model_copy(
                update={
                    "status": JobStatus.cancelled,
                    "completed_at": datetime.now(timezone.utc),
                }
            )
            self._jobs[job_id] = cancelled
            return cancelled

    def remove(self, job_id: str) -> bool:
        """Delete a job. Returns False if not found or not in a terminal state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status not in (JobStatus.completed, JobStatus.failed, JobStatus.cancelled):
                return False
            del self._jobs[job_id]
            return True

    def list_all(self) -> list[ScanJobStatus]:
        with self._lock:
            self._evict_expired_locked()
            return list(self._jobs.values())


job_store = JobStore()
