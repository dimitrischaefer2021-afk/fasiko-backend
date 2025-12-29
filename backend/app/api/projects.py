import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from .. import crud
from ..schemas import (
    ProjectCreate, ProjectUpdate, ProjectOut,
    SourceOut, SourceListOut, SourceReplaceOut,
)
from ..storage import save_source_upload_to_disk, delete_source_files, parse_tags

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------- Projects CRUD ----------------

@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    return crud.create_project(db, payload)

@router.get("", response_model=list[ProjectOut])
def list_projects(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    return crud.list_projects(db, limit=limit, offset=offset)

@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = crud.get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = crud.update_project(db, project_id, payload)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    ok = crud.delete_project(db, project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Project not found")
    return None


# ---------------- Sources (Uploads) ----------------

def _ensure_project_exists(db: Session, project_id: str) -> None:
    if crud.get_project(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

def _to_source_out(src) -> SourceOut:
    return SourceOut(
        id=src.id,
        project_id=src.project_id,
        group_id=src.group_id,
        filename=src.filename,
        content_type=src.content_type,
        size_bytes=src.size_bytes,
        tags=crud.source_tags(src),
        status=src.status,
        created_at=src.created_at,
        updated_at=src.updated_at,
    )

@router.post("/{project_id}/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED, tags=["sources"])
def upload_source(
    project_id: str,
    file: UploadFile = File(...),
    tags: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    _ensure_project_exists(db, project_id)

    source_id = str(uuid.uuid4())
    tag_list = parse_tags(tags)

    try:
        storage_path, size_bytes, filename, content_type = save_source_upload_to_disk(project_id, source_id, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    src = crud.create_source_record(
        db=db,
        project_id=project_id,
        source_id=source_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        tags=tag_list,
    )
    return _to_source_out(src)

@router.get("/{project_id}/sources", response_model=SourceListOut, tags=["sources"])
def list_sources(project_id: str, db: Session = Depends(get_db)):
    _ensure_project_exists(db, project_id)
    items = [_to_source_out(s) for s in crud.list_sources(db, project_id)]
    return {"items": items}

@router.get("/{project_id}/sources/{source_id}/download", tags=["sources"])
def download_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    _ensure_project_exists(db, project_id)
    src = crud.get_source(db, project_id, source_id)
    if src is None or src.status == "deleted":
        raise HTTPException(status_code=404, detail="Source not found")
    return FileResponse(path=src.storage_path, filename=src.filename, media_type=src.content_type)

@router.delete("/{project_id}/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["sources"])
def delete_source(project_id: str, source_id: str, db: Session = Depends(get_db)):
    _ensure_project_exists(db, project_id)
    src = crud.get_source(db, project_id, source_id)
    if src is None or src.status == "deleted":
        raise HTTPException(status_code=404, detail="Source not found")

    delete_source_files(project_id, source_id)

    ok = crud.delete_source(db, project_id, source_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Source not found")
    return None

@router.post("/{project_id}/sources/{source_id}/replace", response_model=SourceReplaceOut, tags=["sources"])
def replace_source(
    project_id: str,
    source_id: str,
    file: UploadFile = File(...),
    tags: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    _ensure_project_exists(db, project_id)
    old = crud.get_source(db, project_id, source_id)
    if old is None or old.status == "deleted":
        raise HTTPException(status_code=404, detail="Source not found")

    new_source_id = str(uuid.uuid4())
    tag_list = parse_tags(tags)

    try:
        storage_path, size_bytes, filename, content_type = save_source_upload_to_disk(project_id, new_source_id, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    res = crud.replace_source(
        db=db,
        project_id=project_id,
        old_source_id=source_id,
        new_source_id=new_source_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        tags=tag_list,
    )
    if res is None:
        raise HTTPException(status_code=404, detail="Source not found")

    old_updated, new = res
    return {"old_id": old_updated.id, "new": _to_source_out(new)}