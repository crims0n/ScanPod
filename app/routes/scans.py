from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import require_api_key
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
    job_store.add(job)
    submit_scan(job)
    return ScanJobCreated(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
    )


@router.get("/{job_id}", response_model=ScanJobStatus)
async def get_scan(job_id: str) -> ScanJobStatus:
    job = job_store.get(job_id)
    if job is None:
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
