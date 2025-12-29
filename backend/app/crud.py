import json
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .models import (
    Project, SourceDocument,
    Artifact, ArtifactVersion,
    OpenPoint, OpenPointAttachment,
    ChatSession, ChatMessage, ChatAttachment,
)
from .schemas import (
    ProjectCreate, ProjectUpdate,
    ArtifactCreate, ArtifactUpdate, ArtifactVersionCreate,
    OpenPointCreate, OpenPointUpdate, OpenPointAnswer,
    ChatSessionCreate, ChatMessageCreate,
)
from .storage import tags_to_json


# ---------- Projects ----------

def create_project(db: Session, payload: ProjectCreate) -> Project:
    project = Project(name=payload.name, description=payload.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session, limit: int = 100, offset: int = 0) -> list[Project]:
    stmt = select(Project).order_by(Project.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def get_project(db: Session, project_id: str) -> Project | None:
    return db.get(Project, project_id)


def update_project(db: Session, project_id: str, payload: ProjectUpdate) -> Project | None:
    project = db.get(Project, project_id)
    if project is None:
        return None
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: str) -> bool:
    project = db.get(Project, project_id)
    if project is None:
        return False
    db.delete(project)
    db.commit()
    return True


# ---------- Sources ----------

def create_source_record(
    db: Session,
    project_id: str,
    source_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
    tags: list[str],
) -> SourceDocument:
    src = SourceDocument(
        id=source_id,
        project_id=project_id,
        group_id=source_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        tags_json=tags_to_json(tags),
        status="stored",
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return src


def list_sources(db: Session, project_id: str) -> list[SourceDocument]:
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.project_id == project_id)
        .order_by(SourceDocument.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_source(db: Session, project_id: str, source_id: str) -> SourceDocument | None:
    src = db.get(SourceDocument, source_id)
    if src is None:
        return None
    if src.project_id != project_id:
        return None
    return src


def delete_source(db: Session, project_id: str, source_id: str) -> bool:
    src = get_source(db, project_id, source_id)
    if src is None:
        return False
    src.status = "deleted"
    db.add(src)
    db.commit()
    return True


def replace_source(
    db: Session,
    project_id: str,
    old_source_id: str,
    new_source_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
    tags: list[str],
) -> tuple[SourceDocument, SourceDocument] | None:
    old = get_source(db, project_id, old_source_id)
    if old is None:
        return None

    old.status = "replaced"
    db.add(old)
    db.commit()
    db.refresh(old)

    new = SourceDocument(
        id=new_source_id,
        project_id=project_id,
        group_id=old.group_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        tags_json=tags_to_json(tags),
        status="stored",
    )
    db.add(new)
    db.commit()
    db.refresh(new)

    return old, new


def source_tags(src: SourceDocument) -> list[str]:
    try:
        data = json.loads(src.tags_json or "[]")
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


# ---------- Artifacts + Versioning ----------

def create_artifact(db: Session, project_id: str, payload: ArtifactCreate) -> Artifact:
    art = Artifact(
        project_id=project_id,
        type=payload.type.strip(),
        title=payload.title.strip(),
        status=(payload.status or "draft").strip(),
        current_version=1,
    )
    db.add(art)
    db.commit()
    db.refresh(art)

    v1 = ArtifactVersion(
        artifact_id=art.id,
        version=1,
        content_md=payload.initial_content_md or "",
    )
    db.add(v1)
    db.commit()
    db.refresh(art)
    return art


def list_artifacts(db: Session, project_id: str) -> list[Artifact]:
    stmt = (
        select(Artifact)
        .where(Artifact.project_id == project_id)
        .order_by(Artifact.updated_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_artifact(db: Session, project_id: str, artifact_id: str) -> Artifact | None:
    art = db.get(Artifact, artifact_id)
    if art is None:
        return None
    if art.project_id != project_id:
        return None
    return art


def count_versions(db: Session, artifact_id: str) -> int:
    stmt = select(func.count()).select_from(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact_id)
    return int(db.execute(stmt).scalar_one())


def get_current_version(db: Session, artifact_id: str, current_version: int) -> ArtifactVersion | None:
    stmt = (
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .where(ArtifactVersion.version == current_version)
    )
    return db.execute(stmt).scalars().first()


def update_artifact_meta(db: Session, project_id: str, artifact_id: str, payload: ArtifactUpdate) -> Artifact | None:
    art = get_artifact(db, project_id, artifact_id)
    if art is None:
        return None
    if payload.title is not None:
        art.title = payload.title.strip()
    if payload.status is not None:
        art.status = payload.status.strip()
    db.add(art)
    db.commit()
    db.refresh(art)
    return art


def delete_artifact(db: Session, project_id: str, artifact_id: str) -> bool:
    art = get_artifact(db, project_id, artifact_id)
    if art is None:
        return False
    db.delete(art)
    db.commit()
    return True


def list_versions(db: Session, artifact_id: str) -> list[ArtifactVersion]:
    stmt = (
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_version(db: Session, artifact_id: str, version: int) -> ArtifactVersion | None:
    stmt = (
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .where(ArtifactVersion.version == version)
    )
    return db.execute(stmt).scalars().first()


def create_version(db: Session, artifact_id: str, payload: ArtifactVersionCreate) -> ArtifactVersion:
    stmt = select(func.max(ArtifactVersion.version)).where(ArtifactVersion.artifact_id == artifact_id)
    max_v = db.execute(stmt).scalar_one()
    next_v = int(max_v or 0) + 1

    ver = ArtifactVersion(
        artifact_id=artifact_id,
        version=next_v,
        content_md=payload.content_md or "",
    )
    db.add(ver)
    db.commit()
    db.refresh(ver)

    if payload.make_current:
        art = db.get(Artifact, artifact_id)
        if art is not None:
            art.current_version = next_v
            db.add(art)
            db.commit()

    return ver


def set_current_version(db: Session, artifact_id: str, version: int) -> bool:
    v = get_version(db, artifact_id, version)
    if v is None:
        return False
    art = db.get(Artifact, artifact_id)
    if art is None:
        return False
    art.current_version = version
    db.add(art)
    db.commit()
    return True


# ---------- Open Points ----------

def create_open_point(db: Session, project_id: str, payload: OpenPointCreate) -> OpenPoint:
    op = OpenPoint(
        project_id=project_id,
        artifact_id=payload.artifact_id,
        bsi_ref=payload.bsi_ref,
        section_ref=payload.section_ref,
        category=payload.category,
        question=payload.question.strip(),
        input_type=(payload.input_type or "text").strip(),
        status=(payload.status or "offen").strip(),
        priority=(payload.priority or "wichtig").strip(),
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def list_open_points(
    db: Session,
    project_id: str,
    status: str | None = None,
    priority: str | None = None,
    artifact_id: str | None = None,
) -> list[OpenPoint]:
    stmt = select(OpenPoint).where(OpenPoint.project_id == project_id)
    if status:
        stmt = stmt.where(OpenPoint.status == status)
    if priority:
        stmt = stmt.where(OpenPoint.priority == priority)
    if artifact_id:
        stmt = stmt.where(OpenPoint.artifact_id == artifact_id)
    stmt = stmt.order_by(OpenPoint.updated_at.desc())
    return list(db.execute(stmt).scalars().all())


def get_open_point(db: Session, project_id: str, open_point_id: str) -> OpenPoint | None:
    op = db.get(OpenPoint, open_point_id)
    if op is None:
        return None
    if op.project_id != project_id:
        return None
    return op


def update_open_point(db: Session, project_id: str, open_point_id: str, payload: OpenPointUpdate) -> OpenPoint | None:
    op = get_open_point(db, project_id, open_point_id)
    if op is None:
        return None

    if payload.priority is not None:
        op.priority = payload.priority.strip()
    if payload.status is not None:
        op.status = payload.status.strip()

    if payload.question is not None:
        op.question = payload.question.strip()
    if payload.input_type is not None:
        op.input_type = payload.input_type.strip()

    if payload.artifact_id is not None:
        op.artifact_id = payload.artifact_id
    if payload.bsi_ref is not None:
        op.bsi_ref = payload.bsi_ref
    if payload.section_ref is not None:
        op.section_ref = payload.section_ref
    if payload.category is not None:
        op.category = payload.category

    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def delete_open_point(db: Session, project_id: str, open_point_id: str) -> bool:
    op = get_open_point(db, project_id, open_point_id)
    if op is None:
        return False
    db.delete(op)
    db.commit()
    return True


def count_openpoint_attachments(db: Session, open_point_id: str) -> int:
    stmt = select(func.count()).select_from(OpenPointAttachment).where(OpenPointAttachment.open_point_id == open_point_id)
    return int(db.execute(stmt).scalar_one())


def answer_open_point(db: Session, project_id: str, open_point_id: str, payload: OpenPointAnswer) -> OpenPoint | None:
    op = get_open_point(db, project_id, open_point_id)
    if op is None:
        return None

    # Keep data clean:
    # - for text: set answer_text, clear answer_choice
    # - for choice: set answer_choice, clear answer_text
    # - for file: answers via attachments, do not touch text/choice fields
    if op.input_type == "text":
        if payload.answer_text is not None:
            op.answer_text = payload.answer_text
        op.answer_choice = None
    elif op.input_type == "choice":
        if payload.answer_choice is not None:
            op.answer_choice = payload.answer_choice
        op.answer_text = None
    else:
        # file: no changes here
        pass

    if payload.mark_done:
        op.status = "fertig"

    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def create_openpoint_attachment(
    db: Session,
    open_point_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
) -> OpenPointAttachment:
    att = OpenPointAttachment(
        open_point_id=open_point_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


def list_openpoint_attachments(db: Session, open_point_id: str) -> list[OpenPointAttachment]:
    stmt = (
        select(OpenPointAttachment)
        .where(OpenPointAttachment.open_point_id == open_point_id)
        .order_by(OpenPointAttachment.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_openpoint_attachment(db: Session, open_point_id: str, attachment_id: str) -> OpenPointAttachment | None:
    att = db.get(OpenPointAttachment, attachment_id)
    if att is None:
        return None
    if att.open_point_id != open_point_id:
        return None
    return att


# ---------- Chat (Block 5) ----------

def create_chat_session(db: Session, payload: ChatSessionCreate) -> ChatSession:
    sess = ChatSession(project_id=payload.project_id, title=payload.title)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def list_chat_sessions(db: Session, limit: int = 100, offset: int = 0) -> list[ChatSession]:
    stmt = select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def get_chat_session(db: Session, session_id: str) -> ChatSession | None:
    return db.get(ChatSession, session_id)


def delete_chat_session(db: Session, session_id: str) -> bool:
    sess = db.get(ChatSession, session_id)
    if sess is None:
        return False
    db.delete(sess)
    db.commit()
    return True


def create_chat_message(db: Session, session_id: str, payload: ChatMessageCreate) -> ChatMessage:
    msg = ChatMessage(session_id=session_id, role=payload.role, content=payload.content or "")
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def list_chat_messages(db: Session, session_id: str, limit: int = 200, offset: int = 0) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


def create_chat_attachment(
    db: Session,
    message_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
) -> ChatAttachment:
    att = ChatAttachment(
        message_id=message_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


def list_chat_attachments(db: Session, message_id: str) -> list[ChatAttachment]:
    stmt = (
        select(ChatAttachment)
        .where(ChatAttachment.message_id == message_id)
        .order_by(ChatAttachment.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())