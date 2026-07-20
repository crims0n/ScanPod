import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_api_key

logger = logging.getLogger(__name__)
from app.models import ScanJobCreated, ScanJobStatus, ScanJobSummary, ScanRequest, new_job
from app.scanner import submit_scan
from app.store import job_store

router = APIRouter(
    prefix="/scans",
    dependencies=[Depends(require_api_key)],
)


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ScanJobCreated)
async def create_scan(req: ScanRequest) -> ScanJobCreated:
    job = new_job(req)
    if not job_store.add(job):
        logger.warning("Scan job rejected — store at capacity")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Job store is at capacity — purge finished jobs (DELETE /scans) or wait for retention to expire",
        )
    submit_scan(job)
    logger.info("Scan job %s created for targets=%s", job.job_id, req.targets)
    return ScanJobCreated(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
    )


@router.get("/{job_id}", response_model=ScanJobStatus)
async def get_scan(job_id: str) -> ScanJobStatus:
    job = job_store.get(job_id)
    if job is None:
        logger.warning("Scan job %s not found", job_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job


@router.get("", response_model=list[ScanJobSummary])
async def list_scans() -> list[ScanJobSummary]:
    return [
        ScanJobSummary(job_id=job.job_id, status=job.status)
        for job in job_store.list_all()
    ]


@router.delete("")
async def purge_scans() -> dict:
    """Delete all finished (completed/failed/cancelled) jobs; leaves active jobs."""
    deleted = job_store.clear_terminal()
    logger.info("Purged %d finished job(s)", deleted)
    return {"deleted": deleted}


@router.post("/{job_id}/cancel", response_model=ScanJobStatus)
async def cancel_scan(job_id: str) -> ScanJobStatus:
    job = job_store.get(job_id)
    if job is None:
        logger.warning("Cancel requested for unknown job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    cancelled = job_store.cancel(job_id)
    if cancelled is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job cannot be cancelled in status '{job.status.value}' — it has already finished",
        )
    logger.info("Scan job %s cancelled", job_id)
    return cancelled


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(job_id: str) -> None:
    job = job_store.get(job_id)
    if job is None:
        logger.warning("Delete requested for unknown job %s", job_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if not job_store.remove(job_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job cannot be deleted in status '{job.status.value}' — cancel it first",
        )
    logger.info("Scan job %s deleted", job_id)
