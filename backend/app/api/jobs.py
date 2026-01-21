"""
API-Router für Jobs.

Dieser Router implementiert einen einfachen Job-Service, mit dem langlaufende Aufgaben
gestartet und überwacht werden können. Der Job-Status wird aktuell im Speicher gehalten
(jobs_store) und ist damit für DEV/Tests geeignet.

Unterstützte Job-Typen:
- export: Exportiert Artefakte als ZIP (txt/md/docx/pdf).
- generate: Generiert Artefakte via LLM (Job).
- edit: Erstellt eine neue Version eines Artefakts via LLM inkl. Diff (Job).

Endpunkte (unter /api/v1/... durch Haupt-Router):
- POST /jobs
- GET  /jobs/{job_id}
"""

from __future__ import annotations

import difflib
import os
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from .. import crud, generator
from ..db import SessionLocal
from ..exporter import export_artifacts_to_zip
from ..jobs_store import jobs_store
from ..schemas import (
    ArtifactCreate,
    ArtifactVersionCreate,
    JobCreate,
    JobOut,
    JobStatus,
    OpenPointCreate,
)

router = APIRouter(tags=["jobs"])


async def _run_export_job(job_id: str, artifact_ids: List[str], file_format: str) -> None:
    """Hintergrundaufgabe: Export von Artefakten als ZIP."""
    job = jobs_store.get(job_id)
    if not job:
        return

    job.status = "running"
    job.error = None
    job.progress = 0.0

    db = SessionLocal()
    try:
        _, zip_path = export_artifacts_to_zip(
            db=db,
            artifact_ids=artifact_ids or [],
            export_format=file_format,
            job_id=job_id,
        )
        job.status = "completed"
        job.result_file = os.path.basename(zip_path)
        job.progress = 1.0
        job.completed_at = datetime.utcnow()
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.progress = 0.0
        job.completed_at = datetime.utcnow()
    finally:
        try:
            db.close()
        except Exception:
            pass


async def _run_generate_job(job_id: str, project_id: str, types: List[str]) -> None:
    """Hintergrundaufgabe: Generierung von Artefakten via LLM."""
    job = jobs_store.get(job_id)
    if not job:
        return

    job.status = "running"
    job.error = None
    job.progress = 0.0

    db = SessionLocal()
    try:
        proj = crud.get_project(db, project_id)
        if proj is None:
            job.status = "failed"
            job.error = "Project not found"
            job.progress = 0.0
            job.completed_at = datetime.utcnow()
            return

        project_name = proj.name
        result_items: List[dict] = []
        total = max(len(types), 1)

        title_map = {
            "strukturanalyse": "Strukturanalyse",
            "schutzbedarf": "Schutzbedarfsfeststellung",
            "modellierung": "Modellierung",
            "grundschutz_check": "IT-Grundschutz-Check",
            "risikoanalyse": "Risikoanalyse",
            "maßnahmenplan": "Maßnahmen-/Umsetzungsplan",
            "sicherheitskonzept": "Sicherheitskonzept",
        }

        for idx, art_type in enumerate(types or []):
            internal_type = art_type.strip().lower()
            title = title_map.get(internal_type, internal_type)

            content_md, open_points_raw = await generator.generate_artifact_content(
                internal_type, project_name
            )

            existing = [a for a in crud.list_artifacts(db, project_id) if a.type == internal_type]
            if existing:
                art = existing[0]
                version = crud.create_version(
                    db,
                    art.id,
                    ArtifactVersionCreate(content_md=content_md, make_current=True),
                )
            else:
                art_payload = ArtifactCreate(
                    type=internal_type,
                    title=title,
                    initial_content_md=content_md,
                    status="draft",
                )
                art = crud.create_artifact(db, project_id, art_payload)
                version = crud.get_current_version(db, art.id, art.current_version)

            open_point_ids: List[str] = []
            for op in open_points_raw or []:
                question = (op or {}).get("question")
                if not question:
                    continue
                payload_op = OpenPointCreate(
                    question=question,
                    input_type="text",
                    priority="wichtig",
                    status="offen",
                    artifact_id=art.id,
                    category=(op or {}).get("category"),
                )
                op_rec = crud.create_open_point(db, project_id, payload_op)
                open_point_ids.append(op_rec.id)

            result_items.append(
                {
                    "artifact_id": art.id,
                    "version": getattr(version, "version", None),
                    "open_points": open_point_ids,
                }
            )

            job.progress = (idx + 1) / total

        job.status = "completed"
        job.result_data = {"items": result_items}
        job.progress = 1.0
        job.completed_at = datetime.utcnow()
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.progress = 0.0
        job.completed_at = datetime.utcnow()
    finally:
        try:
            db.close()
        except Exception:
            pass


