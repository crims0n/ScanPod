from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import nmap

from app.config import settings
from app.models import (
    HostResult,
    JobStatus,
    PortResult,
    ScanJobStatus,
    ScanResult,
)
from app.store import job_store

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=settings.max_scan_workers)


def _run_scan(job: ScanJobStatus) -> None:
    """Execute an nmap scan synchronously (called from thread pool)."""
    job = job.model_copy(
        update={
            "status": JobStatus.running,
            "started_at": datetime.now(timezone.utc),
        }
    )
    job_store.update(job)

    try:
        nm = nmap.PortScanner()
        kwargs: dict = {"arguments": job.request.arguments or ""}
        if job.request.ports:
            kwargs["ports"] = job.request.ports

        nm.scan(
            hosts=job.request.targets,
            timeout=settings.scan_timeout,
            **kwargs,
        )

        hosts: list[HostResult] = []
        for host in nm.all_hosts():
            ports: list[PortResult] = []
            for proto in nm[host].all_protocols():
                for port_num in sorted(nm[host][proto]):
                    info = nm[host][proto][port_num]
                    ports.append(
                        PortResult(
                            port=port_num,
                            protocol=proto,
                            state=info.get("state", "unknown"),
                            service=info.get("name", ""),
                        )
                    )
            hosts.append(
                HostResult(
                    host=host,
                    state=nm[host].state(),
                    ports=ports,
                )
            )

        result = ScanResult(
            hosts=hosts,
            command_line=nm.command_line(),
        )

        job = job.model_copy(
            update={
                "status": JobStatus.completed,
                "result": result,
                "completed_at": datetime.now(timezone.utc),
            }
        )
        job_store.update(job)

    except Exception as exc:
        logger.exception("Scan failed for job %s", job.job_id)
        job = job.model_copy(
            update={
                "status": JobStatus.failed,
                "error": str(exc),
                "completed_at": datetime.now(timezone.utc),
            }
        )
        job_store.update(job)


def submit_scan(job: ScanJobStatus) -> None:
    """Submit a scan job to run in the background thread pool."""
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_executor, _run_scan, job)
