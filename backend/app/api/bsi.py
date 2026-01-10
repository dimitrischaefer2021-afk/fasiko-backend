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

from typing import Dict, List

from fastapi import APIRouter, HTTPException, status

from ..schemas import (
    BsiGenerateRequest,
    BsiGenerateResponse,
    BsiEvaluationOut,
    BsiEvaluationUpdate,
)


router = APIRouter(tags=["bsi"])

# In‑Memory‑Store für BSI‑Bewertungen.
# Struktur: {project_id: {module_code: BsiEvaluationOut}}
bsi_store: Dict[str, Dict[str, BsiEvaluationOut]] = {}


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