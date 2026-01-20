"""
CRUD‑Operationen für das FaSiKo‑Backend.

Dieses Modul enthält Funktionen zum Anlegen, Lesen, Aktualisieren und Löschen
der verschiedenen Datenbankeinträge (Projekte, Quellen, Artefakte, Versionen,
Offene Punkte, Anhänge, Chat‑Sessions und Chat‑Nachrichten). Die Funktionen
arbeiten mit SQLAlchemy‑Sessions und nutzen die in ``models.py`` definierten
ORM‑Klassen.
"""

import json
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from .models import (
    Project,
    SourceDocument,
    Artifact,
    ArtifactVersion,
    OpenPoint,
    OpenPointAttachment,
    ChatSession,
    ChatMessage,
    ChatAttachment,
    BsiCatalog,
    BsiModule,
    BsiRequirement,
)
from .schemas import (
    ProjectCreate,
    ProjectUpdate,
    ArtifactCreate,
    ArtifactUpdate,
    ArtifactVersionCreate,
    OpenPointCreate,
    OpenPointUpdate,
    OpenPointAnswer,
    ChatSessionCreate,
    ChatMessageCreate,
)

# Nur für BSI-Kataloge verwendete Funktionen (Block 18)

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
    extraction_status: str = "unknown",
    extraction_reason: str | None = None,
    extracted_text_len: int = 0,
) -> SourceDocument:
    """Erzeugt einen neuen SourceDocument‑Datensatz und speichert ihn in der DB.

    Der Parameter ``extraction_status`` gibt den Status der Textextraktion an
    (``ok``, ``partial``, ``error`` oder ``unknown``). ``extraction_reason``
    enthält eine optionale Fehlermeldung, und ``extracted_text_len`` gibt die
    Länge des extrahierten Textes an. Diese Felder werden in Block 17
    benötigt, um Upload‑Metadaten persistieren zu können.
    """
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
        extraction_status=extraction_status,
        extraction_reason=extraction_reason,
        extracted_text_len=extracted_text_len,
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
    # Erzeuge die erste Version
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


def get_version(db: Session, artifact_id: str, version: int) -> ArtifactVersion | None:
    stmt = (
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .where(ArtifactVersion.version == version)
    )
    return db.execute(stmt).scalars().first()


def list_versions(db: Session, artifact_id: str) -> list[ArtifactVersion]:
    stmt = select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact_id).order_by(ArtifactVersion.version.desc())
    return list(db.execute(stmt).scalars().all())


def create_version(db: Session, artifact_id: str, payload: ArtifactVersionCreate) -> ArtifactVersion:
    art = db.get(Artifact, artifact_id)
    if art is None:
        raise ValueError("Artifact not found")
    next_version = count_versions(db, artifact_id) + 1
    v = ArtifactVersion(
        artifact_id=artifact_id,
        version=next_version,
        content_md=payload.content_md or "",
    )
    db.add(v)
    db.commit()
    if payload.make_current:
        art.current_version = v.version
        db.add(art)
        db.commit()
    db.refresh(v)
    return v


def set_current_version(db: Session, artifact_id: str, version: int) -> bool:
    art = db.get(Artifact, artifact_id)
    if art is None:
        return False
    # Überprüfe, ob Version existiert
    v = get_version(db, artifact_id, version)
    if v is None:
        return False
    art.current_version = version
    db.add(art)
    db.commit()
    return True


def delete_artifact(db: Session, project_id: str, artifact_id: str) -> bool:
    art = get_artifact(db, project_id, artifact_id)
    if art is None:
        return False
    db.delete(art)
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
        input_type=payload.input_type.strip(),
        status=payload.status.strip() if payload.status else "offen",
        priority=payload.priority.strip() if payload.priority else "wichtig",
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    return op


def list_open_points(db: Session, project_id: str) -> list[OpenPoint]:
    stmt = (
        select(OpenPoint)
        .where(OpenPoint.project_id == project_id)
        .order_by(OpenPoint.created_at.asc())
    )
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
        op.priority = payload.priority
    if payload.status is not None:
        op.status = payload.status
    if payload.question is not None:
        op.question = payload.question
    if payload.input_type is not None:
        op.input_type = payload.input_type
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


