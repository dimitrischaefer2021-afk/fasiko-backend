"""
API‑Router für Projektquellen (Uploads).

Dieser Router stellt einen Endpunkt bereit, um Dateien (PDF, DOCX, TXT, MD) zu
einem bestehenden Projekt hochzuladen. Die Dateien werden im
``UPLOAD_DIR/<project_id>`` gespeichert. Zusätzlich wird eine einfache
Textextraktion durchgeführt, um Inhalte für spätere Analysen verfügbar zu
machen. Unterstützte Formate:

* **TXT/MD**: der gesamte Text wird aus dem Upload gelesen.
* **DOCX**: der Text wird mit ``python-docx`` extrahiert.
* **PDF**: wird gespeichert, aber die Textextraktion ist noch nicht
  implementiert (Status = ``partial``).

Für jede Datei liefert der Endpunkt einen Datensatz mit Status, optionaler
Fehlermeldung und Länge des extrahierten Textes. Metadaten werden in einem
speicherresidenten ``sources_store`` abgelegt.

Block 13 ergänzt damit den Upload‑Workflow, der in Block 12 noch fehlte.
"""

from __future__ import annotations

import os
import io
from datetime import datetime
from typing import List, Dict
from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status

from ..schemas import SourceUploadResponse
from ..settings import UPLOAD_DIR

# Optional: python-docx wird nur für DOCX benötigt. Falls es nicht vorhanden ist,
# schlägt die Extraktion fehl und der Status wird entsprechend gesetzt.
try:
    from docx import Document  # type: ignore
except Exception:
    Document = None  # type: ignore


router = APIRouter(tags=["sources"])

# In‑Memory Store für hochgeladene Quellen.
# Strukturiert als sources_store[project_id][source_id] = metadata
sources_store: Dict[str, Dict[str, Dict[str, object]]] = {}


def _extract_text_from_content(filename: str, content: bytes) -> tuple[str, str, int]:
    """Extrahiert Text aus dem Upload-Inhalt.

    Gibt ein Tupel (status, reason, text_len) zurück. Bei Erfolg ist ``status``
    ``ok`` oder ``partial`` und ``reason`` enthält None. Bei Fehlern
    ``status`` = ``error`` und ``reason`` enthält die Exception.
    """
    name = filename.lower()
    # Default: keine Extraktion
    status_str: str = "ok"
    reason: str | None = None
    extracted_text: str = ""
    if name.endswith(".txt") or name.endswith(".md"):
        try:
            extracted_text = content.decode("utf-8", errors="ignore")
        except Exception as exc:
            status_str = "error"
            reason = str(exc)
    elif name.endswith(".docx"):
        if Document is None:
            status_str = "error"
            reason = "python-docx is not installed"
        else:
            try:
                file_like = io.BytesIO(content)
                doc = Document(file_like)
                extracted_text = "\n".join(p.text for p in doc.paragraphs)
            except Exception as exc:
                status_str = "error"
                reason = str(exc)
    elif name.endswith(".pdf"):
        # PDF-Extraktion ist noch nicht implementiert. Markiere als partial.
        status_str = "partial"
        reason = "PDF extraction not implemented"
    else:
        status_str = "error"
        reason = f"Unsupported file extension for {filename}"
    text_len = len(extracted_text.strip())
    # Leerer Text gilt als partial (sofern kein Fehler)
    if status_str == "ok" and text_len == 0:
        status_str = "partial"
        reason = reason or "No text extracted"
    return status_str, reason, text_len


@router.post(
    "/projects/{project_id}/sources/upload",
    response_model=List[SourceUploadResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_project_sources(
    project_id: str,
    file: List[UploadFile] = File(
        ...,  # file parameter is required
        description=(
            "Datei(en) zum Hochladen. In der Swagger‑UI kann über 'Add item' weitere Dateien "
            "hinzugefügt werden. Beim Upload via curl können mehrere `-F file=@...` Parameter "
            "verwendet werden."
        ),
    ),
    tags: str | None = Form(
        default=None,
        description=(
            "Optionale Schlagworte, kommasepariert, die den hochgeladenen Dateien zugeordnet "
            "werden sollen. Diese werden allen Dateien gleichermaßen zugeordnet und später nicht weiter ausgewertet."
        ),
    ),
) -> List[SourceUploadResponse]:
    """Lädt Dateien für ein Projekt hoch und extrahiert ggf. Text.

    Die Dateien werden im Verzeichnis ``UPLOAD_DIR/<project_id>`` abgelegt.
    Unterstützte Formate sind TXT, MD, DOCX und PDF. PDFs werden zwar
    gespeichert, aber die Textextraktion wird derzeit nicht durchgeführt
    (Status = ``partial``).

    Parameter
    ---------
    project_id: str
        ID des Projekts, dem die Dateien zugeordnet werden sollen.
    files: List[UploadFile]
        Eine oder mehrere Dateien zum Hochladen. In der Swagger‑UI kann
        über "Add item" eine zweite, dritte usw. Datei ausgewählt
        werden. Über `curl` können mehrere ``-F``-Parameter mit demselben
        Namen ``files`` gesendet werden.
    tags: List[str] | None
        Optional: eine Liste von Schlagworten, die den hochgeladenen
        Dateien zugeordnet werden sollen. Diese werden lediglich
        gespeichert und später nicht verwendet.
    """
    # file kann eine oder mehrere UploadFile-Objekte enthalten.
    uploads: List[UploadFile] = file
    if not uploads:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

    # Parse tags string into a list if provided
    tag_list: List[str] | None = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    responses: List[SourceUploadResponse] = []
    for upload in uploads:
        source_id = str(uuid4())
        original_name = upload.filename or "unnamed"
        safe_name = f"{source_id}_{original_name}"
        project_dir = os.path.join(UPLOAD_DIR, project_id)
        os.makedirs(project_dir, exist_ok=True)
        file_path = os.path.join(project_dir, safe_name)
        content = await upload.read()
        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save file {original_name}: {exc}",
            )
        status_str, reason, text_len = _extract_text_from_content(original_name, content)
        meta = {
            "id": source_id,
            "project_id": project_id,
            "filename": original_name,
            "stored_filename": safe_name,
            "content_type": upload.content_type,
            "size_bytes": len(content),
            "status": status_str,
            "reason": reason,
            "extracted_text_len": text_len,
            "tags": tag_list,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        sources_store.setdefault(project_id, {})[source_id] = meta
        responses.append(
            SourceUploadResponse(
                id=source_id,
                filename=original_name,
                status=status_str,
                reason=reason,
                extracted_text_len=text_len,
            )
        )
    return responses