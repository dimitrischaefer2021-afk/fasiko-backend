"""
LLM-basierter Text-Normalizer für BSI-Anforderungen (Block 22).

Ziel:
- Titel/Description aus PDF-Extraktion stabil "reparieren" (Worttrennung, Leerzeichen, Zeilenumbrüche)
- KEINE inhaltliche Veränderung (keine neuen Beispiele, keine Produktvorschläge, keine Umschreibungen)
- Transparente Vorschau inkl. Flags (DEV), Persistenz in PROD

Wichtig:
- Um Halluzinationen zuverlässig abzufangen, wird die LLM-Antwort strikt validiert.
  Wenn die Antwort das vorgegebene Format nicht einhält oder inhaltlich abweicht,
  wird sie verworfen (DEV: sichtbar als llm_rejected; PROD: Job schlägt fehl).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from .db import SessionLocal
from .jobs_store import jobs_store
from .models import BsiModule, BsiRequirement
from .settings import ENV_PROFILE, MODEL_GENERAL_8B
from .llm_client import call_llm

# -----------------------------
# Heuristiken / Artefaktprüfung
# -----------------------------


_PAGE_RE = re.compile(r"\bSeite\s+\d+\s+von\s+\d+\b", re.IGNORECASE)
_HYPHEN_SPLIT_RE = re.compile(r"(?<=[A-Za-zÄÖÜäöüß])\-\s+(?=[A-Za-zÄÖÜäöüß])")
_SOFT_HYPHEN_RE = re.compile("\u00ad")
_SINGLE_LETTER_SPLIT_RE = re.compile(r"\b([A-Za-zÄÖÜäöüß])\s+([a-zäöüß]{4,})\b")

# Typische "LLM hat Inhalt erfunden"-Marker (DE/EN)
_BAD_MARKERS = [
    "here is",
    "hier ist",
    "please note",
    "in this example",
    "zum beispiel",
    "beispielsweise",
    "airwatch",
    "app annie",
    "similarweb",
    "microsoft intune",
    "android 4.3",
    "ios 8",
]


def contains_artifacts(text: Optional[str]) -> bool:
    """Erkennt typische PDF-Extraktionsartefakte."""
    if not text:
        return False

    if _SOFT_HYPHEN_RE.search(text):
        return True
    if _PAGE_RE.search(text):
        return True
    if _HYPHEN_SPLIT_RE.search(text):
        return True
    if _SINGLE_LETTER_SPLIT_RE.search(text):
        return True
    if re.search(r"[ \t]{2,}", text):
        return True

    # Zeilenumbrüche im Fließtext (außer reine Bullet-Listen)
    if "\n" in text:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        non_bullet = [ln for ln in lines if not ln.lstrip().startswith("•")]
        if len(non_bullet) >= 2:
            return True

    return False


def apply_heuristics(text: str, *, keep_bullets: bool) -> str:
    """Konservative, deterministische Heuristiken zur Artefaktentfernung.

    - Entfernt Soft-Hyphens
    - Entfernt "Seite X von Y"
    - Fix: "Sicher- heit" -> "Sicherheit" (nur wenn nach '-' ein Leerzeichen folgt)
    - Fix: "m indestens" / "E influss" -> "mindestens" / "Einfluss" (1 Buchstabe + Space + >=4)
    - Normalisiert Whitespace
    - Bullet-Format (nur keep_bullets=True): jede Aufzählung in eigener Zeile mit "• "
    """
    if not text:
        return text

    out = text

    # Einheitliche Line-Endings
    out = out.replace("\r\n", "\n").replace("\r", "\n")

    # Soft hyphen entfernen
    out = _SOFT_HYPHEN_RE.sub("", out)

    # Seitenmarker entfernen
    out = _PAGE_RE.sub("", out)

    # Bindestrich-Splits reparieren: "- " innerhalb eines Wortes entfernen
    out = _HYPHEN_SPLIT_RE.sub("", out)

    # Single-letter-Splits reparieren (nur sehr spezifisch)
    out = _SINGLE_LETTER_SPLIT_RE.sub(r"\1\2", out)

    if keep_bullets:
        # Bullet-Token normieren (auch wenn Bullet im Fließtext hängt)
        out = re.sub(r"[ \t]*\n?[ \t]*•[ \t]*", "\n• ", out)

        # Bullet-Newlines konservieren, andere Newlines in Spaces umwandeln
        out = out.replace("\n• ", "\n__BULLET__")
        out = out.replace("\n", " ")
        out = out.replace("__BULLET__", "\n• ")

    else:
        # Titel: keine Bullets, keine Newlines
        out = out.replace("•", " ")
        out = out.replace("\n", " ")

    # Whitespace normalisieren
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+\n", "\n", out)
    out = re.sub(r"\n\s+", "\n", out)
    out = out.strip()

    return out


# -----------------------------
# LLM-Validierung / Normalizing
# -----------------------------


_SYSTEM_PROMPT = (
    "Du bist ein Textkorrektor. Du darfst ausschließlich Worttrennung, "
    "Leerzeichen, Silbentrennung und Formatierung korrigieren. "
    "Du darfst KEINEN Inhalt verändern, KEINE Beispiele ergänzen, "
    "KEINE Tools/Produkte nennen und KEINE neuen Sätze hinzufügen. "
    "Erhalte Fachbegriffe, Codes und Norm-Begriffe (MUSS/SOLL/SOLLTE/DARF) unverändert.\n"
    "\n"
    "Gib DEINE Antwort strikt in genau diesem Format zurück (ohne zusätzliche Zeilen davor/danach):\n"
    "<TITLE>\n"
    "...\n"
    "</TITLE>\n"
    "<DESCRIPTION>\n"
    "...\n"
    "</DESCRIPTION>"
)


def _count_norm_keywords(s: str) -> Dict[str, int]:
    keys = ["MUSS", "SOLLTE", "SOLL", "DARF", "DÜRFEN", "MÜSSEN", "SOLLEN"]
    up = s.upper()
    return {k: up.count(k) for k in keys}


def _new_word_ratio(raw: str, out: str) -> float:
    # alphabetische Wörter >=4 Zeichen; sehr grobe Heuristik gegen Erfindungen
    raw_words = set(re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", raw.lower()))
    out_words = set(re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", out.lower()))
    if not out_words:
        return 0.0
    new_words = out_words - raw_words
    return len(new_words) / max(len(out_words), 1)


def _looks_like_wrong_answer(raw_title: str, raw_desc: str, cand_title: str, cand_desc: str) -> Tuple[bool, str]:
    low = (cand_title + "\n" + cand_desc).lower()

    for m in _BAD_MARKERS:
        if m in low:
            return True, f"bad_marker:{m}"

    # Bullet-Erfindung: mehr Bullets als vorher
    if (cand_title + cand_desc).count("•") > (raw_title + raw_desc).count("•") + 1:
        return True, "bullets_increased"

    # Norm-Schlüsselwörter dürfen nicht verschwinden/auftauchen
    raw_counts = _count_norm_keywords(raw_desc)
    out_counts = _count_norm_keywords(cand_desc)
    if raw_counts != out_counts:
        return True, "norm_keywords_changed"

    # Neue Wörter zu viele -> vermutlich Halluzination
    ratio = _new_word_ratio(raw_desc, cand_desc)
    if len(raw_desc) >= 120 and ratio > 0.25:
        return True, f"too_many_new_words:{ratio:.2f}"

    # Unzulässige Meta-Antworten am Anfang
    if low.strip().startswith(("here", "hier", "note:", "korrekturen")):
        return True, "meta_prefix"

    return False, ""


def _parse_tagged_output(out: str) -> Optional[Tuple[str, str]]:
    m = re.search(r"<TITLE>\s*(.*?)\s*</TITLE>\s*<DESCRIPTION>\s*(.*?)\s*</DESCRIPTION>\s*$", out, re.DOTALL)
    if not m:
        return None
    title = m.group(1).strip()
    desc = m.group(2).strip()
    return title, desc


async def _llm_normalize_pair(raw_title: str, raw_desc: str) -> Tuple[str, str, bool, bool, bool, Optional[str]]:
    """LLM-Normalisierung (ein Call pro Requirement) mit strikter Validierung."""
    if not raw_title and not raw_desc:
        return raw_title, raw_desc, False, False, False, None

    user_content = (
        "Titel (Original):\n"
        "<<<\n"
        f"{raw_title}\n"
        ">>>\n\n"
        "Beschreibung (Original):\n"
        "<<<\n"
        f"{raw_desc}\n"
        ">>>"
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        out = await call_llm(messages=messages, model=MODEL_GENERAL_8B)
    except Exception as exc:
        # Endpoint / Timeout / etc.
        return raw_title, raw_desc, False, False, False, f"llm_error:{exc}"

    # LLM geantwortet
    llm_used = True

    # Leere Antwort = "keine Änderungen"
    if out == "":
        return raw_title, raw_desc, True, False, False, None

    parsed = _parse_tagged_output(out)
    if not parsed:
        return raw_title, raw_desc, True, False, True, "unparseable_output"

    cand_title, cand_desc = parsed

    # Kandidaten dürfen nicht leer werden
    cand_title = cand_title or raw_title
    cand_desc = cand_desc or raw_desc

    bad, reason = _looks_like_wrong_answer(raw_title, raw_desc, cand_title, cand_desc)
    if bad:
        return raw_title, raw_desc, True, False, True, reason

    llm_changed = (cand_title.strip() != (raw_title or "").strip()) or (cand_desc.strip() != (raw_desc or "").strip())
    return cand_title, cand_desc, llm_used, llm_changed, False, None


# -----------------------------
# Public API: Preview + Job
# -----------------------------


async def normalize_requirement_preview(req: BsiRequirement) -> Dict[str, Any]:
    """Normalisiert eine einzelne Anforderung für die Vorschau."""
    raw_title = req.raw_title or req.title or ""
    raw_desc = req.raw_description or req.description or ""

    llm_title, llm_desc, llm_used, llm_changed, llm_rejected, reject_reason = await _llm_normalize_pair(
        raw_title, raw_desc
    )

    final_title = apply_heuristics(llm_title, keep_bullets=False)
    final_desc = apply_heuristics(llm_desc, keep_bullets=True)

    flags: Dict[str, Any] = {
        "llm_used": llm_used,
        "llm_changed": llm_changed,
        "llm_rejected": llm_rejected,
        "llm_reject_reason": reject_reason,
        "heuristic_used": True,
        "artifact_before": contains_artifacts(raw_title) or contains_artifacts(raw_desc),
        "artifact_after": contains_artifacts(final_title) or contains_artifacts(final_desc),
    }

    return {
        "id": req.id,
        "req_id": req.req_id,
        "raw_title": raw_title,
        "raw_description": raw_desc,
        "llm_title": llm_title,
        "llm_description": llm_desc,
        "final_title": final_title,
        "final_description": final_desc,
        "flags": flags,
    }


async def run_normalize_job(job_id: str, catalog_id: str, module_code: Optional[str] = None) -> None:
    """Führt einen Normalisierungsjob aus (DEV: Preview, PROD: Persistenz)."""
    job = jobs_store.get(job_id)
    if not job:
        return

    job.status = "running"
    job.error = None
    job.progress = 0.0

    db: Session = SessionLocal()
    try:
        # Module des Katalogs laden
        q = db.query(BsiModule).filter(BsiModule.catalog_id == catalog_id)
        if module_code:
            q = q.filter(BsiModule.code == module_code)
        modules: Iterable[BsiModule] = q.all()

        # Anforderungen sammeln
        requirements: List[BsiRequirement] = []
        for mod in modules:
            reqs = (
                db.query(BsiRequirement)
                .filter(BsiRequirement.module_id == mod.id)
                .order_by(BsiRequirement.req_id)
                .all()
            )
            requirements.extend(reqs)

        total = len(requirements)
        if total == 0:
            job.result_data = {
                "requirements": [],
                "summary": {
                    "total": 0,
                    "llm_used_count": 0,
                    "llm_changed_count": 0,
                    "heuristic_used_count": 0,
                    "artifact_remaining_count": 0,
                },
            }
            job.status = "completed"
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            return

        # DEV: keine Persistenz, aber volle Preview
        if ENV_PROFILE != "prod":
            result_reqs: List[Dict[str, Any]] = []
            llm_used_count = 0
            llm_changed_count = 0
            heuristic_used_count = 0
            artifact_remaining_count = 0

            for idx, req in enumerate(requirements):
                preview = await normalize_requirement_preview(req)
                result_reqs.append(preview)

                flags = preview.get("flags", {})
                if flags.get("llm_used"):
                    llm_used_count += 1
                if flags.get("llm_changed"):
                    llm_changed_count += 1
                if flags.get("heuristic_used"):
                    heuristic_used_count += 1
                if flags.get("artifact_after"):
                    artifact_remaining_count += 1

                job.progress = (idx + 1) / total

            job.result_data = {
                "requirements": result_reqs,
                "summary": {
                    "total": total,
                    "llm_used_count": llm_used_count,
                    "llm_changed_count": llm_changed_count,
                    "heuristic_used_count": heuristic_used_count,
                    "artifact_remaining_count": artifact_remaining_count,
                },
            }
            job.status = "completed"
            job.progress = 1.0
            job.completed_at = datetime.utcnow()
            if artifact_remaining_count > 0:
                job.error = (
                    f"WARN: Normalization incomplete for {artifact_remaining_count}/{total} requirements; "
                    f"Artefakte verbleiben."
                )
            return

        # PROD: Persistenz (strikter)
        for idx, req in enumerate(requirements):
            preview = await normalize_requirement_preview(req)
            flags = preview.get("flags", {})

            # In PROD: wenn LLM nicht erreichbar oder Antwort verworfen -> FAIL (sonst riskant)
            if not flags.get("llm_used"):
                job.status = "failed"
                job.error = "LLM nicht erreichbar (llm_used=false)."
                job.progress = idx / total
                job.completed_at = datetime.utcnow()
                db.commit()
                return
            if flags.get("llm_rejected"):
                job.status = "failed"
                job.error = f"LLM-Antwort ungültig: {flags.get('llm_reject_reason')}"
                job.progress = idx / total
                job.completed_at = datetime.utcnow()
                db.commit()
                return

            # Rohdaten nur einmalig setzen
            if req.raw_title is None:
                req.raw_title = req.title
            if req.raw_description is None:
                req.raw_description = req.description

            req.title = preview["final_title"]
            req.description = preview["final_description"]
            db.add(req)

            if (idx + 1) % 20 == 0:
                db.commit()

            job.progress = (idx + 1) / total

        db.commit()
        job.status = "completed"
        job.progress = 1.0
        job.completed_at = datetime.utcnow()

    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.progress = 0.0
        job.completed_at = datetime.utcnow()
    finally:
        try:
            db.close()
        except Exception:
            pass
