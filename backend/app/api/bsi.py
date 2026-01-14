"""
API‑Router für BSI‑Bausteine (Block 11).

Dieser Router bietet Endpunkte für die Generierung und Verwaltung
von BSI‑Baustein‑Bewertungen. Ein BSI‑Baustein repräsentiert einen
konkreten Grundschutz‑Baustein (z. B. SYS.2.1 Allgemeiner Server).
Beim Generieren werden die angegebenen Bausteine initial mit
Status "offen" angelegt. Fehlende Informationen werden als
offene Fragen markiert. Die Bewertungen können anschließend
abgerufen oder aktualisiert werden. Alle Daten werden in einem
speicherresidenten Store gehalten und sind nicht persistent.

Endpunkte:

    * **POST /api/v1/projects/{project_id}/bsi/generate** –
      Erzeugt initiale Bewertungen für die angegebenen BSI‑Bausteine.
    * **GET /api/v1/projects/{project_id}/bsi** –
      Listet alle bestehenden Baustein‑Bewertungen des Projekts.
    * **GET /api/v1/projects/{project_id}/bsi/{module_code}** –
      Liefert die Bewertung eines einzelnen Bausteins.
    * **PUT /api/v1/projects/{project_id}/bsi/{module_code}** –
      Aktualisiert den Status oder Kommentar eines Bausteins.

Hinweis: In dieser Minimalversion werden die Bewertungen nur im
Speicher gehalten. Für eine produktive Nutzung sollten die Daten
in einer Datenbank persistiert werden.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, status

from ..schemas import (
    BsiGenerateRequest,
    BsiGenerateResponse,
    BsiEvaluationOut,
    BsiEvaluationUpdate,
    BsiMeasureEvaluation,
    BsiEvaluationDetailOut,
    BsiAnalyzeResponse,
)

from ..settings import UPLOAD_DIR
import os
import re
from docx import Document  # type: ignore


# Definition der bekannten BSI‑Bausteine und ihrer Maßnahmen.
# Für eine produktive Lösung sollten diese Daten aus einer offiziellen
# Quelle (z. B. JSON oder Datenbank) geladen werden. Hier werden sie
# exemplarisch definiert.
MODULE_MEASURES: Dict[str, List[Dict[str, str]]] = {
    # Allgemeiner Server (Beispiel)
    "SYS.2.1": [
        {
            "id": "SYS.2.1.A1",
            "requirement": "Ein Patchmanagement muss eingerichtet sein.",
        },
        {
            "id": "SYS.2.1.A2",
            "requirement": "Ein Administrationskonzept muss vorliegen.",
        },
        {
            "id": "SYS.2.1.A3",
            "requirement": "Regelmäßige Systemhärtung und Sicherheitsupdates müssen nachweisbar sein.",
        },
    ],
    # Beispielhafter Anwendungsbaustein
    "APP.1.2": [
        {
            "id": "APP.1.2.A1",
            "requirement": "Ein Sicherheitskonzept für die Anwendung muss existieren.",
        },
        {
            "id": "APP.1.2.A2",
            "requirement": "Zugriffsrechte müssen rollenbasiert umgesetzt sein.",
        },
    ],
}


def _read_text_from_file(file_path: str) -> str:
    """Liest den Textinhalt einer Datei.

    Unterstützt .txt, .md und .docx. Bei anderen Formaten wird ein leerer
    String zurückgegeben. PDF‑Parsing ist nicht implementiert.

    Args:
        file_path: Absoluter Pfad zur Datei.

    Returns:
        Den extrahierten Text (eventuell leer).
    """
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in {".txt", ".md"}:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if ext == ".docx":
            doc = Document(file_path)
            return "\n".join([p.text for p in doc.paragraphs])
    except Exception:
        pass
    return ""


def _collect_project_text(project_id: str) -> str:
    """Sammelt Text aus allen hochgeladenen Dateien eines Projekts.

    Durchsucht das Verzeichnis ``UPLOAD_DIR/{project_id}`` und liest
    Inhalte aus unterstützten Formaten. Der zusammengesetzte Text wird
    in Kleinbuchstaben zurückgegeben, um die Suche zu erleichtern.

    Args:
        project_id: Kennung des Projekts.

    Returns:
        Ein großer Textblock mit allen extrahierten Inhalten.
    """
    base_path = os.path.join(UPLOAD_DIR, project_id)
    collected = []
    if os.path.isdir(base_path):
        for name in os.listdir(base_path):
            path = os.path.join(base_path, name)
            if not os.path.isfile(path):
                continue
            text = _read_text_from_file(path)
            if text:
                collected.append(text)
    # Auch die Bausteine ggf. gruppiert nach .txt oder .md etc.
    return "\n".join(collected).lower()


def _evaluate_measure(requirement: str, project_text: str) -> tuple[str, List[str], Optional[str]]:
    """Bewertet eine einzelne Maßnahme.

    Eine sehr einfache Heuristik: Wenn alle Wörter des Requirements im
    Projekttext vorkommen, wird die Maßnahme als "erfüllt" bewertet. Wenn
    mindestens eines der Wörter vorkommt, gilt sie als "teilweise". Wenn
    nichts gefunden wird, ist sie "offen" und eine Frage wird gestellt.

    Args:
        requirement: Der Solltext der Maßnahme.
        project_text: Aggregierter Text aus den Projektquellen (in Kleinbuchstaben).

    Returns:
        Ein Tupel (status, evidences, open_point).
    """
    # Bereinige Anforderung und zerlege in Wörter
    cleaned_req = re.sub(r"[^a-zA-Z0-9äöüß ]+", " ", requirement.lower())
    words = [w for w in cleaned_req.split() if len(w) > 3]
    if not words:
        return "offen", [], f"Information zur Maßnahme fehlt: {requirement}"
    matches = [w for w in words if w in project_text]
    if len(matches) == len(words):
        # Alle Wörter gefunden → erfüllt. Als Evidence fügen wir den ersten
        # Satz mit einem der gefundenen Wörter ein.
        evidence = []
        for w in matches[:1]:
            idx = project_text.find(w)
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(project_text), idx + 80)
                evidence.append(project_text[start:end].strip())
        return "erfüllt", evidence, None
    if matches:
        # Teilweise erfüllt
        evidence = []
        for w in matches[:1]:
            idx = project_text.find(w)
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(project_text), idx + 80)
                evidence.append(project_text[start:end].strip())
        return "teilweise", evidence, None
    # Nichts gefunden → offen
    return "offen", [], f"Wie wird folgende Anforderung erfüllt? {requirement}"


router = APIRouter(tags=["bsi"])

# In‑Memory‑Store für BSI‑Bewertungen.
# Struktur: {project_id: {module_code: BsiEvaluationOut}}
bsi_store: Dict[str, Dict[str, BsiEvaluationOut]] = {}


@router.post(
    "/projects/{project_id}/bsi/analyze",
    response_model=BsiAnalyzeResponse,
    status_code=status.HTTP_200_OK,
)
def analyze_bsi(project_id: str, request: BsiGenerateRequest) -> BsiAnalyzeResponse:
    """Analysiert mehrere BSI‑Bausteine anhand der hochgeladenen Projektquellen.

    Für jeden Baustein werden die vordefinierten Maßnahmen betrachtet. Das
    System durchsucht die hochgeladenen Dateien des Projekts nach
    Informationen zu den Maßnahmen. Je nach Fundlage wird der Status
    "erfüllt", "teilweise" oder "offen" vergeben. Gefundene
    Textstellen werden als Belege (evidence) gespeichert. Für offene
    Maßnahmen wird eine konkrete Frage formuliert, die als offene
    Frage im Ergebnis erscheint. Zusätzlich wird der aggregierte
    Bausteinstatus abgeleitet: "erfüllt", wenn alle Maßnahmen erfüllt
    sind, "teilweise", wenn mindestens eine Maßnahme teilweise ist, und
    "offen", wenn mindestens eine Maßnahme offen ist.

    Args:
        project_id: Kennung des Projekts, zu dem die Dokumente gehören.
        request: Enthält die Liste der Baustein‑Codes zur Analyse.

    Returns:
        Eine Antwort mit detaillierten Bewertungen pro Baustein.
    """
    project_text = _collect_project_text(project_id)
    evaluations: List[BsiEvaluationDetailOut] = []
    for module_code in request.modules:
        # Normalisieren: führende/trailing Leerzeichen entfernen
        code = module_code.strip()
        measures_def = MODULE_MEASURES.get(code)
        measure_evals: List[BsiMeasureEvaluation] = []
        all_statuses: List[str] = []
        open_points: List[str] = []
        if not measures_def:
            # Wenn der Baustein nicht definiert ist, markieren wir ihn als offen
            # und hinterlegen einen Hinweis als offene Frage.
            evaluations.append(
                BsiEvaluationDetailOut(
                    module_code=code,
                    status="offen",
                    measures=[],
                    comment=None,
                    open_points=[f"Baustein {code} ist nicht im Katalog definiert. Bitte ergänzen Sie die Maßnahmen."],
                )
            )
            continue
        # Maßnahmen auswerten
        for meas in measures_def:
            mid = meas.get("id", "")
            requirement = meas.get("requirement", "")
            status, evidence, open_point = _evaluate_measure(requirement, project_text)
            all_statuses.append(status)
            if open_point:
                open_points.append(open_point)
            measure_evals.append(
                BsiMeasureEvaluation(
                    measure_id=mid,
                    status=status,
                    evidence=evidence,
                    open_point=open_point,
                )
            )
        # Aggregierter Status bestimmen
        agg_status = "erfüllt"
        if any(s == "offen" for s in all_statuses):
            agg_status = "offen"
        elif any(s == "teilweise" for s in all_statuses):
            agg_status = "teilweise"
        evaluations.append(
            BsiEvaluationDetailOut(
                module_code=code,
                status=agg_status,
                measures=measure_evals,
                comment=None,
                open_points=open_points,
            )
        )
    return BsiAnalyzeResponse(items=evaluations)


@router.post(
    "/projects/{project_id}/bsi/generate",
    response_model=BsiGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_bsi(project_id: str, request: BsiGenerateRequest) -> BsiGenerateResponse:
    """Erzeugt für jeden angegebenen BSI‑Baustein eine initiale Bewertung.

    Alle generierten Bausteine werden mit dem Status ``offen``
    initialisiert. Für jeden Baustein wird zudem eine offene
    Frage hinterlegt, die den Umsetzungsstand abfragt.

    Args:
        project_id: ID des Projekts, zu dem die Bewertungen gehören.
        request: Enthält eine Liste der zu generierenden Baustein‑Codes.

    Returns:
        Eine Antwort mit den erzeugten Baustein‑Bewertungen.
    """
    project_store = bsi_store.setdefault(project_id, {})
    evaluations: List[BsiEvaluationOut] = []
    for module_code in request.modules:
        # Normalisieren: Großschreibung beibehalten, Trim
        code = module_code.strip()
        # Offene Frage für den Baustein
        question = f"Wie ist der Umsetzungsstand für das Baustein {code}?"
        evaluation = BsiEvaluationOut(
            module_code=code,
            status="offen",
            comment=None,
            open_points=[question],
        )
        project_store[code] = evaluation
        evaluations.append(evaluation)
    return BsiGenerateResponse(items=evaluations)


@router.get(
    "/projects/{project_id}/bsi",
    response_model=List[BsiEvaluationOut],
)
def list_bsi(project_id: str) -> List[BsiEvaluationOut]:
    """Listet alle Baustein‑Bewertungen eines Projekts."""
    project_store = bsi_store.get(project_id, {})
    return list(project_store.values())


@router.get(
    "/projects/{project_id}/bsi/{module_code}",
    response_model=BsiEvaluationOut,
)
def get_bsi(project_id: str, module_code: str) -> BsiEvaluationOut:
    """Liefert die Bewertung eines einzelnen Bausteins."""
    project_store = bsi_store.get(project_id)
    if not project_store or module_code not in project_store:
        raise HTTPException(status_code=404, detail="Baustein nicht gefunden")
    return project_store[module_code]


@router.put(
    "/projects/{project_id}/bsi/{module_code}",
    response_model=BsiEvaluationOut,
)
def update_bsi(
    project_id: str,
    module_code: str,
    update: BsiEvaluationUpdate,
) -> BsiEvaluationOut:
    """Aktualisiert den Status oder Kommentar eines Bausteins.

    Der Status kann auf "offen", "teilweise", "erfüllt" oder einen anderen
    sinnvollen Wert gesetzt werden. Der Kommentar kann genutzt werden,
    um Hinweise oder Nachweise zu hinterlegen.

    Args:
        project_id: Projektkennung.
        module_code: Code des Bausteins.
        update: Objekt mit den Feldern ``status`` und/oder ``comment``.

    Returns:
        Die aktualisierte Baustein‑Bewertung.
    """
    project_store = bsi_store.get(project_id)
    if not project_store or module_code not in project_store:
        raise HTTPException(status_code=404, detail="Baustein nicht gefunden")
    evaluation = project_store[module_code]
    if update.status is not None:
        evaluation.status = update.status
    if update.comment is not None:
        evaluation.comment = update.comment
    # open_points werden hier nicht geändert; sie bleiben erhalten
    return evaluation