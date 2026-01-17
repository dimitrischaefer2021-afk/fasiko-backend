"""
API‑Router für das Verwalten von BSI‑Katalogen (Block 18).

Dieses Modul ermöglicht das Hochladen von BSI‑PDFs, deren Verarbeitung zu
strukturieren und die extrahierten Module sowie Anforderungen abzufragen.

Endpunkte:

* ``POST /api/v1/bsi/catalogs/upload`` – Upload eines oder mehrerer BSI‑PDFs.
  Für jede hochgeladene Datei wird ein neuer Katalog erzeugt. Die PDF
  wird gespeichert, der Text extrahiert und anschließend in Module und
  Anforderungen zerlegt. Das Ergebnis wird dauerhaft in der Datenbank
  gespeichert. Die Antwort gibt Auskunft über den Status der Verarbeitung.

* ``GET /api/v1/bsi/catalogs`` – Auflistung aller vorhandenen Kataloge.

* ``GET /api/v1/bsi/catalogs/{catalog_id}/modules`` – Liste aller Module
  (Bausteine) in einem Katalog.

* ``GET /api/v1/bsi/catalogs/{catalog_id}/modules/{module_id}/requirements`` –
  Liste aller Anforderungen/Maßnahmen zu einem bestimmten Modul.

Die Extraktion basiert auf ``PyPDF2``. Ist diese Bibliothek nicht installiert
oder schlägt die Extraktion fehl, wird der Upload als ``error`` markiert.
"""

from __future__ import annotations

import os
import io
import re
import uuid
from typing import List, Tuple

from fastapi import APIRouter, UploadFile, File, HTTPException, status

from ..settings import BSI_CATALOG_DIR, MAX_UPLOAD_BYTES
from ..db import SessionLocal
from .. import crud
from ..schemas import (
    BsiCatalogUploadResponse,
    BsiCatalogOut,
    BsiModuleOut,
    BsiRequirementOut,
)

# Optional: PDF‑Bibliothek. Wenn nicht vorhanden, ist keine Extraktion möglich.
try:
    from PyPDF2 import PdfReader  # type: ignore
except Exception:
    PdfReader = None  # type: ignore

router = APIRouter(tags=["bsi_catalogs"])


def _extract_pdf_text(content: bytes) -> str:
    """Extrahiert Rohtext aus einem PDF.

    Nutzt ``PyPDF2`` zum Auslesen aller Seiten. Wenn die Bibliothek nicht
    installiert ist oder die Extraktion fehlschlägt, wird ein leerer
    String zurückgegeben.
    """
    if PdfReader is None:
        return ""
    try:
        file_like = io.BytesIO(content)
        reader = PdfReader(file_like)
        texts: List[str] = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            texts.append(page_text)
        return "\n".join(texts)
    except Exception:
        return ""


def _normalize_text(text: str) -> str:
    """Normalisiert den aus dem PDF extrahierten Text.

    * Entfernt Silbentrennungen (Zeilen, die mit ``-`` enden, werden mit der
      folgenden Zeile verbunden).
    * Lässt andere Zeilen unverändert.
    Weitere Verbesserungen (z. B. Entfernen von Mehrfach‑Leerzeichen) können
    in späteren Blöcken ergänzt werden.
    """
    lines = text.splitlines()
    normalized: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Wenn Zeile mit Bindestrich endet und es eine nächste Zeile gibt, verbinde beides
        if line.endswith("-") and i < len(lines) - 1:
            next_line = lines[i + 1].lstrip()
            line = line[:-1] + next_line
            i += 1  # nächste Zeile wird übersprungen
        normalized.append(line)
        i += 1
    return "\n".join(normalized)


