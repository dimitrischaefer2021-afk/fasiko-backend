"""
LLM‑basierter Text‑Normalizer für BSI‑Anforderungen (Block 22).

Dieser Normalizer verbessert die aus den PDF‑Katalogen extrahierten
Titel und Beschreibungen der BSI‑Anforderungen. Die Normalisierung
geschieht in zwei Schritten:

1. Zunächst wird das kleine LLM‑Modell (8B) mit einem strikten
   Prompt aufgerufen, um nur Formatierungsfehler (Worttrennung,
   Leerzeichen, Zeilenumbrüche) zu beheben. Es dürfen keine neuen
   Inhalte erzeugt oder Aussagen verändert werden. Bei einem Fehler
   oder leerer Antwort bleibt der Originaltext erhalten.
2. Im Anschluss werden deterministische Heuristiken angewendet, die
   typische Artefakte der PDF‑Extraktion beseitigen (z. B. getrennte
   Silben, Bindestrich‑Umbrüche, mehrfache Leerzeichen). Diese
   Heuristiken sind bewusst konservativ gewählt, um den Inhalt
   unverändert zu lassen.

Das Verhalten unterscheidet sich zwischen Entwicklungs‑ (DEV) und
Produktionsumgebung (PROD):

* In DEV (ENV_PROFILE != "prod") werden alle Anforderungen
  verarbeitet, das Ergebnis jedoch **nicht** in die Datenbank
  persistiert. Stattdessen wird eine Vorschau im Feld
  ``job.result_data`` gespeichert. Für jede Anforderung wird der
  Originaltext, das LLM‑Ergebnis, der heuristisch bereinigte Text sowie
  eine Reihe von Flags zurückgegeben. Bleiben Artefakte nach der
  Verarbeitung bestehen, wird eine Warnung im ``job.error`` vermerkt.

* In PROD (ENV_PROFILE == "prod") werden die normalisierten Texte
  persistiert. Rohdaten (``raw_title`` und ``raw_description``) werden
  nur gesetzt, wenn sie noch nicht vorhanden sind. Bei Fehlern beim
  LLM‑Aufruf wird der Job abgebrochen und als ``failed`` markiert.

Die Funktionen dieses Moduls werden vom Normalisierungs‑Router und
anderen Komponenten genutzt, um eine einheitliche Normalisierung
sicherzustellen.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Optional, Iterable, Dict, Any, List

from sqlalchemy.orm import Session

from .settings import MODEL_GENERAL_8B, ENV_PROFILE
from .llm_client import call_llm
from .db import SessionLocal
from .models import BsiModule, BsiRequirement
from .api.jobs import jobs_store  # Zugriff auf den globalen Job‑Status


async def _call_llm_normalizer(text: str) -> str:
    """Ruft das LLM auf, um Formatierungsfehler im Text zu korrigieren.

    Es wird ausschließlich das kleine Modell (8B) verwendet. Der Prompt
    weist das Modell an, nur Worttrennungen, Grammatik und
    Formatierungen zu reparieren, ohne Inhalte zu verändern. Aufzählungen
    sollen als eigene Zeilen mit ``• `` bestehen bleiben. Eine leere
    Antwort bedeutet, dass das LLM keine Änderungen vornehmen wollte. In
    diesem Fall wird der ursprüngliche Text zurückgegeben. Bei einem
    Fehler wird ebenfalls der Originaltext geliefert.

    Args:
        text: Der zu normalisierende Text.

    Returns:
        Die vom LLM normalisierte Fassung oder der unveränderte Text im
        Fehlerfall.
    """
    if not text:
        return text
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
        result = await call_llm(messages=messages, model=MODEL_GENERAL_8B)
        if isinstance(result, str):
            # Leere Zeichenkette bedeutet: LLM hat keine Änderungen vorgenommen
            return result or text
        return text
    except Exception:
        # Bei Fehlern (z. B. kein Endpoint erreichbar) originalen Text verwenden
        return text


def contains_artifacts(text: Optional[str]) -> bool:
    """Erkennt typische Extraktionsartefakte in einem Text.

    Es werden folgende Muster geprüft:
    * Großbuchstabe gefolgt von Leerzeichen und mehreren Kleinbuchstaben
      (z. B. "E influss")
    * Bindestrich gefolgt von Leerzeichen innerhalb eines Wortes
      (z. B. "Sicher- heit")
    * Mehrfache Leerzeichen
    * Zeilenumbrüche innerhalb eines Fließtextes

    Args:
        text: Eingabetext

    Returns:
        True, wenn eines der Artefakte gefunden wurde, sonst False.
    """
    if not text:
        return False
    # Großbuchstabe + Leerzeichen + >=4 Kleinbuchstaben
    if re.search(r"[A-ZÄÖÜ][a-zäöüß]*\s+[a-zäöüß]{4,}", text):
        return True
    # Bindestrich + Leerzeichen mitten im Wort
    if re.search(r"-\s+[A-Za-zÄÖÜäöüß]", text):
        return True
    # Mehrere Leerzeichen
    if re.search(r"\s{2,}", text):
        return True
    # Zeilenumbrüche
    if "\n" in text:
        return True
    return False


def apply_heuristics(text: str) -> str:
    """Wendet sichere Heuristiken zur Bereinigung von Extraktionsartefakten an.

    Die folgenden Regeln werden angewandt (in der Reihenfolge):
    1. Ersetze Zeilenumbrüche durch ein Leerzeichen.
    2. Reduziere mehrfache Leerzeichen auf ein einzelnes.
    3. Verbinde Großbuchstabe + Leerzeichen + >=4 Kleinbuchstaben zu einem Wort
       (z. B. "E influss" → "Einfluss").
    4. Entferne Bindestriche am Zeilenende zusammen mit nachfolgendem Leerraum
       (z. B. "Sicher- heit" → "Sicherheit").
    5. Sorge dafür, dass Aufzählungspunkte ("•") am Zeilenanfang stehen.

    Args:
        text: Eingabetext

    Returns:
        Bereinigter Text
    """
    if not text:
        return text
    out = text
    # 1. Zeilenumbrüche entfernen
    out = out.replace("\n", " ")
    # 2. Mehrfache Leerzeichen reduzieren
    out = re.sub(r"\s{2,}", " ", out)
    # 3. Großbuchstabe + Leerzeichen + >=4 Kleinbuchstaben verbinden
    out = re.sub(r"([A-ZÄÖÜ])\s+([a-zäöüß]{4,})", r"\1\2", out)
    # 4. Bindestrich + Leerzeichen innerhalb eines Wortes verbinden
    out = re.sub(r"-\s+([A-Za-zÄÖÜäöüß])", r"\1", out)
    # 5. Aufzählungspunkte auf eigene Zeile stellen
    out = re.sub(r"\s*•\s*", "\n• ", out)
    return out.strip()


async def normalize_requirement_preview(req: BsiRequirement) -> Dict[str, Any]:
    """Normalisiert eine einzelne Anforderung für die Vorschau.

    Es werden sowohl das LLM als auch die Heuristiken angewendet. Die
    Funktion liefert ein Wörterbuch mit Originaltexten, LLM‑Antworten,
    finalen (heuristisch bereinigten) Texten sowie Flags. Fehler beim
    LLM‑Aufruf führen dazu, dass das LLM‑Ergebnis dem Rohtext entspricht
    und ``llm_used`` auf False gesetzt wird.

    Args:
        req: Die zu normalisierende Anforderung.

    Returns:
        Ein Dictionary mit den Feldern ``id``, ``req_id``, ``raw_title``,
        ``raw_description``, ``llm_title``, ``llm_description``,
        ``final_title``, ``final_description`` sowie ``flags``.
    """
    raw_title = req.raw_title or req.title
    raw_desc = req.raw_description or req.description
    # Titel
    llm_title = raw_title
    llm_used_title = False
    try:
        tmp = await _call_llm_normalizer(raw_title)
        llm_title = tmp
        llm_used_title = True
    except Exception:
        llm_title = raw_title
        llm_used_title = False
    # Beschreibung
    llm_desc = raw_desc
    llm_used_desc = False
    try:
        tmp2 = await _call_llm_normalizer(raw_desc)
        llm_desc = tmp2
        llm_used_desc = True
    except Exception:
        llm_desc = raw_desc
        llm_used_desc = False
    # Determine if LLM changed
    llm_changed = (llm_title.strip() != (raw_title or "").strip()) or (
        llm_desc.strip() != (raw_desc or "").strip()
    )
    # Heuristiken anwenden
    final_title = apply_heuristics(llm_title)
    final_desc = apply_heuristics(llm_desc)
    # Flags
    flags: Dict[str, Any] = {
        "llm_used": llm_used_title or llm_used_desc,
        "llm_changed": llm_changed,
        "heuristic_used": True,
        "artifact_before": contains_artifacts(raw_title) or contains_artifacts(raw_desc),
        "artifact_after": contains_artifacts(final_title) or contains_artifacts(final_desc),
    }
    return {
        "id": req.id,
        "req_id": req.req_id,
        "raw_title": raw_title,
        "raw_description": raw_desc,
        "llm_title": llm_title,
        "llm_description": llm_desc,
        "final_title": final_title,
        "final_description": final_desc,
        "flags": flags,
    }


async def run_normalize_job(job_id: str, catalog_id: str, module_code: Optional[str] = None) -> None:
    """Ausführung eines Normalisierungsjobs im Hintergrund (Block 22).

    In der Entwicklungsumgebung werden alle Anforderungen eines
    Katalogs (optional eines Moduls) normalisiert, aber das Ergebnis
    wird nicht persistiert. Stattdessen wird eine detaillierte Vorschau
    inklusive Flags im Job gespeichert. In der Produktion werden die
    normalisierten Texte in der Datenbank gespeichert. Fehler beim
    LLM‑Aufruf führen in PROD zum Abbruch des Jobs.

    Args:
        job_id: Die ID des Jobs.
        catalog_id: ID des BSI‑Katalogs.
        module_code: Optionaler Modulkürzel, um nur ein Modul zu verarbeiten.
    """
    job = jobs_store.get(job_id)
    if not job:
        return
    job.status = "running"
    job.error = None
    job.progress = 0.0

    db: Session = SessionLocal()
    try:
        # Module des Katalogs laden (optional filtern)
        if module_code:
            modules: Iterable[BsiModule] = [
                m
                for m in db.query(BsiModule)
                .filter(BsiModule.catalog_id == catalog_id)
                .all()
                if m.code == module_code
            ]
        else:
            modules = db.query(BsiModule).filter(BsiModule.catalog_id == catalog_id).all()
        # Anforderungen sammeln
        requirements: List[BsiRequirement] = []
        for mod in modules:
            reqs = (
                db.query(BsiRequirement)
                .filter(BsiRequirement.module_id == mod.id)
                .order_by(BsiRequirement.req_id)
                .all()
            )
            requirements.extend(reqs)
        total = len(requirements)
        # Wenn keine Anforderungen vorhanden sind, beende den Job sofort. Dies
        # verhindert, dass die Zusammenfassung eine künstliche ``total`` von 1
        # anzeigt und ermöglicht eine klare Unterscheidung zwischen
        # Katalogen ohne Anforderungen und der Normalisierung von leeren Daten.
        if total == 0:
            if ENV_PROFILE != "prod":
                job.result_data = {
                    "requirements": [],
                    "summary": {
                        "total": 0,
                        "llm_used_count": 0,
                        "llm_changed_count": 0,
                        "heuristic_used_count": 0,
                        "artifact_remaining_count": 0,
                    },
                }
            job.status = "completed"
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            # Kein Fehler, sondern einfach 0 Anforderungen
            return
        # Wenn Anforderungen vorhanden sind, setze total auf ihre Anzahl
        # ``total`` wird für die Progress‑Berechnung verwendet
        # Entwicklungsmodus: Vorschaudaten sammeln, keine Persistenz
        if ENV_PROFILE != "prod":
            result_reqs: List[Dict[str, Any]] = []
            llm_used_count = 0
            llm_changed_count = 0
            heuristic_used_count = 0
            artifact_remaining_count = 0
            for idx, req in enumerate(requirements):
                preview = await normalize_requirement_preview(req)
                result_reqs.append(preview)
                flags = preview["flags"]
                if flags.get("llm_used"):
                    llm_used_count += 1
                if flags.get("llm_changed"):
                    llm_changed_count += 1
                if flags.get("heuristic_used"):
                    heuristic_used_count += 1
                if flags.get("artifact_after"):
                    artifact_remaining_count += 1
                job.progress = (idx + 1) / total
            # Zusammenfassung
            summary = {
                "total": total,
                "llm_used_count": llm_used_count,
                "llm_changed_count": llm_changed_count,
                "heuristic_used_count": heuristic_used_count,
                "artifact_remaining_count": artifact_remaining_count,
            }
            job.result_data = {
                "requirements": result_reqs,
                "summary": summary,
            }
            job.status = "completed"
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            if artifact_remaining_count > 0:
                job.error = (
                    f"WARN: Normalization incomplete for {artifact_remaining_count}/{total} requirements; "
                    f"Artefakte verbleiben."
                )
            return
        # Produktionsmodus: Texte persistieren
        for idx, req in enumerate(requirements):
            try:
                preview = await normalize_requirement_preview(req)
            except Exception as exc:
                # Fehler beim LLM im Produktionsmodus -> Job abbrechen
                job.status = "failed"
                job.error = f"Normalisierung abgebrochen: {exc}"
                job.progress = (idx / total)
                job.completed_at = datetime.utcnow()
                db.commit()
                return
            # Rohdaten nur setzen, falls noch nicht vorhanden
            if req.raw_title is None:
                req.raw_title = req.title
            if req.raw_description is None:
                req.raw_description = req.description
            # Persistiere finalen Text
            req.title = preview["final_title"]
            req.description = preview["final_description"]
            db.add(req)
            # Periodischer Commit zur Vermeidung langer Transaktionen
            if (idx + 1) % 20 == 0:
                db.commit()
            job.progress = (idx + 1) / total
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