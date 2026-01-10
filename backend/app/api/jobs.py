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
from ..schemas import JobCreate, JobOut, JobStatus
from ..exporter import export_artifacts_to_zip

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


@router.post("/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(job_in: JobCreate, background_tasks: BackgroundTasks) -> JobOut:
    """Erstellt einen neuen Job.

    Aktuell wird nur der Typ ``export`` unterstützt. Für einen
    Export müssen die ``artifact_ids`` angegeben werden. Optional
    kann ein ``format`` angegeben werden (Standard: ``txt``).

    Args:
        job_in: Pydantic‑Modell mit Job‑Type und Parametern.
        background_tasks: FastAPI‑BackgroundTasks, über die der
            Export im Hintergrund ausgeführt wird.

    Returns:
        JobOut: Informationen über den gestarteten Job.

    Raises:
        HTTPException: Wenn ein nicht unterstützter Job‑Typ
            angefordert wird.
    """
    if job_in.type != "export":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur der Job‑Typ 'export' wird unterstützt.",
        )

    job_id = str(uuid.uuid4())
    # Erlaubte Formate: 'txt', 'docx', 'pdf'. Standard ist 'txt'.
    file_format = job_in.format.lower() if job_in.format else "txt"
    allowed_formats = {"txt", "docx", "pdf"}
    if file_format not in allowed_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Format '{file_format}' wird nicht unterstützt. Erlaubt sind: {', '.join(sorted(allowed_formats))}.",
        )

    # Neuen Jobstatus anlegen
    job_status = JobStatus(
        id=job_id,
        type=job_in.type,
        status="queued",
        progress=0.0,
        result_file=None,
        error=None,
        created_at=datetime.utcnow(),
        completed_at=None,
    )
    jobs_store[job_id] = job_status

    # Hintergrundtask starten
    background_tasks.add_task(
        _run_export_job, job_id, job_in.artifact_ids or [], file_format
    )

    return JobOut(
        id=job_status.id,
        type=job_status.type,
        status=job_status.status,
        progress=job_status.progress,
        result_file=job_status.result_file,
        error=job_status.error,
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
    )