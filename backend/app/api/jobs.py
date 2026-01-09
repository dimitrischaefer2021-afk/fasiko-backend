"""
API‑Router für Jobs (Block 07).

Dieser Router implementiert einen einfachen Job‑Service, über den
langlaufende Aufgaben gestartet und überwacht werden können. Aktuell
wird nur der Export von Artefakten unterstützt. Ein Export erstellt
für jedes ausgewählte Artefakt eine einfache Textdatei und packt
alle Dateien in ein ZIP‑Archiv. Die Dateien enthalten einen
Placeholder‑Inhalt, da im Minimal‑Repository keine Artefakt‑Daten
vorliegen. Die ZIP‑Datei wird im konfigurierten ``EXPORT_DIR``
gespeichert und kann später heruntergeladen werden.

Endpunkte:
    • POST ``/api/v1/jobs`` startet einen neuen Job. Der Request
      erwartet ein ``JobCreate``‑Objekt mit ``type='export'``, einer
      Liste von ``artifact_ids`` und optional einem ``format``. Der
      Server erstellt einen Eintrag im ``jobs_store``, startet im
      Hintergrund einen Export und gibt die Job‑ID zurück.
    • GET ``/api/v1/jobs/{job_id}`` liefert den aktuellen Status
      eines Jobs. Ist der Job abgeschlossen, enthält die Antwort
      außerdem den Namen der ZIP‑Datei zur Abholung.

Der Job‑Status kann folgende Werte annehmen: ``queued``, ``running``,
``completed`` oder ``failed``. Fortschritt wird als Wert zwischen
0.0 und 1.0 zurückgegeben. Fehlermeldungen werden im Feld
``error`` ausgegeben.

Hinweis: Diese Implementierung verwendet einen in‑memory ``jobs_store``
und ist nicht für den produktiven Einsatz gedacht. In einer späteren
Version sollte der Job‑Status persistiert und eine robuste
Export‑Funktion implementiert werden.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

import zipfile
from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from ..schemas import JobCreate, JobOut, JobStatus
from ..settings import EXPORT_DIR


# In‑Memory‑Speicher für Jobs. Jeder Eintrag enthält Informationen
# über den aktuellen Status, Fortschritt und das Ergebnis (Dateiname).
jobs_store: Dict[str, JobStatus] = {}

router = APIRouter(tags=["jobs"])


async def _run_export_job(job_id: str, artifact_ids: List[str], file_format: str) -> None:
    """Hintergrundfunktion zum Exportieren ausgewählter Artefakte.

    Für jedes ``artifact_id`` wird eine Textdatei mit einem
    Placeholder‑Inhalt generiert. Anschließend werden alle Dateien
    in eine ZIP‑Datei gepackt und im EXPORT_DIR abgelegt. Der
    Fortschritt des Jobs wird im ``jobs_store`` aktualisiert.

    Args:
        job_id: Die ID des Jobs.
        artifact_ids: Liste der zu exportierenden Artefakt‑IDs.
        file_format: Zielformat der Dateien (derzeit nur ``txt``
            unterstützt; andere Werte werden ignoriert).
    """
    # Vorbereitungen: sicherstellen, dass das Export‑Verzeichnis existiert
    os.makedirs(EXPORT_DIR, exist_ok=True)

    job = jobs_store.get(job_id)
    if not job:
        return
    job.status = "running"
    job.error = None
    job.progress = 0.0

    tmp_dir = os.path.join(EXPORT_DIR, f"tmp_{job_id}")
    os.makedirs(tmp_dir, exist_ok=True)

    total = len(artifact_ids) if artifact_ids else 1
    completed = 0

    try:
        for art_id in artifact_ids:
            # Simulierter Export: Schreibe eine Placeholder‑Datei
            filename = f"{art_id}.{file_format}"
            file_path = os.path.join(tmp_dir, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(
                    f"Dies ist ein Platzhalter für den Export des Artefakts {art_id}.\n"
                )
            completed += 1
            job.progress = completed / total
            # Kurze Pause simuliert die Verarbeitung (ohne CPU zu blockieren)
            await asyncio.sleep(0)

        # Alle Dateien in ZIP packen
        zip_name = f"{job_id}.zip"
        zip_path = os.path.join(EXPORT_DIR, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for filename in os.listdir(tmp_dir):
                file_path = os.path.join(tmp_dir, filename)
                zipf.write(file_path, arcname=filename)

        # Aufräumen
        for filename in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, filename))
        os.rmdir(tmp_dir)

        # Job abschließen
        job.status = "completed"
        job.result_file = zip_name
        job.progress = 1.0
        job.completed_at = datetime.utcnow()
    except Exception as exc:
        # Fehlerbehandlung
        job.status = "failed"
        job.error = str(exc)
        job.progress = 0.0
        job.completed_at = datetime.utcnow()


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
    # Standardformat ist 'txt' – nur dieses Format wird im Minimal‑Backend unterstützt.
    file_format = job_in.format if job_in.format else "txt"

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