from datetime import datetime
from pydantic import BaseModel, Field


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


class HealthOut(BaseModel):
    status: str
    app: str


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


# -------- Artifacts (Documents) + Versioning --------

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


# -------- Open Points --------

OPENPOINT_STATUS = {"offen", "in_bearbeitung", "fertig", "archiviert"}
OPENPOINT_PRIORITY = {"kritisch", "wichtig", "nice-to-have"}
OPENPOINT_INPUT = {"text", "choice", "file"}


class OpenPointCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    input_type: str = Field(default="text", description="text|choice|file")

    priority: str = Field(default="wichtig", description="kritisch|wichtig|nice-to-have")
    status: str = Field(default="offen", description="offen|in_bearbeitung|fertig|archiviert")

    # optional references
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


# -------- Chat (Block 5) --------

CHAT_ROLE = {"user", "assistant", "system"}


class ChatSessionCreate(BaseModel):
    # optional, for later: you can link chat to project
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


class ChatAttachmentOut(BaseModel):
    id: str
    message_id: str
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ChatMessageDetailOut(ChatMessageOut):
    attachments: list[ChatAttachmentOut]


class ChatStreamIn(BaseModel):
    content: str = Field(min_length=1, max_length=200000)
    # optional: override model if needed later
    model: str | None = Field(default=None)


class ChatStreamMetaOut(BaseModel):
    session_id: str
    user_message_id: str
    assistant_message_id: str | None = None