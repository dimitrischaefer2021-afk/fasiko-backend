import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from .. import crud
from ..schemas import (
    OpenPointCreate, OpenPointUpdate, OpenPointAnswer,
    OpenPointOut, OpenPointDetailOut, OpenPointListOut,
    OpenPointAttachmentOut,
    OPENPOINT_STATUS, OPENPOINT_PRIORITY, OPENPOINT_INPUT,
)
from ..storage import save_openpoint_attachment_to_disk, delete_openpoint_attachment_files

router = APIRouter(prefix="/projects/{project_id}/open-points", tags=["open-points"])


def _ensure_project(db: Session, project_id: str) -> None:
    if crud.get_project(db, project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")


def _validate_openpoint_fields(payload_status: str | None, payload_priority: str | None, payload_input: str | None) -> None:
    if payload_status is not None and payload_status not in OPENPOINT_STATUS:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {sorted(OPENPOINT_STATUS)}")
    if payload_priority is not None and payload_priority not in OPENPOINT_PRIORITY:
        raise HTTPException(status_code=400, detail=f"Invalid priority. Allowed: {sorted(OPENPOINT_PRIORITY)}")
    if payload_input is not None and payload_input not in OPENPOINT_INPUT:
        raise HTTPException(status_code=400, detail=f"Invalid input_type. Allowed: {sorted(OPENPOINT_INPUT)}")


def _is_nonempty_str(x: str | None) -> bool:
    return x is not None and str(x).strip() != ""


def _to_attachment_out(att) -> OpenPointAttachmentOut:
    return OpenPointAttachmentOut(
        id=att.id,
        open_point_id=att.open_point_id,
        filename=att.filename,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        created_at=att.created_at,
    )


def _to_openpoint_out(db: Session, op) -> OpenPointOut:
    return OpenPointOut(
        id=op.id,
        project_id=op.project_id,
        artifact_id=op.artifact_id,
        bsi_ref=op.bsi_ref,
        section_ref=op.section_ref,
        category=op.category,
        question=op.question,
        input_type=op.input_type,
        status=op.status,
        priority=op.priority,
        answer_text=op.answer_text,
        answer_choice=op.answer_choice,
        attachments_count=crud.count_openpoint_attachments(db, op.id),
        created_at=op.created_at,
        updated_at=op.updated_at,
    )


def _to_openpoint_detail(db: Session, op) -> OpenPointDetailOut:
    atts = [_to_attachment_out(a) for a in crud.list_openpoint_attachments(db, op.id)]
    base = _to_openpoint_out(db, op)
    return OpenPointDetailOut(**base.model_dump(), attachments=atts)


@router.post("", response_model=OpenPointOut, status_code=status.HTTP_201_CREATED)
def create_open_point(project_id: str, payload: OpenPointCreate, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    _validate_openpoint_fields(payload.status, payload.priority, payload.input_type)

    # optional artifact_id must belong to project
    if payload.artifact_id:
        art = crud.get_artifact(db, project_id, payload.artifact_id)
        if art is None:
            raise HTTPException(status_code=400, detail="artifact_id not found in this project")

    op = crud.create_open_point(db, project_id, payload)
    return _to_openpoint_out(db, op)


@router.get("", response_model=OpenPointListOut)
def list_open_points(
    project_id: str,
    status: str | None = None,
    priority: str | None = None,
    artifact_id: str | None = None,
    db: Session = Depends(get_db),
):
    _ensure_project(db, project_id)
    _validate_openpoint_fields(status, priority, None)

    if artifact_id:
        art = crud.get_artifact(db, project_id, artifact_id)
        if art is None:
            raise HTTPException(status_code=400, detail="artifact_id not found in this project")

    items = [_to_openpoint_out(db, op) for op in crud.list_open_points(db, project_id, status, priority, artifact_id)]
    return {"items": items}


@router.get("/{open_point_id}", response_model=OpenPointDetailOut)
def get_open_point(project_id: str, open_point_id: str, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    op = crud.get_open_point(db, project_id, open_point_id)
    if op is None:
        raise HTTPException(status_code=404, detail="Open point not found")
    return _to_openpoint_detail(db, op)


@router.put("/{open_point_id}", response_model=OpenPointOut)
def update_open_point(project_id: str, open_point_id: str, payload: OpenPointUpdate, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    _validate_openpoint_fields(payload.status, payload.priority, payload.input_type)

    if payload.artifact_id is not None:
        # allow explicit null / empty to detach
        if payload.artifact_id:
            art = crud.get_artifact(db, project_id, payload.artifact_id)
            if art is None:
                raise HTTPException(status_code=400, detail="artifact_id not found in this project")

    op = crud.update_open_point(db, project_id, open_point_id, payload)
    if op is None:
        raise HTTPException(status_code=404, detail="Open point not found")
    return _to_openpoint_out(db, op)


@router.delete("/{open_point_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_open_point(project_id: str, open_point_id: str, db: Session = Depends(get_db)):
    _ensure_project(db, project_id)
    ok = crud.delete_open_point(db, project_id, open_point_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Open point not found")
    return None


@router.post("/{open_point_id}/answer", response_model=OpenPointOut)
def answer_open_point(project_id: str, open_point_id: str, payload: OpenPointAnswer, db: Session = Depends(get_db)):
    """
    Strict answer rules to keep data clean (Swagger example values protection):

    - if input_type=text  -> require non-empty answer_text, forbid answer_choice
    - if input_type=choice-> require non-empty answer_choice, forbid answer_text
    - if input_type=file  -> answers via /attachments only
    """
    _ensure_project(db, project_id)
    op = crud.get_open_point(db, project_id, open_point_id)
    if op is None:
        raise HTTPException(status_code=404, detail="Open point not found")

    if op.input_type == "text":
        if not _is_nonempty_str(payload.answer_text):
            raise HTTPException(status_code=400, detail="answer_text is required for input_type=text and must be non-empty")
        if _is_nonempty_str(payload.answer_choice):
            raise HTTPException(status_code=400, detail="answer_choice must not be provided for input_type=text")

    elif op.input_type == "choice":
        if not _is_nonempty_str(payload.answer_choice):
            raise HTTPException(status_code=400, detail="answer_choice is required for input_type=choice and must be non-empty")
        if _is_nonempty_str(payload.answer_text):
            raise HTTPException(status_code=400, detail="answer_text must not be provided for input_type=choice")

    elif op.input_type == "file":
        raise HTTPException(status_code=400, detail="Use /attachments for input_type=file")

    else:
        raise HTTPException(status_code=400, detail="Invalid open point input_type")

    updated = crud.answer_open_point(db, project_id, open_point_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Open point not found")
    return _to_openpoint_out(db, updated)


# ---- Attachments (evidence files) ----

@router.post("/{open_point_id}/attachments", response_model=OpenPointAttachmentOut, status_code=status.HTTP_201_CREATED)
def add_attachment(
    project_id: str,
    open_point_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _ensure_project(db, project_id)
    op = crud.get_open_point(db, project_id, open_point_id)
    if op is None:
        raise HTTPException(status_code=404, detail="Open point not found")

    attachment_id = str(uuid.uuid4())
    try:
        storage_path, size_bytes, filename, content_type = save_openpoint_attachment_to_disk(
            project_id, open_point_id, attachment_id, file
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    att = crud.create_openpoint_attachment(
        db=db,
        open_point_id=open_point_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
    )

    return _to_attachment_out(att)


@router.get("/{open_point_id}/attachments/{attachment_id}/download")
def download_attachment(
    project_id: str,
    open_point_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
):
    _ensure_project(db, project_id)
    op = crud.get_open_point(db, project_id, open_point_id)
    if op is None:
        raise HTTPException(status_code=404, detail="Open point not found")

    att = crud.get_openpoint_attachment(db, open_point_id, attachment_id)
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    return FileResponse(path=att.storage_path, filename=att.filename, media_type=att.content_type)


@router.delete("/{open_point_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    project_id: str,
    open_point_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
):
    _ensure_project(db, project_id)
    op = crud.get_open_point(db, project_id, open_point_id)
    if op is None:
        raise HTTPException(status_code=404, detail="Open point not found")

    att = crud.get_openpoint_attachment(db, open_point_id, attachment_id)
    if att is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    delete_openpoint_attachment_files(project_id, open_point_id, attachment_id)

    db.delete(att)
    db.commit()
    return None