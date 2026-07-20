from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.validation import validate_arguments, validate_ports, validate_targets


# --- Request ---

class ScanRequest(BaseModel):
    targets: str
    ports: Optional[str] = None
    arguments: Optional[str] = None
    timeout: Optional[int] = None

    @field_validator("targets")
    @classmethod
    def _check_targets(cls, v: str) -> str:
        return validate_targets(v)

    @field_validator("ports")
    @classmethod
    def _check_ports(cls, v: Optional[str]) -> Optional[str]:
        return validate_ports(v)

    @field_validator("arguments")
    @classmethod
    def _check_arguments(cls, v: Optional[str]) -> Optional[str]:
        return validate_arguments(v)


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
    cancelled = "cancelled"


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
