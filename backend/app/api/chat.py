"""
API‑Router für Chat-Funktionen.

Dieser Router ermöglicht das Anlegen und Verwalten von Chat-Sessions, das
Speichern von Nachrichten und Dateianhängen sowie das Nutzen eines
Assistenten, der basierend auf Konversation und Websuche antwortet.
"""

from __future__ import annotations

from datetime import datetime
import uuid
from typing import List

# Kein direkter Import von httpx erforderlich, da LLM-Aufrufe über llm_client laufen
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from .. import crud
from .. import storage
from .. import websearch
from ..settings import MODEL_GENERAL_8B
from ..llm_client import call_llm
from ..schemas import (
    ChatSessionCreate,
    ChatSessionOut,
    ChatSessionListOut,
    ChatSessionUpdate,
    ChatMessageCreate,
    ChatMessageOut,
    ChatMessageListOut,
    ChatMessageDetailOut,
    ChatAttachmentOut,
    ChatAssistantIn,
    ChatAssistantReplyOut,
    WebSearchResult,
)

router = APIRouter(prefix="/chat/sessions", tags=["chat"])

# System-Prompt: klare deutsche Antworten, keine Fußnoten
ASSISTANT_SYSTEM_PROMPT = (
    "Du bist ein hilfreicher Assistent, der Fragen beantwortet und Texte "
    "überarbeitet. Antworte stets klar, strukturiert und auf Deutsch. "
    "Wenn du Informationen aus Webquellen erhältst, nutze sie, um die Frage "
    "zu beantworten, aber nenne keine Links im Text."
)


def _ensure_session(db: Session, session_id: str) -> None:
    if crud.get_chat_session(db, session_id) is None:
        raise HTTPException(status_code=404, detail="Chat session not found")


def _ensure_message(db: Session, session_id: str, message_id: str) -> None:
    msg = crud.get_chat_message(db, message_id)
    if msg is None or msg.session_id != session_id:
        raise HTTPException(status_code=404, detail="Chat message not found")


def _to_session_out(sess) -> ChatSessionOut:
    return ChatSessionOut(
        id=sess.id,
        project_id=sess.project_id,
        title=sess.title,
        created_at=sess.created_at,
        updated_at=sess.updated_at,
    )


def _to_message_out(msg) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
    )


def _to_attachment_out(att) -> ChatAttachmentOut:
    return ChatAttachmentOut(
        id=att.id,
        message_id=att.message_id,
        filename=att.filename,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        created_at=att.created_at,
    )


def _to_message_detail(db: Session, msg) -> ChatMessageDetailOut:
    atts = crud.list_chat_attachments(db, msg.id)
    return ChatMessageDetailOut(
        id=msg.id,
        session_id=msg.session_id,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
        attachments=[_to_attachment_out(att) for att in atts],
    )


async def _call_llm(messages: List[dict]) -> str:
    """Verwendet den zentralen LLM‑Client für Chat‑Anfragen.

    Diese Funktion ruft das LLM über den gemeinsamen Client ``call_llm``
    auf und übergibt die Nachrichten sowie das allgemeine Chat‑Modell
    (8B). Fehler werden vom Aufrufer behandelt.
    """
    return await call_llm(messages=messages, model=MODEL_GENERAL_8B)


@router.post("", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: ChatSessionCreate, db: Session = Depends(get_db)) -> ChatSessionOut:
    sess = crud.create_chat_session(db, payload)
    return _to_session_out(sess)


