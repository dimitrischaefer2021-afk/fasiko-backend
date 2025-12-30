"""
API‑Router für Artefakte und Versionen.

Dieser Router ermöglicht CRUD‑Operationen auf Artefakt‑Meta‑Daten und
Versionen sowie die Generierung neuer Dokumente aus dem Projektkontext.
Beim Generieren werden die vorhandenen Artefakte, Quellen und der
Projektname an das LLM gesendet. Fehlende Informationen werden als
offene Punkte gespeichert.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from .. import crud
from ..schemas import (
    ArtifactCreate,
    ArtifactUpdate,
    ArtifactOut,
    ArtifactDetailOut,
    ArtifactListOut,
    ArtifactVersionOut,
    ArtifactVersionListOut,
    ArtifactVersionCreate,
    ArtifactSetCurrent,
    ArtifactGenerateRequest,
    ArtifactGenerateResponse,
    GeneratedArtifactOut,
    OpenPointCreate,
    OpenPointOut,
)
from .. import generator

router = APIRouter(prefix="/projects/{project_id}/artifacts", tags=["artifacts"])


def _ensure_project(db: Session, project_id: str) -> None:
    if crud.get_project(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


def _to_artifact_out(db: Session, art) -> ArtifactOut:
    return ArtifactOut(
        id=art.id,
        project_id=art.project_id,
        type=art.type,
        title=art.title,
        status=art.status,
        current_version=art.current_version,
        versions_count=crud.count_versions(db, art.id),
        created_at=art.created_at,
        updated_at=art.updated_at,
    )


def _to_artifact_detail(db: Session, art) -> ArtifactDetailOut:
    cur = crud.get_current_version(db, art.id, art.current_version)
    return ArtifactDetailOut(
        id=art.id,
        project_id=art.project_id,
        type=art.type,
        title=art.title,
        status=art.status,
        current_version=art.current_version,
        versions_count=crud.count_versions(db, art.id),
        current_content_md=(cur.content_md if cur else ""),
        created_at=art.created_at,
        updated_at=art.updated_at,
    )


def _to_version_out(v) -> ArtifactVersionOut:
    return ArtifactVersionOut(
        id=v.id,
        artifact_id=v.artifact_id,
        version=v.version,
        content_md=v.content_md,
        created_at=v.created_at,
    )


@router.post("", response_model=ArtifactOut, status_code=status.HTTP_201_CREATED)
def create_artifact(project_id: str, payload: ArtifactCreate, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    art = crud.create_artifact(db, project_id, payload)
    return _to_artifact_out(db, art)


@router.get("", response_model=ArtifactListOut)
def list_artifacts(project_id: str, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    items = [_to_artifact_out(db, a) for a in crud.list_artifacts(db, project_id)]
    return {"items": items}


@router.get("/{artifact_id}", response_model=ArtifactDetailOut)
def get_artifact(project_id: str, artifact_id: str, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    art = crud.get_artifact(db, project_id, artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _to_artifact_detail(db, art)


@router.put("/{artifact_id}", response_model=ArtifactOut)
def update_artifact(project_id: str, artifact_id: str, payload: ArtifactUpdate, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    art = crud.update_artifact_meta(db, project_id, artifact_id, payload)
    if art is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _to_artifact_out(db, art)


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artifact(project_id: str, artifact_id: str, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    ok = crud.delete_artifact(db, project_id, artifact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return None


# ---- Versioning ----


@router.get("/{artifact_id}/versions", response_model=ArtifactVersionListOut)
def list_versions(project_id: str, artifact_id: str, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    art = crud.get_artifact(db, project_id, artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    items = [_to_version_out(v) for v in crud.list_versions(db, artifact_id)]
    return {"items": items}


@router.get("/{artifact_id}/versions/{version}", response_model=ArtifactVersionOut)
def get_version(project_id: str, artifact_id: str, version: int, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    art = crud.get_artifact(db, project_id, artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    v = crud.get_version(db, artifact_id, version)
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return _to_version_out(v)


@router.post("/{artifact_id}/versions", response_model=ArtifactVersionOut, status_code=status.HTTP_201_CREATED)
def create_version(project_id: str, artifact_id: str, payload: ArtifactVersionCreate, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    art = crud.get_artifact(db, project_id, artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    v = crud.create_version(db, artifact_id, payload)
    return _to_version_out(v)


@router.post("/{artifact_id}/set-current", status_code=status.HTTP_200_OK)
def set_current(project_id: str, artifact_id: str, payload: ArtifactSetCurrent, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    art = crud.get_artifact(db, project_id, artifact_id)
    if art is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    ok = crud.set_current_version(db, artifact_id, payload.version)
    if not ok:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"status": "ok", "current_version": payload.version}


# ---- Generierung neuer Artefakte ----


@router.post("/generate", response_model=ArtifactGenerateResponse)
async def generate_artifacts(
    project_id: str,
    payload: ArtifactGenerateRequest,
    db: Session = Depends(get_db),
) -> ArtifactGenerateResponse:
    """Generiert ein oder mehrere Artefakte mit Hilfe des LLM.

    Für jeden angefragten Artefakt‑Typ wird ein neues Dokument erstellt, falls
    es noch nicht existiert. Existierende Artefakte erhalten eine neue
    Version. Die erzeugten Inhalte werden als Markdown gespeichert. Offene
    Fragen werden als Open Points in der Datenbank angelegt.
    """
    _ensure_project(db, project_id)
    # Hole den Projektnamen für den Prompt
    proj = crud.get_project(db, project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project_name = proj.name

    items: List[GeneratedArtifactOut] = []

    for art_type in payload.types:
        internal_type = art_type.strip().lower()
        # Definiere eine Standardübersetzung des Typs in einen Titel
        title_map = {
            "strukturanalyse": "Strukturanalyse",
            "schutzbedarf": "Schutzbedarfsfeststellung",
            "modellierung": "Modellierung",
            "grundschutz_check": "IT‑Grundschutz‑Check",
            "risikoanalyse": "Risikoanalyse",
            "maßnahmenplan": "Maßnahmen‑/Umsetzungsplan",
            "sicherheitskonzept": "Sicherheitskonzept",
        }
        title = title_map.get(internal_type, internal_type)

        # Prüfe, ob Artefakt bereits existiert
        existing: List = [a for a in crud.list_artifacts(db, project_id) if a.type == internal_type]
        if existing:
            art = existing[0]
        else:
            # Neues Artefakt anlegen (initiale Version wird mit leerem Inhalt erstellt)
            art_payload = ArtifactCreate(type=internal_type, title=title, initial_content_md="", status="draft")
            art = crud.create_artifact(db, project_id, art_payload)

        # LLM aufrufen, um Inhalt und offene Punkte zu generieren
        content_md, open_points_raw = await generator.generate_artifact_content(internal_type, project_name)

        # Neue Version erzeugen (macht sie automatisch zur aktuellen Version)
        version = crud.create_version(db, art.id, ArtifactVersionCreate(content_md=content_md, make_current=True))

        # Offene Punkte persistieren
        open_points_out: List[OpenPointOut] = []
        for op in open_points_raw:
            question = op.get("question")
            if not question:
                continue
            category = op.get("category")
            payload_op = OpenPointCreate(
                question=question,
                input_type="text",
                priority="wichtig",
                status="offen",
                artifact_id=art.id,
                category=category,
            )
            op_rec = crud.create_open_point(db, project_id, payload_op)
            # Um Anhänge zählen zu können, nutzen wir count_openpoint_attachments
            attachments_count = crud.count_openpoint_attachments(db, op_rec.id)
            open_points_out.append(
                OpenPointOut(
                    id=op_rec.id,
                    project_id=op_rec.project_id,
                    artifact_id=op_rec.artifact_id,
                    bsi_ref=op_rec.bsi_ref,
                    section_ref=op_rec.section_ref,
                    category=op_rec.category,
                    question=op_rec.question,
                    input_type=op_rec.input_type,
                    status=op_rec.status,
                    priority=op_rec.priority,
                    answer_text=op_rec.answer_text,
                    answer_choice=op_rec.answer_choice,
                    attachments_count=attachments_count,
                    created_at=op_rec.created_at,
                    updated_at=op_rec.updated_at,
                )
            )

        items.append(
            GeneratedArtifactOut(
                artifact=_to_artifact_out(db, art),
                version=_to_version_out(version),
                open_points=open_points_out,
            )
        )

    return ArtifactGenerateResponse(items=items)