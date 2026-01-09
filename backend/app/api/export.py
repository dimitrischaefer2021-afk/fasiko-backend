"""
Export-Download (Block 08/09)

GET /api/v1/exports/{job_id}
- liefert die ZIP-Datei eines completed export-jobs
"""

from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from ..settings import EXPORT_DIR
from .jobs import jobs_store

router = APIRouter(tags=["exports"])


@router.get("/exports/{job_id}")
def download_export(job_id: str) -> FileResponse:
    job = jobs_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job nicht gefunden.")

    if job.status != "completed" or not job.result_file:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export ist noch nicht abgeschlossen oder es existiert keine Ergebnisdatei.",
        )

    path = os.path.join(EXPORT_DIR, job.result_file)
    if not os.path.exists(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export-Datei nicht gefunden.")

    return FileResponse(path=path, filename=job.result_file, media_type="application/zip")