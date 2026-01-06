"""
    Pydantic‑Schemas für das FaSiKo‑Backend.

    Diese Datei definiert die Datenstrukturen für Anfragen und Antworten der
    API. Die Klassen sind eng an die zugrunde liegenden Datenbankmodelle
    angelehnt und ermöglichen eine klare Typisierung sowie Validierung
    der Eingaben. Für Block 06 wurden Ready‑Schemes ergänzt.
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

# -------- Projekte --------

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

class ProjectOut(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

# -------- Health --------

class HealthOut(BaseModel):
    status: str
    app: str

# -------- Ready (neu in Block 06) --------

class ReadyComponent(BaseModel):
    """Beschreibt den Zustand einer einzelnen Komponente für den Ready‑Check."""
    name: str
    status: str
    message: str | None = None

class ReadyOut(BaseModel):
    """Aggregierter Ready‑Check für alle Komponenten."""
    components: list[ReadyComponent]

# -------- Sources (Uploads) --------

class SourceOut(BaseModel):
    id: str
    project_id: str
    group_id: str
    filename: str
    content_type: str
    size_bytes: int
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime

class SourceListOut(BaseModel):
    items: list[SourceOut]

class SourceReplaceOut(BaseModel):
    old_id: str
    new: SourceOut

# -------- Artifacts (Dokumente) + Versionierung --------

class ArtifactCreate(BaseModel):
    type: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=250)
    initial_content_md: str = Field(default="")
    status: str = Field(default="draft")

class ArtifactUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    status: str | None = Field(default=None)

class ArtifactOut(BaseModel):
    id: str
    project_id: str
    type: str
    title: str
    status: str
    current_version: int
    versions_count: int
    created_at: datetime
    updated_at: datetime

class ArtifactDetailOut(BaseModel):
    id: str
    project_id: str
    type: str
    title: str
    status: str
    current_version: int
    versions_count: int
    current_content_md: str
    created_at: datetime
    updated_at: datetime

class ArtifactListOut(BaseModel):
    items: list[ArtifactOut]

class ArtifactVersionOut(BaseModel):
    id: str
    artifact_id: str
    version: int
    content_md: str
    created_at: datetime

class ArtifactVersionListOut(BaseModel):
    items: list[ArtifactVersionOut]

class ArtifactVersionCreate(BaseModel):
    content_md: str = Field(default="")
    make_current: bool = Field(default=True)

class ArtifactSetCurrent(BaseModel):
    version: int = Field(ge=1)

# -------- Artefakt‑Generierung (Block 4) --------

class ArtifactGenerateRequest(BaseModel):
    """Anforderung zur Generierung mehrerer Artefakte."""
    types: list[str] = Field(..., description="Liste der zu generierenden Artefakt‑Typen")

class GeneratedArtifactOut(BaseModel):
    """Ein generiertes Artefakt mit neuer Version und offenen Punkten."""
    artifact: ArtifactOut
    version: ArtifactVersionOut
    open_points: list["OpenPointOut"]

class ArtifactGenerateResponse(BaseModel):
    """Antwort auf die Generierung mehrerer Artefakte."""
    items: list[GeneratedArtifactOut]

# -------- Open Points --------

OPENPOINT_STATUS = {"offen", "in_bearbeitung", "fertig", "archiviert"}
OPENPOINT_PRIORITY = {"kritisch", "wichtig", "nice-to-have"}
OPENPOINT_INPUT = {"text", "choice", "file"}

class OpenPointCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    input_type: str = Field(default="text", description="text|choice|file")
    priority: str = Field(default="wichtig", description="kritisch|wichtig|nice-to-have")
    status: str = Field(default="offen", description="offen|in_bearbeitung|fertig|archiviert")
    artifact_id: str | None = Field(default=None)
    bsi_ref: str | None = Field(default=None, max_length=200)
    section_ref: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=100)

class OpenPointUpdate(BaseModel):
    priority: str | None = Field(default=None)
    status: str | None = Field(default=None)
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    input_type: str | None = Field(default=None)
    artifact_id: str | None = Field(default=None)
    bsi_ref: str | None = Field(default=None, max_length=200)
    section_ref: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=100)

class OpenPointAnswer(BaseModel):
    # for input_type=text
    answer_text: str | None = Field(default=None)
    # for input_type=choice
    answer_choice: str | None = Field(default=None)
    # if true -> set status to fertig automatically
    mark_done: bool = Field(default=True)

class OpenPointAttachmentOut(BaseModel):
    id: str
    open_point_id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime

class OpenPointOut(BaseModel):
    id: str
    project_id: str
    artifact_id: str | None
    bsi_ref: str | None
    section_ref: str | None
    category: str | None
    question: str
    input_type: str
    status: str
    priority: str
    answer_text: str | None
    answer_choice: str | None
    attachments_count: int
    created_at: datetime
    updated_at: datetime

class OpenPointDetailOut(OpenPointOut):
    attachments: list[OpenPointAttachmentOut]

class OpenPointListOut(BaseModel):
    items: list[OpenPointOut]

# -------- Chat (Block 5) --------

CHAT_ROLE = {"user", "assistant", "system"}

class ChatSessionCreate(BaseModel):
    project_id: str | None = Field(default=None)
    title: str | None = Field(default=None, max_length=200)

class ChatSessionOut(BaseModel):
    id: str
    project_id: str | None
    title: str | None
    created_at: datetime
    updated_at: datetime

class ChatSessionListOut(BaseModel):
    items: list[ChatSessionOut]

class ChatMessageCreate(BaseModel):
    role: str = Field(default="user", description="user|assistant|system")
    content: str = Field(default="", max_length=200000)

class ChatMessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime

class ChatMessageListOut(BaseModel):
    items: list[ChatMessageOut]

# -------- Erweiterungen für Chat (Dateianhänge, Assistent) --------

class ChatSessionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)

class ChatAttachmentOut(BaseModel):
    id: str
    message_id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime

class ChatMessageDetailOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    attachments: list[ChatAttachmentOut]

class ChatAssistantIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)

class WebSearchResult(BaseModel):
    """Struktur eines Websuchergebnisses aus SearXNG."""
    title: str
    url: str

class ChatAssistantReplyOut(BaseModel):
    """Antwort des Assistenten inklusive Quellen."""
    message: ChatMessageOut
    sources: list[WebSearchResult]