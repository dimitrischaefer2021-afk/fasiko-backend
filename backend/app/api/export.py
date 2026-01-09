"""
API‑Router für Exporte (Block 08).

Dieser Router stellt einen Endpunkt bereit, über den abgeschlossene
Export‑Jobs heruntergeladen werden können. Export‑Jobs werden im
``jobs_store`` verwaltet und erzeugen beim Abschluss eine ZIP‑Datei im
Verzeichnis ``EXPORT_DIR``. Der Download‑Endpunkt prüft, ob der
angefragte Job existiert, erfolgreich abgeschlossen wurde und eine
Datei vorhanden ist, und liefert diese dann als FileResponse
zurück.

Endpunkte:
    • **GET /api/v1/exports/{job_id}** – liefert die ZIP‑Datei des
      angegebenen Jobs, sofern dieser abgeschlossen ist. Andernfalls
      wird ein HTTP‑Fehler (404) ausgegeben.

Hinweis: Dieser Endpunkt ersetzt nicht die Status‑Abfrage über
``GET /api/v1/jobs/{job_id}``, sondern ergänzt sie. Der Download
ist erst möglich, wenn ``status`` des Jobs ``completed`` ist und
``result_file`` gesetzt wurde.
"""

from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..settings import EXPORT_DIR
from .jobs import jobs_store  # Zugriff auf den in‑memory Jobs‑Store

router = APIRouter(tags=["exports"])


@router.get("/exports/{job_id}")
def download_export(job_id: str) -> FileResponse:
    """Liefert die erzeugte ZIP‑Datei eines abgeschlossenen Export‑Jobs.

    Args:
        job_id: Die ID des Jobs, dessen ZIP‑Datei heruntergeladen werden
            soll.

    Returns:
        FileResponse: Die ZIP‑Datei zum Download.

    Raises:
        HTTPException: Wenn der Job nicht existiert, nicht abgeschlossen
            ist oder die Datei nicht gefunden wurde.
    """
    job = jobs_store.get(job_id)
    if not job or job.status != "completed" or not job.result_file:
        raise HTTPException(status_code=404, detail="Export nicht bereit.")
    file_path = os.path.join(EXPORT_DIR, job.result_file)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")
    # Rückgabe der ZIP‑Datei; der Dateiname wird für den Download beibehalten
    return FileResponse(file_path, filename=job.result_file, media_type="application/zip")