async def _run_edit_job(job_id: str, project_id: str, artifact_id: str, instructions: str) -> None:
    """Hintergrundaufgabe: Bearbeitung eines Artefakts via LLM (neue Version + Diff)."""
    job = jobs_store.get(job_id)
    if not job:
        return

    job.status = "running"
    job.error = None
    job.progress = 0.0

    db = SessionLocal()
    try:
        art = crud.get_artifact(db, project_id, artifact_id)
        if art is None:
            job.status = "failed"
            job.error = "Artifact not found"
            job.progress = 0.0
            job.completed_at = datetime.utcnow()
            return

        cur = crud.get_current_version(db, art.id, art.current_version)
        current_md = (cur.content_md if cur else "") or ""
        if not current_md.strip():
            job.status = "failed"
            job.error = "Current document is empty"
            job.progress = 0.0
            job.completed_at = datetime.utcnow()
            return

        new_md = await generator.edit_artifact_content(instructions, current_md)
        version = crud.create_version(
            db, art.id, ArtifactVersionCreate(content_md=new_md, make_current=False)
        )

        diff_lines = difflib.unified_diff(
            current_md.splitlines(),
            new_md.splitlines(),
            fromfile=f"v{art.current_version}",
            tofile=f"v{getattr(version, 'version', 'new')}",
            lineterm="",
        )
        diff_text = "\n".join(list(diff_lines))

        job.status = "completed"
        job.result_data = {
            "artifact_id": art.id,
            "new_version": getattr(version, "version", None),
            "diff": diff_text,
        }
        job.progress = 1.0
        job.completed_at = datetime.utcnow()
    except Exception as exc:
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
async def create_job(job_in: JobCreate, background_tasks: BackgroundTasks) -> JobOut:
    """Erstellt einen neuen Job."""
    job_type = (job_in.type or "").lower().strip()
    job_id = str(uuid.uuid4())

    job_status = JobStatus(
        id=job_id,
        type=job_type,
        status="queued",
        progress=0.0,
        result_file=None,
        error=None,
        created_at=datetime.utcnow(),
        completed_at=None,
        result_data=None,
    )
    jobs_store[job_id] = job_status

    if job_type == "export":
        file_format = (job_in.format or "txt").lower()
        allowed_formats = {"txt", "md", "docx", "pdf"}
        if file_format not in allowed_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Format '{file_format}' wird nicht unterstützt. "
                    f"Erlaubt sind: {', '.join(sorted(allowed_formats))}."
                ),
            )
        artifact_ids = job_in.artifact_ids or []
        if not artifact_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Für den Export müssen artifact_ids angegeben werden.",
            )
        background_tasks.add_task(_run_export_job, job_id, artifact_ids, file_format)

    elif job_type == "generate":
        if not job_in.project_id or not job_in.types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Für generate müssen project_id und types angegeben werden.",
            )
        background_tasks.add_task(_run_generate_job, job_id, job_in.project_id, job_in.types)

    elif job_type == "edit":
        if not job_in.project_id or not job_in.artifact_id or not job_in.instructions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Für edit müssen project_id, artifact_id und instructions angegeben werden.",
            )
        background_tasks.add_task(
            _run_edit_job, job_id, job_in.project_id, job_in.artifact_id, job_in.instructions
        )

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job-Typ '{job_in.type}' wird nicht unterstützt.",
        )

    return JobOut(
        id=job_status.id,
        type=job_status.type,
        status=job_status.status,
        progress=job_status.progress,
        result_file=job_status.result_file,
        error=job_status.error,
        result_data=job_status.result_data,
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str) -> JobOut:
    """Gibt den Status eines Jobs zurück."""
    job = jobs_store.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job nicht gefunden.")
    return JobOut(
        id=job.id,
        type=job.type,
        status=job.status,
        progress=job.progress,
        result_file=job.result_file,
        error=job.error,
        result_data=job.result_data,
    )
