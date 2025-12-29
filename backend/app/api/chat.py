import json
import os
import uuid
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..db import get_db, SessionLocal
from .. import crud
from ..schemas import (
    ChatSessionCreate, ChatSessionOut, ChatSessionListOut,
    ChatMessageCreate, ChatMessageOut, ChatMessageListOut,
    ChatAttachmentOut, ChatMessageDetailOut,
    ChatStreamIn,
)

router = APIRouter(prefix="/chat", tags=["chat"])

# --- Config (ENV, no settings.py changes needed) ---
# IMPORTANT: Default is docker-compose service name "ollama"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
OLLAMA_DISABLED = os.getenv("OLLAMA_DISABLED", "").strip().lower() in {"1", "true", "yes"}

# storage
CHAT_DIR = os.getenv("CHAT_DIR", "/data/chat")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(30 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1].strip()
    return name if name else "upload.bin"


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def _ensure_allowed(file: UploadFile) -> None:
    filename = _safe_filename(file.filename or "")
    ext = _ext(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file extension: {ext}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )


def _chat_attachment_dir(session_id: str, message_id: str, attachment_id: str) -> Path:
    base = Path(CHAT_DIR)
    return base / session_id / message_id / attachment_id


def _save_upload_to_disk(session_id: str, message_id: str, file: UploadFile) -> tuple[str, int, str, str]:
    _ensure_allowed(file)
    filename = _safe_filename(file.filename or "")
    content_type = (file.content_type or "application/octet-stream").strip()

    attachment_id = str(uuid.uuid4())
    target_dir = _chat_attachment_dir(session_id, message_id, attachment_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename

    size = 0
    with open(target_path, "wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                try:
                    out.close()
                except Exception:
                    pass
                try:
                    if target_path.exists():
                        target_path.unlink()
                except Exception:
                    pass
                raise HTTPException(status_code=400, detail=f"File too large. Max is {MAX_UPLOAD_BYTES} bytes.")
            out.write(chunk)

    return (str(target_path), size, filename, content_type)


def _to_session_out(s) -> ChatSessionOut:
    return ChatSessionOut(
        id=s.id,
        project_id=s.project_id,
        title=s.title,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _to_message_out(m) -> ChatMessageOut:
    return ChatMessageOut(
        id=m.id,
        session_id=m.session_id,
        role=m.role,
        content=m.content,
        created_at=m.created_at,
    )


def _to_attachment_out(a) -> ChatAttachmentOut:
    return ChatAttachmentOut(
        id=a.id,
        message_id=a.message_id,
        filename=a.filename,
        content_type=a.content_type,
        size_bytes=a.size_bytes,
        created_at=a.created_at,
    )


def _ensure_session(db: Session, session_id: str):
    sess = crud.get_chat_session(db, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return sess


@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: ChatSessionCreate, db: Session = Depends(get_db)):
    if payload.project_id:
        if crud.get_project(db, payload.project_id) is None:
            raise HTTPException(status_code=400, detail="project_id not found")

    sess = crud.create_chat_session(db, payload)
    return _to_session_out(sess)


@router.get("/sessions", response_model=ChatSessionListOut)
def list_sessions(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    items = [_to_session_out(s) for s in crud.list_chat_sessions(db, limit=limit, offset=offset)]
    return {"items": items}


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)):
    sess = _ensure_session(db, session_id)
    return _to_session_out(sess)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    ok = crud.delete_chat_session(db, session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return None


@router.get("/sessions/{session_id}/messages", response_model=ChatMessageListOut)
def list_messages(session_id: str, limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    _ensure_session(db, session_id)
    msgs = crud.list_chat_messages(db, session_id, limit=limit, offset=offset)
    return {"items": [_to_message_out(m) for m in msgs]}


@router.post("/sessions/{session_id}/messages", response_model=ChatMessageDetailOut, status_code=status.HTTP_201_CREATED)
def create_message_with_optional_uploads(
    session_id: str,
    role: str = Form("user"),
    content: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
):
    _ensure_session(db, session_id)

    payload = ChatMessageCreate(role=role, content=content)
    msg = crud.create_chat_message(db, session_id, payload)

    atts_out: list[ChatAttachmentOut] = []
    if files:
        for f in files:
            storage_path, size_bytes, filename, content_type = _save_upload_to_disk(session_id, msg.id, f)
            att = crud.create_chat_attachment(
                db=db,
                message_id=msg.id,
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                storage_path=storage_path,
            )
            atts_out.append(_to_attachment_out(att))

    base = _to_message_out(msg)
    return ChatMessageDetailOut(**base.model_dump(), attachments=atts_out)


def _ollama_stream(messages: list[dict], model: str) -> Iterator[str]:
    """
    Sync generator that yields SSE frames.
    Uses urllib (stdlib) to avoid new dependencies.
    """
    import urllib.request
    import urllib.error

    url = f"{OLLAMA_URL}/api/chat"
    payload = {"model": model, "messages": messages, "stream": True}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = ""
                try:
                    line = raw.decode("utf-8").strip()
                except Exception:
                    continue
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                token = ""
                if isinstance(obj, dict):
                    msg = obj.get("message") or {}
                    if isinstance(msg, dict):
                        token = msg.get("content") or ""
                done = bool(obj.get("done")) if isinstance(obj, dict) else False

                if token:
                    yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                if done:
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    return

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            pass
        yield f"data: {json.dumps({'type': 'error', 'message': f'Ollama HTTPError {e.code}', 'body': body}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return

    except Exception as e:
        # This is where your current error came from (Errno 101 Network unreachable)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'hint': f'Check OLLAMA_URL={OLLAMA_URL} and docker compose service ollama'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        return


@router.post("/sessions/{session_id}/messages/stream")
def stream_assistant_reply(session_id: str, payload: ChatStreamIn, db: Session = Depends(get_db)):
    """
    SSE streaming assistant response.

    Flow:
    1) Save user message
    2) Stream assistant tokens from Ollama
    3) After done, save assistant message in DB (full text)
    """
    _ensure_session(db, session_id)

    user_msg = crud.create_chat_message(db, session_id, ChatMessageCreate(role="user", content=payload.content))

    history = crud.list_chat_messages(db, session_id, limit=200, offset=0)
    messages = [{"role": m.role, "content": m.content} for m in history]

    model = (payload.model or OLLAMA_CHAT_MODEL).strip() or OLLAMA_CHAT_MODEL

    def event_gen() -> Iterator[str]:
        assistant_text_parts: list[str] = []

        if OLLAMA_DISABLED:
            fake = "OK (OLLAMA_DISABLED=1): " + payload.content
            for ch in fake:
                assistant_text_parts.append(ch)
                yield f"data: {json.dumps({'type': 'token', 'content': ch}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

            sdb = SessionLocal()
            try:
                crud.create_chat_message(sdb, session_id, ChatMessageCreate(role="assistant", content="".join(assistant_text_parts)))
            finally:
                sdb.close()
            return

        for frame in _ollama_stream(messages=messages, model=model):
            # capture tokens to persist final assistant message
            try:
                if frame.startswith("data: "):
                    obj = json.loads(frame[len("data: "):].strip())
                    if obj.get("type") == "token":
                        assistant_text_parts.append(obj.get("content", ""))
            except Exception:
                pass

            yield frame

            if '"type": "done"' in frame or '"type":"done"' in frame:
                sdb = SessionLocal()
                try:
                    crud.create_chat_message(sdb, session_id, ChatMessageCreate(role="assistant", content="".join(assistant_text_parts)))
                finally:
                    sdb.close()
                return

    return StreamingResponse(event_gen(), media_type="text/event-stream")