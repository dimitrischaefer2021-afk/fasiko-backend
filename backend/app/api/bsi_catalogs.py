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

from fastapi import APIRouter, UploadFile, File, HTTPException, status, BackgroundTasks

from ..settings import BSI_CATALOG_DIR, MAX_UPLOAD_BYTES
from ..db import SessionLocal
from .. import crud
from ..schemas import (
    BsiCatalogUploadResponse,
    BsiCatalogOut,
    BsiModuleOut,
    BsiRequirementOut,
)

# PDF‑Bibliotheken. Für eine layout‑bewusste Extraktion verwenden wir
# ``pdfplumber``. Diese Bibliothek nutzt pdfminer.six und rekonstruiert
# Textblöcke anhand der X‑Y‑Koordinaten. Damit bleiben Zeilenumbrüche,
# Einrückungen und Listen erhalten, was für BSI‑Kataloge mit Aufzählungen
# hilfreich ist. Falls ``pdfplumber`` nicht vorhanden ist oder bei der
# Extraktion scheitert, greifen wir auf ``PyPDF2`` zurück, das reinen
# Fließtext liefert.
try:
    import pdfplumber  # type: ignore
except Exception:
    pdfplumber = None  # type: ignore

try:
    from PyPDF2 import PdfReader  # type: ignore
except Exception:
    PdfReader = None  # type: ignore

router = APIRouter(tags=["bsi_catalogs"])


def _extract_pdf_text(content: bytes) -> str:
    """Extrahiert Rohtext aus einem PDF.

    Die Extraktion erfolgt bevorzugt mit ``pdfplumber`` und fallweise mit
    ``PyPDF2``. ``pdfplumber`` bietet eine layoutbewusste Extraktion, die
    Zeilenumbrüche, Einrückungen und Listen besser erhält. Um die oft
    unregelmäßigen Wortabstände in BSI‑PDFs zu korrigieren, verwenden wir
    spezifische Parameter für ``x_tolerance`` und ``line_overlap``. Wenn
    ``pdfplumber`` nicht installiert ist oder bei der Extraktion ein Fehler
    auftritt, wird ``PyPDF2`` als Fallback genutzt.

    :param content: Die binären Daten der PDF-Datei.
    :returns: Der extrahierte Text mit Zeilenumbrüchen; im Fehlerfall ein
        leerer String.
    """
    # Bevorzugt pdfplumber verwenden, sofern verfügbar
    if pdfplumber is not None:
        try:
            file_like = io.BytesIO(content)
            text_parts: List[str] = []
            with pdfplumber.open(file_like) as pdf:
                for page in pdf.pages:
                    try:
                        # x_tolerance und line_overlap sorgen für bessere Wortabstände
                        page_text = page.extract_text(x_tolerance=2, line_overlap=0.5) or ""
                    except Exception:
                        page_text = ""
                    text_parts.append(page_text)
            return "\n".join(text_parts)
        except Exception:
            # Bei Fehlern auf pdfplumber-Fallback verzichten und PyPDF2 verwenden
            pass
    # Fallback: PyPDF2, wenn verfügbar
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
        # Im Fehlerfall leeren String zurückgeben
        return ""


