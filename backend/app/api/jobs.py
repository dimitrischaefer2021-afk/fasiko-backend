"""
API‑Router für Jobs.

Dieser Router implementiert einen einfachen Job‑Service, mit dem
langlaufende Aufgaben gestartet und überwacht werden können. Aktuell
unterstützt der Service ausschließlich den Jobtyp ``export``. Ein
Export erstellt für jedes ausgewählte Artefakt eine Datei im
gewünschten Format und packt alle Dateien in ein ZIP‑Archiv. Die
Formate ``txt``, ``md``, ``docx`` und ``pdf`` werden unterstützt
(siehe ``backend/app/exporter.py``). Die ZIP‑Datei wird im
konfigurierten ``EXPORT_DIR`` abgelegt und kann über den Export‑
Download‑Endpunkt heruntergeladen werden.

Endpunkte:
    • **POST** ``/api/v1/jobs`` – Startet einen neuen Job. Der Request
      erwartet ein ``JobCreate``‑Objekt mit ``type='export'``, einer
      Liste von Artefakt‑IDs (``artifact_ids``) und optional einem
      ``format``. Der Server erstellt einen Eintrag im in‑memory
      ``jobs_store``, startet im Hintergrund einen Export und gibt
      die Job‑ID zurück.
    • **GET** ``/api/v1/jobs/{job_id}`` – Liefert den aktuellen
      Status eines Jobs. Ist der Job abgeschlossen, enthält die
      Antwort außerdem den Namen der ZIP‑Datei zur Abholung.

Der Job‑Status kann folgende Werte annehmen: ``queued``, ``running``,
``completed`` oder ``failed``. Fortschritt wird als Wert zwischen 0.0
und 1.0 zurückgegeben. Fehlermeldungen werden im Feld ``error``
ausgegeben. Diese Implementierung speichert den Job‑Status nur im
Speicher und ist nicht für den produktiven Einsatz gedacht; in einer
späteren Version sollte der Status persistiert und der Export robuster
gestaltet werden.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from ..db import SessionLocal
from ..schemas import JobCreate, JobOut, JobStatus, ArtifactCreate, ArtifactVersionCreate, OpenPointCreate
from ..exporter import export_artifacts_to_zip
from .. import crud, generator
import difflib

jobs_store: Dict[str, JobStatus] = {}

router = APIRouter(tags=["jobs"])


async def _run_export_job(job_id: str, artifact_ids: List[str], file_format: str) -> None:
    """Hintergrundaufgabe für den Export von Artefakten.

    Diese Funktion öffnet eine eigene Datenbank‑Session, ruft den
    Exporter auf, um die ausgewählten Artefakte in das gewünschte
    Format zu schreiben und als ZIP‑Archiv zu speichern. Der
    Fortschritt des Jobs wird im ``jobs_store`` aktualisiert.

    Args:
        job_id: Eindeutige ID des Jobs.
        artifact_ids: Liste der zu exportierenden Artefakt‑IDs.
        file_format: ``txt``, ``md``, ``docx`` oder ``pdf``.
    """
    job = jobs_store.get(job_id)
    if not job:
        return

    job.status = "running"
    job.error = None
    job.progress = 0.0

    # Datenbank‑Session öffnen
    db = SessionLocal()
    try:
        # Export durchführen
        _, zip_path = export_artifacts_to_zip(
            db=db,
            artifact_ids=artifact_ids or [],
            export_format=file_format,
            job_id=job_id,
        )
        # Job abschließen
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
    """Hintergrundaufgabe zur Generierung von Artefakten via LLM.

    Für jedes angegebene Artefakt‑Typ wird der Inhalt generiert und als
    neue Version gespeichert. Existiert das Artefakt noch nicht, wird es
    mit der generierten Version 1 angelegt. Offene Punkte werden
    persistiert. Das Ergebnis (Liste der Artefakte, Versionen und
    Open‑Point‑IDs) wird im Job gespeichert.

    Args:
        job_id: Eindeutige Job‑ID
        project_id: Projekt‑ID
        types: Liste der Artefakt‑Typen
    """
    job = jobs_store.get(job_id)
    if not job:
        return
    job.status = "running"
    job.error = None
    job.progress = 0.0

    db = SessionLocal()
    try:
        # Projekt laden
        proj = crud.get_project(db, project_id)
        if proj is None:
            job.status = "failed"
            job.error = "Project not found"
            job.progress = 0.0
            job.completed_at = datetime.utcnow()
            db.close()
            return
        project_name = proj.name
        result_items: List[dict] = []
        total = len(types) if types else 1
        for idx, art_type in enumerate(types or []):
            internal_type = art_type.strip().lower()
            title_map = {
                "strukturanalyse": "Strukturanalyse",
                "schutzbedarf": "Schutzbedarfsfeststellung",
                "modellierung": "Modellierung",
                "grundschutz_check": "IT‑Grundschutz‑Check",
                "risikoanalyse": "Risikoanalyse",
                "maßnahmenplan": "Maßnahmen‑/Umsetzungsplan",
                "sicherheitskonzept": "Sicherheitskonzept",
            }
            title = title_map.get(internal_type, internal_type)
            # Inhalt generieren
            content_md, open_points_raw = await generator.generate_artifact_content(internal_type, project_name)
            # Existierendes Artefakt prüfen
            existing = [a for a in crud.list_artifacts(db, project_id) if a.type == internal_type]
            if existing:
                art = existing[0]
                version = crud.create_version(db, art.id, ArtifactVersionCreate(content_md=content_md, make_current=True))
            else:
                # neues Artefakt mit Version 1 anlegen
                art_payload = ArtifactCreate(type=internal_type, title=title, initial_content_md=content_md, status="draft")
                art = crud.create_artifact(db, project_id, art_payload)
                version = crud.get_current_version(db, art.id, art.current_version)
            # offene Punkte persistieren
            open_point_ids: List[str] = []
            for op in open_points_raw:
                question = op.get("question")
                if not question:
                    continue
                category = op.get("category")
                payload_op = OpenPointCreate(
                    question=question,
                    input_type="text",
                    priority="wichtig",
                    status="offen",
                    artifact_id=art.id,
                    category=category,
                )
                op_rec = crud.create_open_point(db, project_id, payload_op)
                open_point_ids.append(op_rec.id)
            result_items.append({
                "artifact_id": art.id,
                "version": version.version,
                "open_points": open_point_ids,
            })
            # Fortschritt aktualisieren
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
    """Hintergrundaufgabe zur Bearbeitung eines Artefakts via LLM.

    Args:
        job_id: Die Job‑ID
        project_id: ID des Projekts
        artifact_id: ID des zu bearbeitenden Artefakts
        instructions: Anweisung für die Überarbeitung
    """
    job = jobs_store.get(job_id)
    if not job:
        return
    job.status = "running"
    job.error = None
    job.progress = 0.0
    db = SessionLocal()
    try:
        # Artefakt laden
        art = crud.get_artifact(db, project_id, artifact_id)
        if art is None:
            job.status = "failed"
            job.error = "Artifact not found"
            job.progress = 0.0
            job.completed_at = datetime.utcnow()
            db.close()
            return
        cur = crud.get_current_version(db, art.id, art.current_version)
        current_md = cur.content_md if cur else ""
        if not current_md.strip():
            job.status = "failed"
            job.error = "Current document is empty"
            job.progress = 0.0
            job.completed_at = datetime.utcnow()
            db.close()
            return
        # LLM aufrufen
        new_md = await generator.edit_artifact_content(instructions, current_md)
        # neue Version anlegen (nicht automatisch aktuell setzen)
        version = crud.create_version(db, art.id, ArtifactVersionCreate(content_md=new_md, make_current=False))
        # diff berechnen
        diff_lines = difflib.unified_diff(
            current_md.splitlines(),
            new_md.splitlines(),
            fromfile=f"v{art.current_version}",
            tofile=f"v{version.version}",
            lineterm="",
        )
        diff_text = "\n".join(list(diff_lines))
        job.status = "completed"
        job.result_data = {
            "artifact_id": art.id,
            "new_version": version.version,
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
    """Erstellt einen neuen Job.

    Unterstützte Typen:

    * ``export`` – exportiert Artefakte in ein bestimmtes Format. Erfordert
      ``artifact_ids`` und optional ``format``.
    * ``generate`` – generiert Artefakte via LLM. Erfordert
      ``project_id`` und ``types``.
    * ``edit`` – bearbeitet ein bestehendes Artefakt via LLM. Erfordert
      ``project_id``, ``artifact_id`` und ``instructions``.

    Args:
        job_in: Pydantic‑Modell mit Job‑Type und Parametern.
        background_tasks: BackgroundTasks, um Jobs im Hintergrund auszuführen.

    Returns:
        JobOut mit Status und Job‑ID.

    Raises:
        HTTPException bei fehlenden oder ungültigen Parametern.
    """
    job_type = job_in.type.lower()
    # Erzeuge eine eindeutige Job‑ID
    job_id = str(uuid.uuid4())

    # Gemeinsam genutzte Struktur für den Jobstatus
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

    # Verarbeitung nach Typ
    if job_type == "export":
        # Erlaubte Formate: 'txt', 'docx', 'pdf'
        file_format = job_in.format.lower() if job_in.format else "txt"
        allowed_formats = {"txt", "docx", "pdf"}
        if file_format not in allowed_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Format '{file_format}' wird nicht unterstützt. Erlaubt sind: {', '.join(sorted(allowed_formats))}.",
            )
        # Export erfordert artifact_ids
        artifact_ids = job_in.artifact_ids or []
        if not artifact_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Für den Export müssen artifact_ids angegeben werden.",
            )
        # Hintergrundtask starten
        background_tasks.add_task(
            _run_export_job, job_id, artifact_ids, file_format
        )

    elif job_type == "generate":
        # Validate required parameters
        if not job_in.project_id or not job_in.types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Für generate müssen project_id und types angegeben werden.",
            )
        # Hintergrundtask starten
        background_tasks.add_task(
            _run_generate_job, job_id, job_in.project_id, job_in.types
        )

    elif job_type == "edit":
        # Validate required parameters
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
            detail=f"Job‑Typ '{job_in.type}' wird nicht unterstützt.",
        )

    # Rückgabe des initialen Status
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
    """Gibt den Status eines Jobs zurück.

    Args:
        job_id: Die ID des Jobs.

    Returns:
        JobOut: Informationen über den Job.

    Raises:
        HTTPException: Wenn kein Job mit der angegebenen ID existiert.
    """
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