def answer_open_point(db: Session, project_id: str, open_point_id: str, payload: OpenPointAnswer) -> OpenPoint | None:
    op = get_open_point(db, project_id, open_point_id)
    if op is None:
        return None
    if payload.answer_text is not None:
        op.answer_text = payload.answer_text
    if payload.answer_choice is not None:
        op.answer_choice = payload.answer_choice
    # optional: set to fertig
    if payload.mark_done:
        op.status = "fertig"
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


def list_open_points(
    db: Session,
    project_id: str,
    status: str | None = None,
    priority: str | None = None,
    artifact_id: str | None = None,
) -> list[OpenPoint]:
    """Liste der offenen Punkte nach optionalen Filtern."""
    stmt = select(OpenPoint).where(OpenPoint.project_id == project_id)
    if status:
        stmt = stmt.where(OpenPoint.status == status)
    if priority:
        stmt = stmt.where(OpenPoint.priority == priority)
    if artifact_id:
        stmt = stmt.where(OpenPoint.artifact_id == artifact_id)
    stmt = stmt.order_by(OpenPoint.created_at.asc())
    return list(db.execute(stmt).scalars().all())


def list_openpoint_attachments(db: Session, open_point_id: str) -> list[OpenPointAttachment]:
    stmt = (
        select(OpenPointAttachment)
        .where(OpenPointAttachment.open_point_id == open_point_id)
        .order_by(OpenPointAttachment.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def count_openpoint_attachments(db: Session, open_point_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(OpenPointAttachment)
        .where(OpenPointAttachment.open_point_id == open_point_id)
    )
    return int(db.execute(stmt).scalar_one())


# ---------- Open Point Attachments ----------


def create_open_point_attachment(
    db: Session,
    open_point_id: str,
    attachment_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
) -> OpenPointAttachment:
    att = OpenPointAttachment(
        id=attachment_id,
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


def list_open_point_attachments(db: Session, open_point_id: str) -> list[OpenPointAttachment]:
    stmt = (
        select(OpenPointAttachment)
        .where(OpenPointAttachment.open_point_id == open_point_id)
        .order_by(OpenPointAttachment.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_open_point_attachment(db: Session, attachment_id: str) -> OpenPointAttachment | None:
    return db.get(OpenPointAttachment, attachment_id)


def delete_open_point_attachment(db: Session, project_id: str, open_point_id: str, attachment_id: str) -> bool:
    att = get_open_point_attachment(db, attachment_id)
    if att is None:
        return False
    # sicherstellen, dass attachment zum richtigen open_point gehört
    if att.open_point_id != open_point_id:
        return False
    db.delete(att)
    db.commit()
    return True


# ---------- Chat Sessions ----------


def create_chat_session(db: Session, payload: ChatSessionCreate) -> ChatSession:
    sess = ChatSession(project_id=payload.project_id, title=payload.title)
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def list_chat_sessions(db: Session, project_id: str | None) -> list[ChatSession]:
    stmt = select(ChatSession)
    if project_id:
        stmt = stmt.where(ChatSession.project_id == project_id)
    stmt = stmt.order_by(ChatSession.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def get_chat_session(db: Session, session_id: str) -> ChatSession | None:
    return db.get(ChatSession, session_id)

# ---------- Delete Chat Session ----------

def delete_chat_session(db: Session, session_id: str) -> bool:
    """Löscht eine Chat‑Session und alle zugehörigen Nachrichten und Anhänge.

    Aufgrund der in models.py gesetzten cascade‑Optionen werden die zugehörigen
    ChatMessages und ChatAttachments automatisch entfernt.
    """
    sess = db.get(ChatSession, session_id)
    if sess is None:
        return False
    db.delete(sess)
    db.commit()
    return True


# ---------- Chat Messages ----------


def create_chat_message(db: Session, session_id: str, payload: ChatMessageCreate) -> ChatMessage:
    # Sicherheit: nur bestimmte Rollen erlauben
    if payload.role not in {"user", "assistant", "system"}:
        raise ValueError("Invalid role")
    msg = ChatMessage(
        session_id=session_id,
        role=payload.role,
        content=payload.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def list_chat_messages(db: Session, session_id: str) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_chat_message(db: Session, msg_id: str) -> ChatMessage | None:
    return db.get(ChatMessage, msg_id)

# ---------- Delete Chat Message ----------

def delete_chat_message(db: Session, session_id: str, message_id: str) -> bool:
    """Löscht eine Nachricht aus einer Chat‑Session.

    Die Anhänge der Nachricht werden automatisch gelöscht (cascade).
    """
    msg = db.get(ChatMessage, message_id)
    if msg is None:
        return False
    if msg.session_id != session_id:
        return False
    db.delete(msg)
    db.commit()
    return True


# ---------- Chat Attachments ----------


def create_chat_attachment(
    db: Session,
    message_id: str,
    attachment_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
) -> ChatAttachment:
    att = ChatAttachment(
        id=attachment_id,
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


def get_chat_attachment(db: Session, attachment_id: str) -> ChatAttachment | None:
    return db.get(ChatAttachment, attachment_id)


def delete_chat_attachment(db: Session, message_id: str, attachment_id: str) -> bool:
    att = get_chat_attachment(db, attachment_id)
    if att is None:
        return False
    if att.message_id != message_id:
        return False
    db.delete(att)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# BSI‑Katalog‑Funktionen (Block 18)
# ---------------------------------------------------------------------------

def create_bsi_catalog(
    db: Session,
    filename: str,
    storage_path: str,
    modules_data: list[
        tuple[
            str,
            str,
            list[tuple[str, str, str | None, bool, str]],
        ]
    ],
) -> BsiCatalog:
    """Erzeugt einen neuen BSI‑Katalog samt seiner Module und Anforderungen.

    :param filename: Ursprünglicher Dateiname der hochgeladenen PDF.
    :param storage_path: Pfad, unter dem die PDF gespeichert wurde.
    :param modules_data: Liste von Tupeln (code, title, requirements). ``requirements``
        ist wiederum eine Liste von Tupeln (req_id, title, classification, is_obsolete, description).
    :returns: Das neu angelegte ``BsiCatalog``.
    """
    # Bestimme die nächste Versionsnummer
    current_max = db.execute(select(func.max(BsiCatalog.version))).scalar()
    next_version = (current_max or 0) + 1
    catalog = BsiCatalog(
        version=next_version,
        filename=filename,
        storage_path=storage_path,
    )
    db.add(catalog)
    db.commit()
    db.refresh(catalog)
    # Füge Module und Anforderungen hinzu
    for module_code, module_title, reqs in modules_data:
        module = BsiModule(catalog_id=catalog.id, code=module_code, title=module_title)
        db.add(module)
        db.commit()
        db.refresh(module)
        for req_id, title, classification, is_obsolete, req_desc in reqs:
            # Speichere neben den normalisierten Feldern auch die Rohdaten.
            # raw_title und raw_description enthalten den unveränderten
            # extrahierten Text und werden erst durch den Normalizer (Block 21)
            # verarbeitet. Vorher sind raw_title und raw_description identisch
            # mit title und req_desc.
            requirement = BsiRequirement(
                module_id=module.id,
                req_id=req_id,
                title=title,
                classification=classification,
                is_obsolete=1 if is_obsolete else 0,
                description=req_desc,
                raw_title=title,
                raw_description=req_desc,
            )
            db.add(requirement)
        db.commit()
    db.refresh(catalog)
    return catalog


def list_bsi_catalogs(db: Session, limit: int = 100, offset: int = 0) -> list[BsiCatalog]:
    """Liefert alle BSI‑Kataloge sortiert nach Erstellungsdatum absteigend."""
    stmt = select(BsiCatalog).order_by(BsiCatalog.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def get_bsi_catalog(db: Session, catalog_id: str) -> BsiCatalog | None:
    """Liest einen BSI‑Katalog anhand seiner ID."""
    return db.get(BsiCatalog, catalog_id)


def list_bsi_modules(db: Session, catalog_id: str) -> list[BsiModule]:
    """Liefert alle Module zu einem Katalog, sortiert nach Modulkürzel."""
    stmt = select(BsiModule).where(BsiModule.catalog_id == catalog_id).order_by(BsiModule.code)
    return list(db.execute(stmt).scalars().all())


def get_bsi_module(db: Session, module_id: str) -> BsiModule | None:
    """Liest ein BSI‑Modul anhand seiner ID."""
    return db.get(BsiModule, module_id)


def list_bsi_requirements(db: Session, module_id: str) -> list[BsiRequirement]:
    """Liefert alle Anforderungen zu einem Modul, sortiert nach Req‑ID."""
    stmt = select(BsiRequirement).where(BsiRequirement.module_id == module_id).order_by(BsiRequirement.req_id)
    return list(db.execute(stmt).scalars().all())