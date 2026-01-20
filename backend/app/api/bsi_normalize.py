"""
API‑Router für die LLM‑Normalisierung von BSI‑Anforderungen (Block 21).

Dieser Router stellt Endpunkte bereit, um die Normalisierung als
Hintergrundjob zu starten und eine Vorschau der normalisierten
Anforderungen anzuzeigen. Die Normalisierung korrigiert lediglich
Worttrennungen, falsche Leerzeichen und andere Extraktionsartefakte
ohne den Inhalt zu verändern. Sie nutzt das kleine LLM‑Modell
(8B) und läuft asynchron, damit große Kataloge das Backend nicht
blockieren.
"""

from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Query

from ..db import SessionLocal
from ..models import BsiModule, BsiRequirement
from ..api.jobs import jobs_store
from ..schemas import JobStatus, JobOut, BsiNormalizationPreviewItem, BsiNormalizationPreviewOut
# Importiere die neue Normalisierungs‑Pipeline. _normalize_requirement bleibt
# erhalten für rückwärtige Kompatibilität, wird hier aber nicht genutzt.
from ..normalizer import run_normalize_job, normalize_requirement_preview
from datetime import datetime


router = APIRouter(tags=["bsi_normalize"])


@router.post("/bsi/catalogs/{catalog_id}/normalize", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def start_normalization(
    catalog_id: str,
    background_tasks: BackgroundTasks,
    module_code: Optional[str] = Query(
        default=None,
        description="Optionaler Code eines Moduls. Wenn gesetzt, wird nur dieses Modul normalisiert."
    ),
) -> JobOut:
    """Startet einen Normalisierungsjob für einen BSI‑Katalog.

    Es wird ein neuer Eintrag im ``jobs_store`` erzeugt und eine
    Hintergrundaufgabe gestartet. Der Job verarbeitet alle
    Anforderungen des angegebenen Katalogs (oder nur die eines
    Moduls) und aktualisiert ``title`` sowie ``description`` mit
    den vom LLM gelieferten, normalisierten Texten. Rohdaten werden
    einmalig gesetzt.

    Args:
        catalog_id: ID des zu normalisierenden Katalogs.
        background_tasks: Von FastAPI bereitgestellter Task‑Scheduler.
        module_code: Optionaler Modulkürzel; begrenzt den Job auf ein Modul.

    Returns:
        JobOut: Status des angelegten Jobs mit ID und initialem Status.
    """
    # Erzeuge eine neue Job‑ID und Statusobjekt
    import uuid
    job_id = str(uuid.uuid4())
    job_status = JobStatus(
        id=job_id,
        type="normalize",
        status="queued",
        progress=0.0,
        result_file=None,
        error=None,
        created_at=datetime.utcnow(),
        completed_at=None,
        result_data=None,
    )
    jobs_store[job_id] = job_status
    # Starte Hintergrundaufgabe
    background_tasks.add_task(run_normalize_job, job_id, catalog_id, module_code)
    return JobOut(
        id=job_status.id,
        type=job_status.type,
        status=job_status.status,
        progress=job_status.progress,
        result_file=job_status.result_file,
        error=job_status.error,
        result_data=job_status.result_data,
    )


@router.get("/bsi/catalogs/{catalog_id}/normalize/preview", response_model=BsiNormalizationPreviewOut)
async def preview_normalization(
    catalog_id: str,
    limit: int = Query(3, ge=1, le=50, description="Anzahl der Anforderungen, die angezeigt werden sollen."),
    module_code: Optional[str] = Query(
        default=None,
        description="Optionaler Modulkürzel; wenn gesetzt, werden nur Anforderungen dieses Moduls in der Vorschau berücksichtigt."
    ),
) -> BsiNormalizationPreviewOut:
    """Liefert eine Vorschau der normalisierten Anforderungen.

    Diese Vorschau zeigt für die ersten ``limit`` Anforderungen des
    angegebenen Katalogs (optional eines Moduls) den originalen
    Titel und Beschreibung sowie die vom LLM berechnete normalisierte
    Fassung. Die Vorschau führt **keine** Persistierung durch.

    Args:
        catalog_id: Katalog, für den die Vorschau erstellt werden soll.
        limit: Maximale Anzahl der Vorschau‑Einträge.
        module_code: Optionaler Modulcode zum Filtern.

    Returns:
        BsiNormalizationPreviewOut mit einer Liste von Vorschau‑Elementen.
    """
    db = SessionLocal()
    try:
        # Hole alle Module des Katalogs (optional gefiltert)
        if module_code:
            modules: List[BsiModule] = [
                m
                for m in db.query(BsiModule)
                .filter(BsiModule.catalog_id == catalog_id)
                .all()
                if m.code == module_code
            ]
        else:
            modules = db.query(BsiModule).filter(BsiModule.catalog_id == catalog_id).all()
        requirements: List[BsiRequirement] = []
        for mod in modules:
            reqs = (
                db.query(BsiRequirement)
                .filter(BsiRequirement.module_id == mod.id)
                .order_by(BsiRequirement.req_id)
                .all()
            )
            requirements.extend(reqs)
        # Begrenzen auf die ersten ``limit`` Anforderungen
        requirements = requirements[:limit]
        items: List[BsiNormalizationPreviewItem] = []
        for req in requirements:
            # Stelle sicher, dass Rohdaten vorhanden sind
            raw_title = req.raw_title or req.title
            raw_desc = req.raw_description or req.description
            # Versuche, den Text mit dem LLM und Heuristiken zu normalisieren.
            try:
                preview = await normalize_requirement_preview(req)
                norm_title = preview["final_title"]
                norm_desc = preview["final_description"]
            except Exception as exc:
                # In der Entwicklungsumgebung liefern wir den Originaltext zurück,
                # um die Vorschau nicht zu blockieren. In Produktion schlagen wir fehl.
                from ..settings import ENV_PROFILE
                if ENV_PROFILE != "prod":
                    norm_title = raw_title
                    norm_desc = raw_desc
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Fehler bei der LLM‑Normalisierung: {exc}",
                    )
            items.append(
                BsiNormalizationPreviewItem(
                    req_id=req.req_id,
                    raw_title=raw_title,
                    normalized_title=norm_title,
                    raw_description=raw_desc,
                    normalized_description=norm_desc,
                )
            )
        return BsiNormalizationPreviewOut(items=items)
    finally:
        try:
            db.close()
        except Exception:
            pass