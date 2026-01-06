"""
Speicherfunktionen für Uploads und Anhänge.

Dieses Modul kapselt das Speichern und Löschen von hochgeladenen Dateien auf
dem Dateisystem. Unterstützte Dateitypen sind PDF, DOCX und TXT. Die
Verzeichnisstruktur wird anhand der Projekt‑ID und Quelle/OpenPoint
organisiert. Es gibt zudem Hilfsfunktionen zum Parsen und Serialisieren von
Tags.
"""

import json
from pathlib import Path

from fastapi import UploadFile

from .settings import UPLOAD_DIR, OPENPOINT_DIR, CHAT_DIR, MAX_UPLOAD_BYTES


# Erlaubte Dateierweiterungen
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1].strip()
    return name if name else "upload.bin"


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def ensure_allowed(file: UploadFile) -> None:
    filename = _safe_filename(file.filename or "")
    ext = _ext(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension: {ext}")


def project_source_dir(project_id: str, source_id: str) -> Path:
    base = Path(UPLOAD_DIR)
    return base / project_id / source_id


def openpoint_evidence_dir(project_id: str, open_point_id: str) -> Path:
    base = Path(OPENPOINT_DIR)
    return base / project_id / open_point_id


def _save_upload_generic(target_dir: Path, file: UploadFile) -> tuple[str, int, str, str]:
    ensure_allowed(file)
    filename = _safe_filename(file.filename or "")
    content_type = (file.content_type or "application/octet-stream").strip()
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
                raise ValueError(f"File too large. Max is {MAX_UPLOAD_BYTES} bytes.")
            out.write(chunk)
    return (str(target_path), size, filename, content_type)


def save_source_upload_to_disk(project_id: str, source_id: str, file: UploadFile) -> tuple[str, int, str, str]:
    return _save_upload_generic(project_source_dir(project_id, source_id), file)


def save_openpoint_attachment_to_disk(project_id: str, open_point_id: str, attachment_id: str, file: UploadFile) -> tuple[str, int, str, str]:
    target_dir = openpoint_evidence_dir(project_id, open_point_id) / attachment_id
    return _save_upload_generic(target_dir, file)


def delete_dir_recursively(dir_path: Path) -> None:
    if not dir_path.exists():
        return
    for p in sorted(dir_path.rglob("*"), reverse=True):
        if p.is_file():
            try:
                p.unlink()
            except Exception:
                pass
        else:
            try:
                p.rmdir()
            except Exception:
                pass
    try:
        dir_path.rmdir()
    except Exception:
        pass


def delete_source_files(project_id: str, source_id: str) -> None:
    delete_dir_recursively(project_source_dir(project_id, source_id))


def delete_openpoint_attachment_files(project_id: str, open_point_id: str, attachment_id: str) -> None:
    delete_dir_recursively(openpoint_evidence_dir(project_id, open_point_id) / attachment_id)

# ---------------------------------------------------------------------------
# Chat‑Attachments
# ---------------------------------------------------------------------------

def chat_session_dir(session_id: str) -> Path:
    """Basispfad für ein Chat‑Session‑Verzeichnis.

    Anhänge werden unterhalb von CHAT_DIR in einer Struktur session_id/message_id/attachment_id gespeichert.
    """
    base = Path(CHAT_DIR)
    return base / session_id


def chat_message_dir(session_id: str, message_id: str) -> Path:
    """Ordner für eine Nachricht innerhalb einer Chat‑Session."""
    return chat_session_dir(session_id) / message_id


def save_chat_attachment_to_disk(
    session_id: str,
    message_id: str,
    attachment_id: str,
    file: UploadFile,
) -> tuple[str, int, str, str]:
    """
    Speichert einen Anhang zu einer Chat‑Nachricht auf dem Dateisystem.

    :returns: Tuple aus (Speicherpfad, Dateigröße in Bytes, Dateiname, Content‑Type)
    """
    target_dir = chat_message_dir(session_id, message_id) / attachment_id
    return _save_upload_generic(target_dir, file)


def delete_chat_attachment_files(session_id: str, message_id: str, attachment_id: str) -> None:
    """Löscht die auf dem Dateisystem abgelegten Daten für einen Chat‑Anhang."""
    delete_dir_recursively(chat_message_dir(session_id, message_id) / attachment_id)


def parse_tags(tags: str | None) -> list[str]:
    if not tags:
        return []
    t = tags.strip()
    if not t:
        return []
    if t.startswith("["):
        try:
            data = json.loads(t)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass
    return [x.strip() for x in t.split(",") if x.strip()]


def tags_to_json(tags: list[str]) -> str:
    seen = set()
    out: list[str] = []
    for x in tags:
        s = str(x).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return json.dumps(out, ensure_ascii=False)