def _cleanup_description(text: str) -> str:
    """Bereinigt den normativen Beschreibungstext einer Anforderung.

    PDF‑Extraktionen leiden häufig unter fehlenden Leerzeichen und
    Silbentrennungen. Diese Funktion wendet einfache Heuristiken an, um
    das Ergebnis lesbarer zu machen:

    * Entfernt Bindestriche innerhalb eines Wortes, wenn sie von
      Buchstaben eingerahmt sind (z. B. ``Regelun-gen`` → ``Regelungen``).
    * Fügt ein Leerzeichen nach Satzzeichen (``.``, `,`) ein, falls
      direkt danach kein Leerzeichen steht.
    * Fügt ein Leerzeichen nach einer schließenden Klammer ein, falls
      sich direkt ein Buchstabe oder eine Zahl anschließt.
    * Fügt ein Leerzeichen vor einem Großbuchstaben ein, wenn dieser
      auf einen Kleinbuchstaben folgt (hilfreich bei zusammengeklebten
      Wörtern wie ``ZunächstSOLLTE`` → ``Zunächst SOLLTE``).
    * Reduziert Mehrfach‑Leerzeichen auf ein einzelnes Leerzeichen.
    """
    if not text:
        return text
    import re

    # Entferne Silbentrennung innerhalb von Wörtern
    text = re.sub(r"(?<=[A-Za-zÄÖÜäöüß])-(?=[a-zäöüß])", "", text)
    # Leerzeichen nach Punkt oder Komma, falls keins vorhanden
    text = re.sub(r"([\.,])(?!\s)", r"\1 ", text)
    # Leerzeichen nach schließender Klammer vor Buchstaben oder Zahlen
    text = re.sub(r"(\))(?!\s)(?=[A-Za-zÄÖÜäöüß0-9])", r"\1 ", text)
    # Leerzeichen vor Großbuchstabe nach Kleinbuchstabe
    text = re.sub(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", " ", text)
    # Reduziere Mehrfach‑Leerzeichen
    text = re.sub(r"\s+", " ", text)

    # Versuche fehlende Leerzeichen vor gängigen deutschen Präpositionen,
    # Artikeln und Pronomen einzufügen, wenn diese direkt an ein
    # vorheriges Wort angehängt wurden. Ein zu großer Präpositionskatalog
    # kann zu unnatürlichen Trennungen führen; daher werden kurze
    # Präpositionen wie "an" oder "aus" bewusst ausgelassen.
    import re as _re_prep
    preps = [
        "von", "mit", "für", "des", "dem", "den", "die", "das", "der", "vom",
        "zu", "zum", "zur", "bei", "im", "in", "auf", "unter", "über",
        "sowie", "durch", "am", "diese", "dieser", "dieses", "diesem", "diesen"
    ]
    # Füge ein Leerzeichen vor der Präposition/Artikel ein, wenn vorher
    # ein Kleinbuchstabe steht und danach ein Buchstabe folgt. So wird
    # z. B. "Clientsmit" zu "Clients mit". Großschreibung im Wort nach
    # der Präposition spielt keine Rolle.
    prep_pattern = r"(?<=[a-zäöüß])((?:" + "|".join(preps) + "))(?=[A-Za-zÄÖÜäöüß])"
    text = _re_prep.sub(prep_pattern, r" \1", text, flags=_re_prep.IGNORECASE)

    # Repariere Worttrennungen, die durch PDF-Extraktion entstanden sind.
    # Wenn ein einzelner oder zwei Kleinbuchstaben gefolgt von einem
    # Leerzeichen und einem Wort aus mindestens drei Kleinbuchstaben
    # auftreten, wird das Leerzeichen entfernt. Dies korrigiert z. B.
    # "e ine" → "eine" oder "i dentifiziert" → "identifiziert". Es werden
    # nur Kleinbuchstaben berücksichtigt, um nicht "Der Arbeits" zu
    # verändern.
    text = re.sub(r"\b([a-zäöüß]{1,2})\s+([a-zäöüß]{3,})", r"\1\2", text)

    # Füge Zeilenumbrüche vor Bullet-Zeichen ein, wenn sie im Text vorkommen. Dies
    # sorgt dafür, dass Aufzählungspunkte (•) im UI als getrennte Zeilen
    # dargestellt werden. Mehrere Bullet-Zeichen hintereinander werden
    # zusammengefasst, wobei vor dem ersten Bullet ein Newline steht.
    text = re.sub(r"\s*•\s*", "\n• ", text)

    # Spezifische Korrekturen für häufig verschmolzene Wörter aufgrund des
    # PDF-Layouts. Diese ersetzen bekannte Problemstellen wie "obdie" -> "ob die"
    # und "obsie" -> "ob sie". Weitere Fehlerbilder können hier ergänzt
    # werden, falls sie im Laufe der Nutzung auffallen.
    corrections = {
        "obdie": "ob die",
        "obsie": "ob sie",
        "verb indlich": "verbindlich",
    }
    for bad, good in corrections.items():
        text = text.replace(bad, good)

    return text.strip()


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


def _parse_modules(text: str) -> List[
    Tuple[str, str, List[Tuple[str, str, str | None, bool, str]]]
]:
    """Extrahiert Module und Anforderungen aus normalisiertem Text.

    Ein Modul beginnt mit einem Muster wie ``SYS.3.2.2 <Titel>``. Alle
    folgenden Zeilen werden untersucht, um Anforderungen zu erkennen. Eine
    Anforderung beginnt mit ``A`` gefolgt von einer Nummer (z. B. ``A1`` oder
    ``A 1``). Der Beschreibungstext einer Anforderung kann über mehrere
    Zeilen gehen, bis die nächste Anforderung oder das nächste Modul beginnt.

    :returns: Liste von Modulen, jeweils mit Code, Titel und Liste der
        Anforderungen. Jede Anforderung wird als Tupel zurückgegeben:
        ``(req_id, title, classification, is_obsolete, description)``. Der
        ``req_id`` enthält den vollständigen BSI‑Code inklusive Titel und
        Klassifizierung. ``title`` ist der reine Titel (ohne Code und
        Klassifizierung). ``classification`` enthält ``B``, ``S`` oder ``H``
        (oder ``None`` bei fehlender Klassifizierung). ``is_obsolete`` ist
        ``True``, wenn der Titel das Wort ``ENTFALLEN`` (Groß/Kleinschreibung
        ignoriert) enthält, andernfalls ``False``. ``description`` ist der
        normative Beschreibungs­text hinter der Klassifizierung, ggf. über
        mehrere Zeilen zusammengeführt.
    """
    modules: List[
        Tuple[str, str, List[Tuple[str, str, str | None, bool, str]]]
    ] = []
    current_code: str | None = None
    current_title: str | None = None
    current_reqs: List[Tuple[str, str, str | None, bool, str]] = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Prüfe auf Modulcode am Zeilenanfang (z. B. SYS.3.2.2 Titel). Wir
        # verwenden hier einen negativen Ausblick, damit Zeilen wie
        # "SYS.3.2.2.A1" nicht als neues Modul erkannt werden. Nach dem
        # Modulcode muss ein Leerzeichen folgen, ansonsten wird die Zeile
        # übersprungen und als möglicher Requirement‑Eintrag behandelt.
        m = re.match(r"([A-Z]{2,4}\.[0-9]+(?:\.[0-9]+)*)\s+(.+)", stripped)
        # Zusätzlich: Erkenne Moduldefinitionen, die mit einem Bullet
        # beginnen (•, -, –) oder per Bindestrich eingeleitet werden,
        # gefolgt von einem Modulcode. Beispiel: "• DER.2.1 Behandlung
        # von Sicherheitsvorfällen". Diese Zeilen werden auch als neue
        # Module behandelt. Das Bullet‑Symbol wird ignoriert.
        if not m:
            # 1) Moduldefinition mit Bullet: Zeilen, die mit einem oder mehreren
            # Bullet‑Zeichen (•, ·, -, –) beginnen, gefolgt von einem Modulcode.
            m_bullet = re.match(r"^[\u2022\u2023\u25cf\u25cb\u25a0\u2219\*\-–·]+\s*([A-Z]{2,4}\.[0-9]+(?:\.[0-9]+)*)\s+(.+)", stripped)
            if m_bullet:
                m = m_bullet
            # 2) Untermodul ohne explizite Bullet: Wenn wir uns bereits in
            # einem Modul befinden und die aktuelle Zeile mit einem Modulcode
            # beginnt, dessen Anzahl an Segmenten (durch Punkte getrennt)
            # größer ist als die des aktuellen Codes, wird diese Zeile als
            # neues Modul interpretiert. Vorangestellte Leer- oder
            # Sonderzeichen (z. B. Aufzählungszeichen) werden ignoriert.
            elif current_code:
                # Entferne führende Leerzeichen und nicht alphanumerische
                # Zeichen, damit z. B. "• DER.2.1 ..." oder "- DER.2.2 ..."
                # korrekt erkannt werden.
                import re as _re_sub
                candidate = _re_sub.sub(r"^[\s\W]+", "", stripped)
                m_sub = _re_sub.match(r"([A-Z]{2,4}\.[0-9]+(?:\.[0-9]+)+)\s+(.+)", candidate)
                if m_sub:
                    candidate_code = m_sub.group(1)
                    # Vergleiche die Anzahl der Segmente: z. B. DER.2 -> 2, DER.2.1 -> 3
                    if len(candidate_code.split(".")) > len(current_code.split(".")):
                        m = m_sub
        if m:
            # Vorheriges Modul abschließen
            if current_code:
                modules.append((current_code, current_title or "", current_reqs))
            current_code = m.group(1)
            # Titel vom Rest der Zeile ermitteln und ggf. bei nachfolgenden
            # Aufzählungen oder Untermodulcodes abschneiden. Manche PDFs
            # enthalten mehrere Bullet‑Symbole oder Codes in einer Zeile, was
            # zu extrem langen Titeln führt. Wir behalten nur den ersten
            # Abschnitt vor einem Bullet‑Symbol oder einem neuen Modulcode.
            raw_title = m.group(2).strip()
            # Suche erstes echtes Bullet‑Symbol (•, ·) im Titel. Bindestriche und
            # Gedankenstriche innerhalb eines Wortes (z. B. „IT-Forensik“)
            # sollen nicht als Trennzeichen behandelt werden, daher werden
            # "-" und "–" hier bewusst ausgelassen.
            import re as _re_cut
            cut_idx = None
            for sym in ["\u2022", "•", "·"]:
                idx = raw_title.find(sym)
                if idx != -1 and (cut_idx is None or idx < cut_idx):
                    cut_idx = idx
            # Suche erstes Auftreten eines weiteren Modulcodes innerhalb des Titels
            # (z. B. "APP.1.2"), um Listen zusammenhängender Module zu trennen.
            mc_match = _re_cut.search(r"([A-Z]{2,4}\.[0-9]+(?:\.[0-9]+)+)", raw_title)
            if mc_match:
                idx = mc_match.start()
                if cut_idx is None or idx < cut_idx:
                    cut_idx = idx
            # Entferne Klassifikationszusätze wie " R3 Informationsverbund/…" oder " R2 IT-System".
            # Diese beginnen typischerweise mit einem Leerzeichen, gefolgt von "R" und einer Ziffer.
            class_match = _re_cut.search(r"\sR\d+\b", raw_title)
            if class_match:
                idx = class_match.start()
                if cut_idx is None or idx < cut_idx:
                    cut_idx = idx
            if cut_idx is not None:
                raw_title = raw_title[:cut_idx].rstrip()
            current_title = raw_title
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

                # Suche nach der ersten Klassifizierung (B|S|H) in Klammern. Wenn
                # vorhanden, trennen wir den Titel bis zur Klammer. Wenn keine
                # Klassifizierung gefunden wird, bleibt die Klassifizierung None.
                class_match = re.search(r"\(([BSH])\)", remainder)
                if class_match:
                    class_idx_start = class_match.start()
                    class_idx_end = class_match.end()
                    title_raw = remainder[:class_idx_start].strip()
                    classification = class_match.group(1)
                    normative = remainder[class_idx_end:].strip()
                    title_with_class = f"{title_raw} ({classification})"
                else:
                    title_raw = remainder
                    classification = None
                    normative = ""
                    title_with_class = title_raw

                # Compose requirement id als vollständiger BSI‑Code inkl. Titel
                req_id = f"{mod_prefix}.A{number} {title_with_class}"
                # Bestimme ob Anforderung entfallen ist (ENTFALLEN im Titel)
                is_obsolete = "ENTFALLEN" in title_raw.upper()
                # Bereinige normative Beschreibung
                cleaned_norm = _cleanup_description(normative)
                # Aktuelle Anforderung hinzufügen: (req_id, title, classification, is_obsolete, description)
                current_reqs.append(
                    (req_id, title_raw, classification, is_obsolete, cleaned_norm)
                )
            else:
                # Zeile gehört zur letzten Anforderung (Fortsetzung des Beschreibungstexts)
                # Füge nur dann an, wenn es einen vorherigen Requirementeintrag gibt und die
                # vorherige Anforderung nicht als entfallen markiert wurde. Bei entfallenen
                # Anforderungen (ENTFALLEN im Titel) soll der Beschreibungstext nicht mit
                # nachfolgenden Zeilen (z. B. Abschnittsüberschriften) erweitert werden.
                if current_reqs and stripped:
                    last_req_id, last_title, last_class, last_obsolete, last_desc = current_reqs[-1]
                    # Wenn die letzte Anforderung entfallen ist, überspringe alle
                    # nachfolgenden Zeilen bis zum nächsten Requirement oder Modul. So
                    # verhindern wir, dass Abschnittsüberschriften wie "3.3. Anforderungen…"
                    # oder "IT-Grundschutz" fälschlich in die Beschreibung aufgenommen werden.
                    if last_obsolete:
                        continue
                    # Prüfe, ob die neue Zeile eine Klassifikation (B|S|H) am Anfang enthält,
                    # wenn bislang keine Klassifikation gesetzt ist. Wenn ja, entferne sie aus der
                    # Zeile und setze die Klassifikation. So werden Klassifizierungen, die
                    # erst in einer späteren Zeile erscheinen (z. B. am Anfang des normativen
                    # Textes), korrekt erkannt.
                    tmp_class = last_class
                    tmp_stripped = stripped
                    if last_class is None:
                        m_class = re.match(r"\(([BSH])\)\s*", stripped)
                        if m_class:
                            tmp_class = m_class.group(1)
                            # alles nach der Klassifikation als Text nehmen
                            tmp_stripped = stripped[m_class.end():].lstrip()
                    # Entscheide, ob die Zeile einen neuen Aufzählungspunkt darstellt. Wenn
                    # die Zeile mit typischen Bullet‑Zeichen (•, -, –, •) oder einer
                    # nummerierten Liste (z. B. 1. oder 1)) beginnt, fügen wir einen
                    # Zeilenumbruch ein. Ansonsten verknüpfen wir die Zeile mit einem
                    # Leerzeichen. Diese heuristische Unterscheidung verbessert die
                    # Darstellung von Unterpunkten in den extrahierten Beschreibungen.
                    bullet_pattern = re.compile(r"^[\u2022\-–•\d]+[\.\)]?\s*")
                    if bullet_pattern.match(tmp_stripped):
                        delimiter = "\n"
                    else:
                        delimiter = " "
                    combined_raw = (last_desc + delimiter + tmp_stripped).strip()
                    # Bereinige normative Beschreibung nach dem Hinzufügen der neuen Zeile
                    cleaned = _cleanup_description(combined_raw)
                    # Aktualisiere die zuletzt gespeicherte Anforderung mit eventuell
                    # aktualisierter Klassifikation und Beschreibung
                    current_reqs[-1] = (
                        last_req_id,
                        last_title,
                        tmp_class,
                        last_obsolete,
                        cleaned,
                    )
    # Letztes Modul anhängen
    if current_code:
        modules.append((current_code, current_title or "", current_reqs))

    # Dedupliziere Module nach ihrem Code. Wenn derselbe Code mehrfach auftaucht,
    # wird nur der erste Eintrag behalten und seine Anforderungen ggf. um die
    # Anforderungen der späteren Einträge ergänzt. So werden Listen wie
    # "IND.2.3 Sensoren und Aktoren" und "IND.2.3 Sensoren und Aktoren R2 IT-System"
    # zu einem Modul zusammengeführt.
    dedup: dict[str, Tuple[str, List[Tuple[str, str, str | None, bool, str]]]] = {}
    for code, title, reqs in modules:
        if code not in dedup:
            dedup[code] = (title, list(reqs))
        else:
            # Füge neue Requirements an bestehende Liste an
            dedup[code][1].extend(reqs)

    # Konvertiere zurück in eine geordnete Liste (Reihenfolge der ersten Vorkommen)
    result: List[
        Tuple[str, str, List[Tuple[str, str, str | None, bool, str]]]
    ] = []
    for code, (title, reqs) in dedup.items():
        result.append((code, title, reqs))
    return result


@router.post(
    "/bsi/catalogs/upload",
    response_model=List[BsiCatalogUploadResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_bsi_catalogs(
    background_tasks: BackgroundTasks,
    file: List[UploadFile] = File(...),
) -> List[BsiCatalogUploadResponse]:
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
            # Die Variable modules_data hält eine Liste von Modulen mit ihren Anforderungen.
            # Jeder Eintrag besteht aus (code, title, requirements) und entspricht dem
            # Rückgabewert von _parse_modules: requirements sind Tupel aus
            # (req_id, title, classification, is_obsolete, description).
            modules_data: List[
                Tuple[str, str, List[Tuple[str, str, str | None, bool, str]]]
            ] = []
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
                # Erstelle eine Upload‑Response für den Katalog
                upload_resp = BsiCatalogUploadResponse(
                    id=catalog.id,
                    version=catalog.version,
                    status=status_str,
                    message=message,
                )
                # Starte automatische Normalisierung über einen Hintergrundjob,
                # falls ein BackgroundTasks‑Objekt vorhanden ist. Dies sorgt dafür,
                # dass die Kataloge sofort nach dem Upload normalisiert werden.
                if background_tasks is not None:
                    # Importiere Job‑Store und Normalizer hier, um zyklische
                    # Importe zu vermeiden
                    from ..api.jobs import jobs_store
                    from ..schemas import JobStatus
                    from ..normalizer import run_normalize_job
                    from datetime import datetime
                    import uuid as _uuid
                    job_id = str(_uuid.uuid4())
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
                    # Startet den Normalisierungsjob für den hochgeladenen Katalog
                    background_tasks.add_task(run_normalize_job, job_id, catalog.id, None)
                    # Gib die Job‑ID in der Upload‑Antwort zurück
                    upload_resp.normalize_job_id = job_id
                responses.append(upload_resp)
            except Exception as exc:
                db.rollback()
                responses.append(
                    BsiCatalogUploadResponse(
                        id="",
                        version=0,
                        status="error",
                        message=str(exc),
                    )
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