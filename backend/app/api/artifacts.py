from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from .. import crud
from ..schemas import (
    ArtifactCreate, ArtifactUpdate,
    ArtifactOut, ArtifactDetailOut, ArtifactListOut,
    ArtifactVersionOut, ArtifactVersionListOut,
    ArtifactVersionCreate, ArtifactSetCurrent,
)

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