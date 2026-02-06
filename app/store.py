from __future__ import annotations

import threading
from typing import Optional

from app.models import ScanJobStatus


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

    def update(self, job: ScanJobStatus) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def list_all(self) -> list[ScanJobStatus]:
        with self._lock:
            return list(self._jobs.values())


job_store = JobStore()