def _parse_modules(text: str) -> List[Tuple[str, str, List[Tuple[str, str]]]]:
    """Extrahiert Module und Anforderungen aus normalisiertem Text.

    Ein Modul beginnt mit einem Muster wie ``SYS.3.2.2 <Titel>``. Alle
    folgenden Zeilen werden untersucht, um Anforderungen zu erkennen. Eine
    Anforderung beginnt mit ``A`` gefolgt von einer Nummer (z. B. ``A1`` oder
    ``A 1``). Der Beschreibungstext einer Anforderung kann über mehrere
    Zeilen gehen, bis die nächste Anforderung oder das nächste Modul beginnt.

    :returns: Liste von Modulen, jeweils mit Code, Titel und Liste der
        Anforderungen (Req‑ID, Beschreibung).
    """
    modules: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    current_code: str | None = None
    current_title: str | None = None
    current_reqs: List[Tuple[str, str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Prüfe auf Modulcode am Zeilenanfang (z. B. SYS.3.2.2 Titel). Wir
        # verwenden hier einen negativen Ausblick, damit Zeilen wie
        # "SYS.3.2.2.A1" nicht als neues Modul erkannt werden. Nach dem
        # Modulcode muss ein Leerzeichen folgen, ansonsten wird die Zeile
        # übersprungen und als möglicher Requirement‑Eintrag behandelt.
        m = re.match(r"([A-Z]{2,4}\.[0-9]+(?:\.[0-9]+)*)\s+(.+)", stripped)
        if m:
            # Vorheriges Modul abschließen
            if current_code:
                modules.append((current_code, current_title or "", current_reqs))
            current_code = m.group(1)
            current_title = m.group(2).strip()
            current_reqs = []
            continue
        # Anforderungen parsen. Ein Requirement kann als "A1", "A 1" oder
        # inklusive Modulpräfix wie "SYS.3.2.2.A1" erscheinen. Wir erlauben
        # optional ein vorangestelltes Modul (Buchstaben + Zahlen mit Punkten)
        # und einen Punkt vor der Kennung A. Danach folgt eine Nummer und
        # optional ein Trennzeichen (. : - oder Leerzeichen) vor dem
        # Beschreibungstext.
        if current_code:
            rm = re.match(
                r"(?:([A-Z]{2,4}\.[0-9]+(?:\.[0-9]+)*)\.)?[Aa]\s*\.?\s*(\d+)[\.:\-\s]*(.*)",
                stripped,
            )
            if rm:
                # Ermittle Modulpräfix aus dem Match oder verwende das aktuelle Modul
                mod_prefix = rm.group(1) if rm.group(1) else current_code
                number = rm.group(2)
                remainder = rm.group(3).strip()

                # Suche nach der ersten Klassifizierung (B|S|H) in Klammern. Wir
                # verwenden re.search, damit normative Texte mit eigenen Klammern
                # nicht fälschlich als Teil des Titels erkannt werden. Wenn kein
                # Klassifizierungsbuchstabe gefunden wird, nehmen wir den gesamten
                # remainder als Titel.
                class_match = re.search(r"\(([BSH])\)", remainder)
                if class_match:
                    end_idx = class_match.end()
                    title_with_class = remainder[:end_idx].strip()
                    normative = remainder[end_idx:].strip()
                else:
                    title_with_class = remainder
                    normative = ""

                # Compose requirement id als vollständiger BSI‑Code inkl. Titel.
                # Eine nachfolgende Normativbeschreibung wird getrennt gespeichert.
                req_id = f"{mod_prefix}.A{number} {title_with_class}"
                desc = normative
                current_reqs.append((req_id, desc))
            else:
                # Zeile gehört zur letzten Anforderung (Fortsetzung)
                if current_reqs and stripped:
                    last_id, last_desc = current_reqs[-1]
                    current_reqs[-1] = (last_id, (last_desc + " " + stripped).strip())
    # Letztes Modul anhängen
    if current_code:
        modules.append((current_code, current_title or "", current_reqs))

    # Dedupliziere Module nach ihrem Code. Wenn derselbe Code mehrfach auftaucht,
    # wird nur der erste Eintrag behalten und seine Anforderungen ggf. um die
    # Anforderungen der späteren Einträge ergänzt. So werden Listen wie
    # "IND.2.3 Sensoren und Aktoren" und "IND.2.3 Sensoren und Aktoren R2 IT-System"
    # zu einem Modul zusammengeführt.
    dedup: dict[str, Tuple[str, List[Tuple[str, str]]]] = {}
    for code, title, reqs in modules:
        if code not in dedup:
            dedup[code] = (title, list(reqs))
        else:
            # Füge neue Requirements an bestehende Liste an
            dedup[code][1].extend(reqs)

    # Konvertiere zurück in eine geordnete Liste (Reihenfolge der ersten Vorkommen)
    result: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    for code, (title, reqs) in dedup.items():
        result.append((code, title, reqs))
    return result


@router.post(
    "/bsi/catalogs/upload",
    response_model=List[BsiCatalogUploadResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_bsi_catalogs(file: List[UploadFile] = File(...)) -> List[BsiCatalogUploadResponse]:
    """Lädt einen oder mehrere BSI‑Kataloge als PDF hoch und verarbeitet sie.

    Für jede hochgeladene Datei wird ein neuer Katalog angelegt. Die PDF
    wird im durch ``BSI_CATALOG_DIR`` konfigurierten Verzeichnis gespeichert.
    Anschließend wird versucht, den Text zu extrahieren und daraus Module
    (Bausteine) sowie Anforderungen abzuleiten. Das Ergebnis wird in der
    Datenbank gespeichert und als Antwort zurückgegeben.
    """
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")
    responses: List[BsiCatalogUploadResponse] = []
    os.makedirs(BSI_CATALOG_DIR, exist_ok=True)
    db = SessionLocal()
    try:
        for upload in file:
            original_name = upload.filename or "catalog.pdf"
            content = await upload.read()
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Datei {original_name} überschreitet die maximale Größe von {MAX_UPLOAD_BYTES} Bytes.",
                )
            # Dateiname sichern und abspeichern
            uid = str(uuid.uuid4())
            safe_name = f"{uid}_{original_name}"
            storage_path = os.path.join(BSI_CATALOG_DIR, safe_name)
            with open(storage_path, "wb") as f:
                f.write(content)
            # Extrahiere Text
            text = _extract_pdf_text(content)
            status_str = "ok"
            message: str | None = None
            modules_data: List[Tuple[str, str, List[Tuple[str, str]]]] = []
            if not text.strip():
                status_str = "error"
                message = "No text extracted or PDF reader not available"
            else:
                normalized = _normalize_text(text)
                modules_data = _parse_modules(normalized)
                if not modules_data:
                    status_str = "partial"
                    message = "Keine Bausteine gefunden"
            # Persistiere Katalog auch bei partial oder error (Module können leer sein)
            try:
                catalog = crud.create_bsi_catalog(
                    db,
                    filename=original_name,
                    storage_path=storage_path,
                    modules_data=modules_data,
                )
                responses.append(
                    BsiCatalogUploadResponse(
                        id=catalog.id,
                        version=catalog.version,
                        status=status_str,
                        message=message,
                    )
                )
            except Exception as exc:
                db.rollback()
                responses.append(
                    BsiCatalogUploadResponse(id="", version=0, status="error", message=str(exc))
                )
        db.commit()
    finally:
        db.close()
    return responses


@router.get("/bsi/catalogs", response_model=List[BsiCatalogOut])
def list_bsi_catalogs() -> List[BsiCatalogOut]:
    """Listet alle verfügbaren BSI‑Kataloge auf."""
    db = SessionLocal()
    try:
        catalogs = crud.list_bsi_catalogs(db)
        return catalogs
    finally:
        db.close()


@router.get("/bsi/catalogs/{catalog_id}/modules", response_model=List[BsiModuleOut])
def list_bsi_modules(catalog_id: str) -> List[BsiModuleOut]:
    """Gibt alle Module eines bestimmten Katalogs zurück."""
    db = SessionLocal()
    try:
        catalog = crud.get_bsi_catalog(db, catalog_id)
        if catalog is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Catalog not found")
        modules = crud.list_bsi_modules(db, catalog_id)
        return modules
    finally:
        db.close()


@router.get(
    "/bsi/catalogs/{catalog_id}/modules/{module_id}/requirements",
    response_model=List[BsiRequirementOut],
)
def list_bsi_requirements(catalog_id: str, module_id: str) -> List[BsiRequirementOut]:
    """Gibt alle Anforderungen eines Moduls zurück."""
    db = SessionLocal()
    try:
        module = crud.get_bsi_module(db, module_id)
        if module is None or module.catalog_id != catalog_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
        requirements = crud.list_bsi_requirements(db, module_id)
        return requirements
    finally:
        db.close()