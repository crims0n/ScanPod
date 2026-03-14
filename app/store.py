from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

from app.models import JobStatus, ScanJobStatus


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, ScanJobStatus] = {}

    def add(self, job: ScanJobStatus) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[ScanJobStatus]:
        with self._lock:
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
        """Mark a pending or running job as cancelled. Returns the updated job, or None if not found or already terminal."""
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
            return list(self._jobs.values())


job_store = JobStore()
