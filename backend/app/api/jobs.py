"""
API-Router für Jobs (Block 07/09).

- POST /api/v1/jobs (type=export) startet Export
- GET  /api/v1/jobs/{id} liefert Status

Block 09:
- Export nutzt echte Artefakt-Inhalte aus DB
- Formate: txt, md, docx, pdf
- Ergebnis immer ZIP (result_file = {job_id}.zip)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..schemas import JobCreate, JobOut, JobStatus
from ..exporter import export_artifacts_to_zip

router = APIRouter(tags=["jobs"])

# In-memory Job Store (MVP)
jobs_store: Dict[str, JobStatus] = {}


def _to_job_out(job: JobStatus) -> JobOut:
    return JobOut(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=float(job.progress),
        result_file=job.result_file,
        error=job.error,
    )


def _run_export_job(job_id: str, artifact_ids: List[str], file_format: str) -> None:
    # Open own DB session in background task
    db: Session = SessionLocal()
    try:
        job = jobs_store.get(job_id)
        if not job:
            return

        job.status = "running"
        job.progress = 0.0
        job.error = None

        # Export as ZIP
        zip_name, _zip_path = export_artifacts_to_zip(
            db=db,
            artifact_ids=artifact_ids,
            export_format=file_format,
            job_id=job_id,
        )

        job.result_file = zip_name
        job.progress = 1.0
        job.status = "completed"
        job.completed_at = datetime.utcnow()
    except Exception as exc:
        job = jobs_store.get(job_id)
        if job:
            job.status = "failed"
            job.error = str(exc)
            job.progress = 0.0
            job.completed_at = datetime.utcnow()
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(job_in: JobCreate, background_tasks: BackgroundTasks) -> JobOut:
    if job_in.type != "export":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur der Job-Typ 'export' wird unterstützt.",
        )

    job_id = str(uuid.uuid4())
    fmt = (job_in.format or "md").lower().strip()

    job = JobStatus(
        id=job_id,
        type="export",
        status="queued",
        progress=0.0,
        result_file=None,
        error=None,
        created_at=datetime.utcnow(),
        completed_at=None,
    )
    jobs_store[job_id] = job

    background_tasks.add_task(_run_export_job, job_id, job_in.artifact_ids or [], fmt)
    return _to_job_out(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str) -> JobOut:
    job = jobs_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job nicht gefunden.")
    return _to_job_out(job)