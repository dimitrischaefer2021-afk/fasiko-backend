"""
    Generator‑Modul für FaSiKo‑Artefakte.

    Dieses Modul kapselt die Logik zur Erstellung von ersten
    FaSiKo‑Dokumenten mithilfe eines LLM über den Ollama‑Server.
    Für jeden Artefakt‑Typ wird ein eigener Prompt definiert. Fehlen
    Informationen in den vorhandenen Quellen, soll das LLM konkrete
    Fragen stellen. Diese Fragen werden als offene Punkte erkannt und
    in der Datenbank gespeichert.

    Die LLM‑Anbindung erfolgt über das HTTP‑Interface von Ollama
    (`/api/chat`). Wenn das 70B‑Modell nicht erreichbar ist, wird in
    Entwicklungsumgebungen automatisch auf das 8B‑Modell zurückgefallen.
    In Produktionsumgebungen wird ein statisches Skelett genutzt.
    """

from __future__ import annotations

from typing import Dict, List, Tuple
import httpx

from .settings import (
    OLLAMA_URL,
    MODEL_FASIKO_CREATE_70B,
    MODEL_GENERAL_8B,
    ENV_PROFILE,
)

# Prompt‑Vorlagen für alle Artefakt‑Typen
PROMPT_TEMPLATES: Dict[str, str] = {
    "strukturanalyse": (
        "Erstelle eine Strukturanalyse für das IT‑Grundschutz‑Sicherheitskonzept. "
        "Nutze vorhandene Dokumente soweit möglich. Jede fehlende Information "
        "soll als offene Frage im Format 'OFFENE_FRAGE: Kategorie; Frage' "
        "aufgeführt werden. Der restliche Inhalt soll klar strukturiert in "
        "Markdown dargestellt werden."
    ),
    "schutzbedarf": (
        "Führe eine Schutzbedarfsfeststellung gemäß IT‑Grundschutz durch. "
        "Bestimme für die relevanten Geschäftsprozesse, Anwendungen und IT‑Systeme "
        "den Schutzbedarf (normal, hoch, sehr hoch). Fehlende Angaben sind als "
        "offene Fragen mit 'OFFENE_FRAGE: Kategorie; Frage' zu formulieren."
    ),
    "modellierung": (
        "Modelliere die Zielobjekte (Anwendungen, Server, Endgeräte, Netzsegmente) "
        "und ihre Beziehungen. Zeige die Modellierung als Text mit Überschriften "
        "(z. B. Geschäftsprozesse, IT‑Systeme, Anwendungen). Fehlende Informationen "
        "sollen als offene Fragen ausgewiesen werden."
    ),
    "grundschutz_check": (
        "Führe einen Soll‑Ist‑Vergleich der ausgewählten BSI‑Grundschutz‑Bausteine "
        "durch. Liste die Anforderungen und bewerte den Umsetzungsgrad. Fehlen Angaben, "
        "notiere sie als offene Fragen."
    ),
    "risikoanalyse": (
        "Erstelle eine Risikoanalyse (nach BSI 200‑3) basierend auf den identifizierten "
        "Gefährdungen und dem Schutzbedarf. Offene Punkte sollen als Fragen ausgewiesen werden."
    ),
    "maßnahmenplan": (
        "Erstelle einen Maßnahmen‑/Umsetzungsplan. Für jede Anforderung, die noch nicht "
        "vollständig umgesetzt ist, sollen Maßnahmen formuliert werden. Fehlende Details "
        "werden als offene Fragen notiert."
    ),
    "sicherheitskonzept": (
        "Erstelle ein übergreifendes Sicherheitskonzept, das die Ergebnisse von "
        "Strukturanalyse, Schutzbedarfsfeststellung, Modellierung, Grundschutz‑Check, "
        "Risikoanalyse und Maßnahmenplan zusammenführt. Unbekannte Punkte sollen als "
        "offene Fragen aufgeführt werden."
    ),
}

# Fallback‑Skelette, falls das LLM nicht verfügbar ist
DEFAULT_TEMPLATES: Dict[str, str] = {
    "strukturanalyse": "# Strukturanalyse\n\nBeschreibe hier die Struktur des Informationsverbunds.\n",
    "schutzbedarf": "# Schutzbedarfsfeststellung\n\nErörtere hier den Schutzbedarf für die betrachteten Objekte.\n",
    "modellierung": "# Modellierung\n\nStelle hier die Zielobjekte und ihre Beziehungen dar.\n",
    "grundschutz_check": "# IT‑Grundschutz‑Check\n\nUntersuche hier die Anforderungen der relevanten Bausteine und den Ist‑Stand.\n",
    "risikoanalyse": "# Risikoanalyse\n\nBewerte hier die Risiken basierend auf Gefährdungen und Schutzbedarf.\n",
    "maßnahmenplan": "# Maßnahmen‑/Umsetzungsplan\n\nLege hier Maßnahmen fest, um identifizierte Lücken zu schließen.\n",
    "sicherheitskonzept": "# Sicherheitskonzept\n\nFasse hier alle Ergebnisse in einem konsistenten Sicherheitskonzept zusammen.\n",
}


async def _call_ollama_chat(messages: List[dict], model: str) -> str:
    """Sendet die Nachrichten an Ollama und liefert den Antworttext."""
    url = f"{OLLAMA_URL}/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message") or {}
        return message.get("content") or ""


def _build_prompt(artifact_type: str, project_name: str) -> str:
    base = PROMPT_TEMPLATES.get(artifact_type, "")
    return (
        f"Du bist ein Assistent, der bei der Erstellung von IT‑Grundschutz‑"
        f"Dokumenten hilft. Projektname: {project_name}. {base}"
    )


async def generate_artifact_content(
    artifact_type: str, project_name: str
) -> Tuple[str, List[dict]]:
    """
    Erzeugt den Inhalt für ein FaSiKo‑Artefakt und eine Liste offener Fragen.
    """
    prompt = _build_prompt(artifact_type, project_name)
    messages = [{"role": "user", "content": prompt}]
    content: str
    # Primär das 70B‑Modell verwenden
    try:
        content = await _call_ollama_chat(messages, MODEL_FASIKO_CREATE_70B)
    except Exception:
        # Fallback-Strategie: In Entwicklung (ENV_PROFILE != "prod") auf 8B‑Modell wechseln
        if ENV_PROFILE != "prod":
            try:
                content = await _call_ollama_chat(messages, MODEL_GENERAL_8B)
            except Exception:
                content = DEFAULT_TEMPLATES.get(artifact_type, "")
        else:
            # In Produktion direkt auf statisches Skelett zurückfallen
            content = DEFAULT_TEMPLATES.get(artifact_type, "")

    open_points: List[dict] = []
    lines: List[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("OFFENE_FRAGE:"):
            rest = stripped[len("OFFENE_FRAGE:"):].strip()
            category, question = None, None
            if ";" in rest:
                cat_part, ques_part = rest.split(";", 1)
                category = cat_part.strip() or None
                question = ques_part.strip() or None
            else:
                question = rest or None
            if question:
                open_points.append({"category": category, "question": question})
        else:
            lines.append(line)

    content_md = "\n".join(lines).strip() or DEFAULT_TEMPLATES.get(artifact_type, "")
    return content_md, open_points