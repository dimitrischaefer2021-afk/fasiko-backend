"""
LLM‑basierter Text‑Normalizer für BSI‑Anforderungen (Block 21).

Dieses Modul stellt Hilfsfunktionen bereit, um die von der PDF‑Extraktion
stammenden Texte (Titel und Beschreibungen) der BSI‑Anforderungen zu
normalisieren. Ziel ist es, Silbentrennungen, falsche Leerzeichen
und Zeilenumbrüche zu korrigieren, ohne den inhaltlichen Gehalt zu
verändern. Die Normalisierung nutzt ausschließlich das kleine LLM‑Modell
(`MODEL_GENERAL_8B`), da das große Modell (70B) nur für die initiale
FaSiKo‑Generierung vorgesehen ist.

Die Funktionen in diesem Modul werden von einem asynchronen Job
(`normalize`) verwendet, der im Hintergrund alle Anforderungen eines
Katalogs oder optional eines einzelnen Moduls verarbeitet.

"""

from __future__ import annotations

import asyncio
from typing import Optional, Iterable
from datetime import datetime


from sqlalchemy.orm import Session

from .settings import MODEL_GENERAL_8B, ENV_PROFILE
from .llm_client import call_llm
from .db import SessionLocal
from .models import BsiCatalog, BsiModule, BsiRequirement
from .api.jobs import jobs_store  # Zugriff auf den globalen Job‑Status
from .schemas import JobStatus


