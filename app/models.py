from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Request ---

class ScanRequest(BaseModel):
    targets: str
    ports: Optional[str] = None
    arguments: Optional[str] = None


# --- Result hierarchy ---

class PortResult(BaseModel):
    port: int
    protocol: str
    state: str
    service: str = ""


class HostResult(BaseModel):
    host: str
    state: str = "unknown"
    ports: list[PortResult] = []


class ScanResult(BaseModel):
    hosts: list[HostResult] = []
    command_line: str = ""


# --- Job lifecycle ---

class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ScanJobSummary(BaseModel):
    job_id: str
    status: JobStatus


class ScanJobCreated(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime


class ScanJobStatus(BaseModel):
    job_id: str
    status: JobStatus
    request: ScanRequest
    result: Optional[ScanResult] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# --- Factory ---

def new_job(request: ScanRequest) -> ScanJobStatus:
    return ScanJobStatus(
        job_id=uuid.uuid4().hex,
        status=JobStatus.pending,
        request=request,
        created_at=datetime.now(timezone.utc),
    )
