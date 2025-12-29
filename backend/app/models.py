import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    sources: Mapped[list["SourceDocument"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    open_points: Mapped[list["OpenPoint"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    # optional later: connect chats to projects (we allow nullable project_id on sessions)
    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class SourceDocument(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    group_id: Mapped[str] = mapped_column(String(36), nullable=False)

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    tags_json: Mapped[str] = mapped_column(String(4000), nullable=False, default="[]")
    storage_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="stored")  # stored|replaced|deleted

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    project: Mapped["Project"] = relationship(back_populates="sources")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    type: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")  # draft|review|final

    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    project: Mapped["Project"] = relationship(back_populates="artifacts")
    versions: Mapped[list["ArtifactVersion"]] = relationship(
        back_populates="artifact",
        cascade="all, delete-orphan",
        order_by="ArtifactVersion.version.desc()",
    )


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    artifact_id: Mapped[str] = mapped_column(String(36), ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    artifact: Mapped["Artifact"] = relationship(back_populates="versions")


class OpenPoint(Base):
    """
    Open Point = a missing info/question that must be answered for project completeness.

    status: offen | in_bearbeitung | fertig | archiviert
    priority: kritisch | wichtig | nice-to-have
    input_type: text | choice | file
    """
    __tablename__ = "open_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # flexible references (optional)
    artifact_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    bsi_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g., "APP.1.2", "SYS.2.1"
    section_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)  # e.g., "Kapitel 3.2"
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g., "Technik", "Organisation"

    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    input_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")  # text|choice|file

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="offen")
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="wichtig")

    # Answer storage (MVP: only save, no triggers)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_choice: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    project: Mapped["Project"] = relationship(back_populates="open_points")
    artifact: Mapped["Artifact"] = relationship()
    attachments: Mapped[list["OpenPointAttachment"]] = relationship(
        back_populates="open_point",
        cascade="all, delete-orphan",
        order_by="OpenPointAttachment.created_at.desc()",
    )


class OpenPointAttachment(Base):
    __tablename__ = "open_point_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    open_point_id: Mapped[str] = mapped_column(String(36), ForeignKey("open_points.id", ondelete="CASCADE"), nullable=False)

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    open_point: Mapped["OpenPoint"] = relationship(back_populates="attachments")


# ----------------- Chat (Block 5) -----------------

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # optional: link to a project later
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    project: Mapped["Project"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at.asc()",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")  # user|assistant|system
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
    attachments: Mapped[list["ChatAttachment"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="ChatAttachment.created_at.desc()",
    )


class ChatAttachment(Base):
    __tablename__ = "chat_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False)

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(2048), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    message: Mapped["ChatMessage"] = relationship(back_populates="attachments")