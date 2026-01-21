"""
API-Router: BSI-Normalisierung (Block 22)

Endpunkte (unter /api/v1/...):
- POST /bsi/catalogs/{catalog_id}/normalize
- GET  /bsi/catalogs/{catalog_id}/normalize/preview
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from ..db import SessionLocal
from ..jobs_store import jobs_store, Job
from ..models import BsiModule, BsiRequirement
from ..normalizer import normalize_requirement_preview, run_normalize_job
from ..schemas import BsiNormalizationPreviewOut, JobOut

router = APIRouter(tags=["bsi_normalize"])


def _job_to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        result_file=job.result_file,
        error=job.error,
        result_data=job.result_data,
    )


@router.post(
    "/bsi/catalogs/{catalog_id}/normalize",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_catalog_normalization(
    catalog_id: str,
    background_tasks: BackgroundTasks,
    module_code: Optional[str] = Query(
        default=None,
        description="Optional: Nur ein Modul-Code, z. B. SYS.3.2.2",
    ),
) -> JobOut:
    """Startet einen Normalisierungsjob und liefert die Job-ID zurück."""
    # WICHTIG: jobs_store ist ein Objekt (JobsStore), kein Dict.
    job = jobs_store.create("normalize")
    jobs_store.set(job)

    background_tasks.add_task(run_normalize_job, job.id, catalog_id, module_code)

    return _job_to_out(job)


@router.get(
    "/bsi/catalogs/{catalog_id}/normalize/preview",
    response_model=BsiNormalizationPreviewOut,
)
async def preview_catalog_normalization(
    catalog_id: str,
    limit: int = Query(default=5, ge=1, le=50),
    module_code: Optional[str] = Query(
        default=None,
        description="Optional: Nur ein Modul-Code, z. B. SYS.3.2.2",
    ),
) -> BsiNormalizationPreviewOut:
    """
    Gibt eine Vorschau der Normalisierung zurück (ohne Persistenz).

    Mapping:
    normalize_requirement_preview() -> final_*  (intern)
    API Schema erwartet normalized_*.
    """
    db = SessionLocal()
    try:
        q = db.query(BsiModule).filter(BsiModule.catalog_id == catalog_id)
        if module_code:
            q = q.filter(BsiModule.code == module_code)
        modules: List[BsiModule] = q.all()

        if not modules:
            raise HTTPException(status_code=404, detail="Keine Module für diesen Katalog gefunden.")

        items: List[dict] = []

        for mod in modules:
            reqs = (
                db.query(BsiRequirement)
                .filter(BsiRequirement.module_id == mod.id)
                .order_by(BsiRequirement.req_id)
                .all()
            )

            for r in reqs:
                prev = await normalize_requirement_preview(r)
                items.append(
                    {
                        "req_id": prev.get("req_id") or "",
                        "raw_title": prev.get("raw_title") or "",
                        "normalized_title": prev.get("final_title") or "",
                        "raw_description": prev.get("raw_description") or "",
                        "normalized_description": prev.get("final_description") or "",
                    }
                )
                if len(items) >= limit:
                    break

            if len(items) >= limit:
                break

        return BsiNormalizationPreviewOut(items=items)

    finally:
        try:
            db.close()
        except Exception:
            pass
