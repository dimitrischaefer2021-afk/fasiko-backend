"""
Definition aller Datenbankmodelle für das FaSiKo‑Backend.

Die Tabellen umfassen Projekte, Quellen, Artefakte mit Versionen,
Offene Punkte sowie Chat‑Sessions und ‑Nachrichten. Alle IDs
werden als UUIDs (Strings) gespeichert. Zeitstempel werden als
timezone‑aware ``datetime`` Werte gespeichert.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    DateTime,
    Integer,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    """Hilfsfunktion zum Erzeugen eines UTC‑Zeitstempels."""
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    sources: Mapped[list["SourceDocument"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    open_points: Mapped[list["OpenPoint"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    # optional später: Chat‑Sessions zu Projekten zuordnen
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


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

    # Ergebnisse der Textextraktion (Block 17)
    extraction_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown"
    )  # ok|partial|error|unknown
    extraction_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # Fehlertext oder Grund für partial/error
    extracted_text_len: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # Länge des extrahierten Texts

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
    Offener Punkt = fehlende Information / Frage, die beantwortet werden muss.

    status: offen | in_bearbeitung | fertig | archiviert
    priority: kritisch | wichtig | nice-to-have
    input_type: text | choice | file
    """

    __tablename__ = "open_points"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # flexible Referenzen (optional)
    artifact_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    bsi_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)  # z. B. "APP.1.2", "SYS.2.1"
    section_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)  # z. B. "Kapitel 3.2"
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)  # z. B. "Technik", "Organisation"

    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    input_type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")  # text|choice|file

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="offen")
    priority: Mapped[str] = mapped_column(String(30), nullable=False, default="wichtig")

    # Speicherung der Antwort (MVP: nur einfache Speicherung, keine Trigger)
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


# ----------------- Chat‑Modelle -----------------


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # optional: Projektbezug (nullable)
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


# ----------------- BSI‑Katalog‑Modelle (Block 18) -----------------

class BsiCatalog(Base):
    """Repräsentiert einen hochgeladenen BSI‑Katalog (PDF).

    Jede Datei erhält eine eindeutige ID und eine fortlaufende Versionsnummer.
    Die zugehörigen Module und Anforderungen werden nach dem Upload aus dem PDF
    extrahiert und in eigenen Tabellen gespeichert.
    """

    __tablename__ = "bsi_catalogs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Beziehungen
    modules: Mapped[list["BsiModule"]] = relationship(
        back_populates="catalog",
        cascade="all, delete-orphan",
        order_by="BsiModule.code",
    )


class BsiModule(Base):
    """Repräsentiert ein BSI‑Modul/Baustein innerhalb eines Katalogs.

    Beispiel: SYS.3.2.2 Systemadministration. Jedes Modul gehört zu genau
    einem Katalog und kann mehrere Anforderungen/Maßnahmen enthalten.
    """

    __tablename__ = "bsi_modules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    catalog_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bsi_catalogs.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Beziehungen
    catalog: Mapped["BsiCatalog"] = relationship(back_populates="modules")
    requirements: Mapped[list["BsiRequirement"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="BsiRequirement.req_id",
    )


class BsiRequirement(Base):
    """Repräsentiert eine Anforderung/Maßnahme innerhalb eines BSI‑Moduls.

    Eine Anforderung wird anhand ihres vollständigen BSI‑Codes inklusive Titel
    identifiziert, z. B. ``SYS.4.3.A1 Regelungen zum Umgang mit eingebetteten
    Systemen (B)``. Dieses Feld kann länger sein als die klassische
    "A1"‑Kennung, daher wurde die Länge der Spalte erhöht.
    Der ausführliche Beschreibungstext enthält nur den normativen Anteil
    nach dem Titel.
    """

    __tablename__ = "bsi_requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bsi_modules.id", ondelete="CASCADE"), nullable=False
    )
    # Kennung der Anforderung: vollständiger BSI‑Code inklusive Titel und
    # Klassifizierung. Da manche Anforderungen sehr lange Titel besitzen oder
    # keine Klassifizierung enthalten, verwenden wir für die Kennung den Typ
    # ``Text`` (unbegrenzte Länge). Die eigentliche Titel‑ und
    # Klassifizierungsinformation wird zusätzlich in den Feldern
    # ``title`` und ``classification`` gespeichert.
    req_id: Mapped[str] = mapped_column(Text, nullable=False)

    # Reiner Titel der Anforderung (ohne Klassifizierung und ohne Code).
    title: Mapped[str] = mapped_column(String(1000), nullable=False)

    # Klassifizierung der Anforderung: ``B`` für Basis, ``S`` für Standard,
    # ``H`` für Hoch oder ``None`` wenn nicht angegeben.
    classification: Mapped[str | None] = mapped_column(String(1), nullable=True)

    # Ob die Anforderung als entfallen gekennzeichnet ist (``ENTFALLEN`` im Titel).
    is_obsolete: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=0
    )  # 0 = False, 1 = True

    # Ausführliche normative Beschreibung der Maßnahme (Markdown oder Plaintext).
    description: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

    # Beziehung
    module: Mapped["BsiModule"] = relationship(back_populates="requirements")