@router.get("", response_model=ChatSessionListOut)
def list_sessions(project_id: str | None = None, db: Session = Depends(get_db)) -> ChatSessionListOut:
    sessions = crud.list_chat_sessions(db, project_id)
    return ChatSessionListOut(items=[_to_session_out(s) for s in sessions])


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_session(session_id: str, db: Session = Depends(get_db)) -> Response:
    ok = crud.delete_chat_session(db, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/messages", response_model=ChatMessageOut, status_code=status.HTTP_201_CREATED)
def create_message(session_id: str, payload: ChatMessageCreate, db: Session = Depends(get_db)) -> ChatMessageOut:
    _ensure_session(db, session_id)
    msg = crud.create_chat_message(db, session_id, payload)
    sess = crud.get_chat_session(db, session_id)
    if sess:
        sess.updated_at = datetime.utcnow()
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return _to_message_out(msg)


@router.get("/{session_id}/messages", response_model=ChatMessageListOut)
def list_messages(session_id: str, db: Session = Depends(get_db)) -> ChatMessageListOut:
    _ensure_session(db, session_id)
    msgs = crud.list_chat_messages(db, session_id)
    return ChatMessageListOut(items=[_to_message_out(m) for m in msgs])


# ---------------------------------------------------------------------------
# Einzelne Nachricht anzeigen und löschen
# ---------------------------------------------------------------------------

@router.get("/{session_id}/messages/{message_id}", response_model=ChatMessageDetailOut)
def get_message(session_id: str, message_id: str, db: Session = Depends(get_db)) -> ChatMessageDetailOut:
    """Liefert eine einzelne Nachricht inklusive ihrer Anhänge."""
    _ensure_session(db, session_id)
    _ensure_message(db, session_id, message_id)
    msg = crud.get_chat_message(db, message_id)
    return _to_message_detail(db, msg)


@router.delete(
    "/{session_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_message(session_id: str, message_id: str, db: Session = Depends(get_db)) -> Response:
    """Löscht eine Nachricht und alle zugehörigen Anhänge."""
    _ensure_session(db, session_id)
    _ensure_message(db, session_id, message_id)
    ok = crud.delete_chat_message(db, session_id, message_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat message not found")
    storage.delete_dir_recursively(storage.chat_message_dir(session_id, message_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Dateianhänge für Nachrichten
# ---------------------------------------------------------------------------

@router.post(
    "/{session_id}/messages/{message_id}/attachments",
    response_model=ChatAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_attachment(
    session_id: str,
    message_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ChatAttachmentOut:
    """Lädt einen Dateianhang zu einer Nachricht hoch."""
    _ensure_session(db, session_id)
    _ensure_message(db, session_id, message_id)
    attachment_id = str(uuid.uuid4())
    try:
        path, size, filename, content_type = storage.save_chat_attachment_to_disk(
            session_id, message_id, attachment_id, file
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    att = crud.create_chat_attachment(db, message_id, attachment_id, filename, content_type, size, path)
    sess = crud.get_chat_session(db, session_id)
    if sess:
        sess.updated_at = datetime.utcnow()
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return _to_attachment_out(att)


@router.get("/{session_id}/messages/{message_id}/attachments/{attachment_id}")
def download_attachment(
    session_id: str,
    message_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Lädt einen Dateianhang herunter."""
    _ensure_session(db, session_id)
    _ensure_message(db, session_id, message_id)
    att = crud.get_chat_attachment(db, attachment_id)
    if att is None or att.message_id != message_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return FileResponse(
        att.storage_path,
        media_type=att.content_type,
        filename=att.filename,
    )


@router.delete(
    "/{session_id}/messages/{message_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_attachment(
    session_id: str,
    message_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
) -> Response:
    """Löscht einen Anhang von einer Nachricht."""
    _ensure_session(db, session_id)
    _ensure_message(db, session_id, message_id)
    att = crud.get_chat_attachment(db, attachment_id)
    if att is None or att.message_id != message_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    ok = crud.delete_chat_attachment(db, message_id, attachment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Attachment not found")
    storage.delete_chat_attachment_files(session_id, message_id, attachment_id)
    sess = crud.get_chat_session(db, session_id)
    if sess:
        sess.updated_at = datetime.utcnow()
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{session_id}/assistant", response_model=ChatAssistantReplyOut)
async def assistant_reply(session_id: str, payload: ChatAssistantIn, db: Session = Depends(get_db)) -> ChatAssistantReplyOut:
    _ensure_session(db, session_id)
    user_msg = crud.create_chat_message(db, session_id, ChatMessageCreate(role="user", content=payload.content))
    sess = crud.get_chat_session(db, session_id)
    if sess:
        sess.updated_at = datetime.utcnow()
        db.add(sess)
        db.commit()
        db.refresh(sess)

    search_results = await websearch.searxng_search(payload.content)

    history = crud.list_chat_messages(db, session_id)
    messages: List[dict] = [{"role": "system", "content": ASSISTANT_SYSTEM_PROMPT}]
    if search_results:
        search_lines = []
        for idx, item in enumerate(search_results, start=1):
            title = item.get("title") or ""
            snippet = item.get("snippet") or ""
            search_lines.append(f"[{idx}] {title}\n{snippet}")
        context_text = "\n\n".join(search_lines)
        system_prompt = (
            "Die folgenden Quellen wurden online gefunden. Nutze sie, um die letzte Nutzerfrage zu beantworten. "
            "Antworte auf Deutsch, aber nenne keine Links im Text. "
            "Verweise nicht auf 'Quellen:' oder '[1]', '[2]' im Text."
            "\n\n" + context_text
        )
        messages.append({"role": "system", "content": system_prompt})
    for m in history:
        messages.append({"role": m.role, "content": m.content})

    answer_text = await _call_llm(messages) or ""
    cleaned_lines = []
    for line in answer_text.splitlines():
        if not line:
            cleaned_lines.append(line)
            continue
        low = line.strip().lower()
        if low.startswith("quellen") or low.startswith("quelle"):
            continue
        if "[1]" in line or "[2]" in line or "[3]" in line or "http://" in line or "https://" in line:
            continue
        cleaned_lines.append(line)
    answer_text = "\n".join(cleaned_lines).strip()

    assistant_msg = crud.create_chat_message(db, session_id, ChatMessageCreate(role="assistant", content=answer_text))
    sess = crud.get_chat_session(db, session_id)
    if sess:
        sess.updated_at = datetime.utcnow()
        db.add(sess)
        db.commit()
        db.refresh(sess)
    src_objs = [WebSearchResult(title=item.get("title") or "", url=item.get("url") or "") for item in search_results]
    return ChatAssistantReplyOut(message=_to_message_out(assistant_msg), sources=src_objs)