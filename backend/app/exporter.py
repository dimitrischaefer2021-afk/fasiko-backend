"""
Export-Funktionen für Jobs.

Block 09:
- Exportiert echte Artefakt-Inhalte aus der DB in Dateien (txt/md/docx/pdf)
- Packt die Dateien in ein ZIP-Archiv
- Zip-Slip Schutz: nur Basename als arcname

Wichtig:
- DOCX/PDF Rendering ist bewusst schlicht (MVP), aber stabil.
- Keine externen Binaries, Multi-Arch kompatibel.
"""

from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Artifact, ArtifactVersion
from .settings import EXPORT_DIR

# Optional dependencies (Block 09)
from docx import Document  # type: ignore
from reportlab.lib.pagesizes import A4  # type: ignore
from reportlab.pdfgen import canvas  # type: ignore


@dataclass(frozen=True)
class ExportItem:
    artifact_id: str
    filename_base: str
    content_md: str


def _safe_filename(name: str) -> str:
    """
    Prevent Zip-Slip and weird filenames.
    Keeps only safe chars and trims length.
    """
    s = name.strip()
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", s)
    s = s.strip("._-")
    return s[:120] if s else "artifact"


def _load_artifacts_current(db: Session, artifact_ids: List[str]) -> List[ExportItem]:
    items: List[ExportItem] = []
    if not artifact_ids:
        return items

    # fetch artifacts
    arts = db.execute(select(Artifact).where(Artifact.id.in_(artifact_ids))).scalars().all()
    art_by_id = {a.id: a for a in arts}

    for aid in artifact_ids:
        art = art_by_id.get(aid)
        if not art:
            # If artifact id does not exist: export placeholder entry but keep job successful
            items.append(
                ExportItem(
                    artifact_id=aid,
                    filename_base=_safe_filename(aid),
                    content_md=f"# Fehlender Datensatz\n\nArtefakt {aid} wurde nicht gefunden.\n",
                )
            )
            continue

        # current version content
        v = db.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == art.id)
            .where(ArtifactVersion.version == art.current_version)
        ).scalars().first()

        content = v.content_md if v else ""
        base = _safe_filename(f"{art.type}_{art.title}") if getattr(art, "title", None) else _safe_filename(art.type)
        items.append(ExportItem(artifact_id=aid, filename_base=base, content_md=content or ""))

    return items


def _write_txt(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_md(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_docx(path: Path, content_md: str) -> None:
    """
    Very simple Markdown -> DOCX:
    - #, ##, ### headings
    - list items starting with '-', '*'
    - else paragraph
    """
    doc = Document()
    for raw in content_md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=1)
        elif line.lstrip().startswith(("- ", "* ")):
            doc.add_paragraph(line.lstrip()[2:].strip(), style="List Bullet")
        else:
            doc.add_paragraph(line)
    doc.save(str(path))


def _write_pdf(path: Path, content_md: str) -> None:
    """
    Very simple Markdown -> PDF:
    - removes markdown markers and prints lines.
    """
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 50
    line_height = 14

    def new_page():
        nonlocal y
        c.showPage()
        y = height - 50

    for raw in content_md.splitlines():
        line = raw.rstrip()
        # strip some markdown
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^\s*[-*]\s+", "• ", line)
        if not line.strip():
            y -= line_height
            if y < 50:
                new_page()
            continue

        # very naive wrap
        max_chars = 110
        while len(line) > max_chars:
            part = line[:max_chars]
            c.drawString(50, y, part)
            y -= line_height
            if y < 50:
                new_page()
            line = line[max_chars:]
        c.drawString(50, y, line)
        y -= line_height
        if y < 50:
            new_page()

    c.save()


def export_artifacts_to_zip(
    db: Session,
    artifact_ids: List[str],
    export_format: str,
    job_id: str,
) -> Tuple[str, str]:
    """
    Exports artifacts into files and zips them.
    Returns (zip_filename, zip_abs_path)
    """
    fmt = (export_format or "md").lower().strip()
    if fmt not in {"txt", "md", "docx", "pdf"}:
        fmt = "md"

    base_dir = Path(EXPORT_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)

    tmp_dir = base_dir / f"tmp_{job_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    items = _load_artifacts_current(db, artifact_ids)

    # if empty, still create a zip with a note
    if not items:
        note = tmp_dir / "README.txt"
        _write_txt(note, "Kein Export-Inhalt: artifact_ids war leer.\n")

    for it in items:
        out_path = tmp_dir / f"{it.filename_base}.{fmt}"
        if fmt == "txt":
            _write_txt(out_path, it.content_md)
        elif fmt == "md":
            _write_md(out_path, it.content_md)
        elif fmt == "docx":
            _write_docx(out_path, it.content_md)
        elif fmt == "pdf":
            _write_pdf(out_path, it.content_md)

    zip_filename = f"{job_id}.zip"
    zip_path = base_dir / zip_filename

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in tmp_dir.iterdir():
            if not p.is_file():
                continue
            # Zip-Slip safe: arcname = basename
            zf.write(p, arcname=p.name)

    # cleanup tmp dir
    for p in tmp_dir.iterdir():
        try:
            p.unlink()
        except Exception:
            pass
    try:
        tmp_dir.rmdir()
    except Exception:
        pass

    return zip_filename, str(zip_path)