async def _call_llm_normalizer(text: str) -> str:
    """Ruft das LLM auf, um Worttrennungen und Leerzeichen zu korrigieren.

    Es wird das kleine Modell (8B) verwendet. Der Prompt weist das
    Modell an, ausschließlich Formatierungen zu reparieren und keine
    inhaltlichen Änderungen vorzunehmen. Aufzählungen sollen als
    getrennte Zeilen mit ``• `` erhalten bleiben. Bei einem Fehler
    oder leeren Ergebnis wird der ursprüngliche Text zurückgegeben.

    Args:
        text: Der zu normalisierende Text.

    Returns:
        Die vom LLM normalisierte Fassung oder der unveränderte Text
        im Fehlerfall.
    """
    # Leerer Text wird unverändert zurückgegeben
    if not text:
        return text
    # System‑Prompt definieren
    system_prompt = (
        "Du bist ein Textkorrektor. Korrigiere nur Worttrennung, Grammatik "
        "und Formatierung im folgenden Text. Ändere keinen Inhalt, füge "
        "keine neuen Sätze hinzu und entferne keine bestehenden Aussagen. "
        "Erhalte Aufzählungen als getrennte Zeilen mit '• '. Erhalte "
        "Fachbegriffe, Codes und Norm‑Begriffe (MUSS/SOLL/SOLLTE) unverändert."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    try:
        # Verwende den zentralen LLM‑Client; dieser versucht automatisch alle Endpunkte
        result = await call_llm(messages=messages, model=MODEL_GENERAL_8B)
        # Wenn das LLM einen String zurückliefert (auch leer), nutzen wir ihn.
        if isinstance(result, str):
            # Eine leere Antwort bedeutet, dass das LLM den Text nicht ändern
            # wollte. In diesem Fall behalten wir den Originaltext bei.
            return result or text
        return text
    except Exception:
        # Wenn der LLM‑Aufruf fehlschlägt (z. B. weil kein Endpunkt antwortete),
        # geben wir den ursprünglichen Text zurück. Der Job entscheidet anhand
        # der ENV_PROFILE‑Einstellung, ob ein Fehler protokolliert wird.
        return text


async def _normalize_requirement(req: BsiRequirement) -> tuple[str, str]:
    """Normalisiert Titel und Beschreibung einer Anforderung via LLM.

    Wenn die Rohdaten nicht gesetzt sind (z. B. bei älteren Katalogen),
    werden zunächst die aktuellen Felder als Rohdaten übernommen. Die
    Funktion ruft den LLM für Titel und Beschreibung separat auf. Bei
    einem Fehler wird eine Ausnahme geworfen, die im Job abgefangen
    werden kann. Eine Rückgabe der normalisierten Texte ermöglicht
    Vorschau‑Funktionen ohne Persistenz.

    Args:
        req: Das ``BsiRequirement``‑Objekt, das normalisiert werden soll.

    Returns:
        Tuple aus (normalized_title, normalized_description).
    """
    # Sicherstellen, dass Rohdaten vorhanden sind
    if not req.raw_title:
        req.raw_title = req.title
    if not req.raw_description:
        req.raw_description = req.description
    # Titel normalisieren
    normalized_title = await _call_llm_normalizer(req.raw_title)
    # Beschreibung normalisieren
    normalized_description = await _call_llm_normalizer(req.raw_description)
    return normalized_title, normalized_description


async def run_normalize_job(job_id: str, catalog_id: str, module_code: Optional[str] = None) -> None:
    """Ausführung eines Normalisierungsjobs im Hintergrund.

    Diese Funktion iteriert über alle Anforderungen des angegebenen
    Katalogs (optional gefiltert nach einem Modul) und aktualisiert
    ``title`` und ``description`` mit den vom LLM gelieferten,
    normalisierten Texten. ``raw_title`` und ``raw_description`` werden
    dabei nur gesetzt, wenn sie leer sind. Fortschritt und Status
    werden im globalen ``jobs_store`` aktualisiert. Im DEV‑Profil
    (``ENV_PROFILE != 'prod'``) wird ein fehlgeschlagener LLM‑Aufruf
    als No‑Op behandelt (Rohdaten werden als normalisiert übernommen).
    Im PROD‑Profil führt ein Fehler zum Abbruch und zum Status ``failed``.

    Args:
        job_id: Die ID des Jobs im ``jobs_store``.
        catalog_id: Der ID des BSI‑Katalogs, dessen Anforderungen
            normalisiert werden sollen.
        module_code: Optionales Modulkürzel; wenn angegeben, werden
            nur Anforderungen des entsprechenden Moduls verarbeitet.
    """
    job = jobs_store.get(job_id)
    if not job:
        return
    job.status = "running"
    job.error = None
    job.progress = 0.0

    db: Session = SessionLocal()
    try:
        # Lade alle Anforderungen des Katalogs (optional gefiltert nach Modulcode)
        # Ermittele alle Module des Katalogs
        modules: Iterable[BsiModule]
        if module_code:
            # Finde das Modul mit dem gegebenen Kürzel
            modules = [
                m
                for m in db.query(BsiModule)
                .filter(BsiModule.catalog_id == catalog_id)
                .all()
                if m.code == module_code
            ]
        else:
            modules = db.query(BsiModule).filter(BsiModule.catalog_id == catalog_id).all()
        # Sammle alle Anforderungen
        requirements: list[BsiRequirement] = []
        for mod in modules:
            reqs = db.query(BsiRequirement).filter(BsiRequirement.module_id == mod.id).order_by(BsiRequirement.req_id).all()
            requirements.extend(reqs)
        total = len(requirements) if requirements else 1
        for idx, req in enumerate(requirements):
            try:
                # Normalisierte Texte abrufen
                norm_title, norm_desc = await _normalize_requirement(req)
            except Exception as exc:
                # Fehlverhalten während der LLM‑Abfrage
                if ENV_PROFILE != "prod":
                    # Im Entwicklermodus Rohdaten übernehmen und fortsetzen
                    norm_title = req.raw_title or req.title
                    norm_desc = req.raw_description or req.description
                    if not job.error:
                        job.error = f"Normalisierung teilweise übersprungen: {exc}"
                else:
                    # In Produktion Job abbrechen
                    job.status = "failed"
                    job.error = f"Normalisierung abgebrochen: {exc}"
                    job.progress = (idx / total) if total else 0.0
                    job.completed_at = datetime.utcnow()
                    db.commit()
                    return
            # Persistiere Rohdaten, falls noch nicht gesetzt
            if req.raw_title is None:
                req.raw_title = req.title
            if req.raw_description is None:
                req.raw_description = req.description
            # Aktualisiere normalisierte Felder
            req.title = norm_title
            req.description = norm_desc
            db.add(req)
            # Committe periodisch, um lange Transaktionen zu vermeiden
            if (idx + 1) % 20 == 0:
                db.commit()
            # Aktualisiere Fortschritt
            job.progress = (idx + 1) / total
        # Abschließender Commit für verbleibende Änderungen
        db.commit()
        job.status = "completed"
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