"""
Generator‑Modul für FaSiKo‑Artefakte (verbesserte Version).

Dieses Modul kapselt die Logik zur Erstellung von ersten
FaSiKo‑Dokumenten mithilfe eines LLM über den Ollama‑Server.
Für jeden Artefakt‑Typ wird ein eigener Prompt definiert, der
konkret beschreibt, welche Abschnitte und Informationen erwartet
werden. Fehlende Informationen sollen als offene Fragen im Format
``OFFENE_FRAGE: Kategorie; Frage`` ausgegeben werden. Offene
Fragen werden an anderer Stelle in der Anwendung als „Open Points“
erfasst.

Die LLM‑Anbindung erfolgt über das HTTP‑Interface von Ollama
(``/api/chat``). Bei einem Fehler mit dem großen 70B‑Modell wird
in Entwicklungsumgebungen automatisch auf das kleinere 8B‑Modell
zurückgegriffen. In Produktionsumgebungen wird bei einem Fehler
ein statischer Skelett‑Text verwendet.

Block 10: Die Prompt‑Vorlagen wurden überarbeitet, um generische
Halluzinationen zu vermeiden und eine klare Struktur in den
Dokumenten zu erzwingen. So enthält die Schutzbedarfsfeststellung
zum Beispiel definierte Abschnitte für Geschäftsprozesse,
Anwendungen und IT‑Systeme.
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


# Präzise Prompt‑Vorlagen für alle Artefakt‑Typen. Jeder Prompt
# definiert die erwartete Struktur des Dokuments. Generische
# Einleitungen sollen vermieden werden; das LLM soll direkt mit
# dem relevanten Inhalt beginnen. Fehlende Daten werden als offene
# Fragen markiert.
PROMPT_TEMPLATES: Dict[str, str] = {
    "strukturanalyse": (
        "Erstelle eine Strukturanalyse für das IT‑Grundschutz‑Sicherheitskonzept. "
        "Nutze vorhandene Dokumente soweit möglich. Jede fehlende Information "
        "soll als offene Frage im Format 'OFFENE_FRAGE: Kategorie; Frage' "
        "aufgeführt werden. Der restliche Inhalt soll klar strukturiert in Markdown "
        "dargestellt werden."
    ),
    "schutzbedarf": (
        "Erstelle eine Schutzbedarfsfeststellung gemäß IT‑Grundschutz. "
        "Gliedere das Dokument in die Abschnitte Geschäftsprozesse, Anwendungen und IT‑Systeme. "
        "Für jeden Abschnitt nenne relevante Beispiele und ordne den Schutzbedarf (normal, hoch, sehr hoch) zu. "
        "Nutze klare Überschriften (##) und nummerierte Listen (1., 2., ...) sowie Aufzählungen. "
        "Vermeide einleitende Kommentare; beginne direkt mit der Schutzbedarfsfeststellung. "
        "Fehlende Informationen gib als offene Fragen im Format 'OFFENE_FRAGE: Kategorie; Frage' an."
    ),
    # Alias für Schutzbedarfsfeststellung. Einige API-Clients verwenden den
    # Typ "schutzbedarfsfeststellung" anstelle von "schutzbedarf". Beide
    # sollen denselben Prompt verwenden.
    "schutzbedarfsfeststellung": (
        "Erstelle eine Schutzbedarfsfeststellung gemäß IT‑Grundschutz. "
        "Gliedere das Dokument in die Abschnitte Geschäftsprozesse, Anwendungen und IT‑Systeme. "
        "Für jeden Abschnitt nenne relevante Beispiele und ordne den Schutzbedarf (normal, hoch, sehr hoch) zu. "
        "Nutze klare Überschriften (##) und nummerierte Listen (1., 2., ...) sowie Aufzählungen. "
        "Vermeide einleitende Kommentare; beginne direkt mit der Schutzbedarfsfeststellung. "
        "Fehlende Informationen gib als offene Fragen im Format 'OFFENE_FRAGE: Kategorie; Frage' an."
    ),
    "modellierung": (
        "Modelliere die Zielobjekte (Anwendungen, Server, Endgeräte, Netzsegmente) und ihre Beziehungen. "
        "Die Modellierung soll in übersichtlichen Abschnitten erfolgen: ## Geschäftsprozesse, ## IT‑Systeme, ## Anwendungen, "
        "## Netzsegmente. Beschreibe stichpunktartig die jeweiligen Elemente und ihre Beziehungen. "
        "Fehlende Informationen sollen als offene Fragen ausgewiesen werden."
    ),
    "grundschutz_check": (
        "Führe einen Soll‑Ist‑Vergleich der ausgewählten BSI‑Grundschutz‑Bausteine durch. "
        "Erstelle eine Tabelle in Markdown oder eine geordnete Liste, in der jede Anforderung, der Ist‑Stand und "
        "ggf. offene Fragen aufgeführt werden. Fehlende Angaben sind als offene Fragen im genannten Format zu formulieren."
    ),
    "risikoanalyse": (
        "Erstelle eine Risikoanalyse (nach BSI 200‑3) basierend auf den identifizierten Gefährdungen und dem Schutzbedarf. "
        "Gliedere sie in die Schritte Risikoidentifikation, Risikobewertung und Risikobehandlung. "
        "Nutze Listen und Abschnitte, um die Analyse übersichtlich zu gestalten. Unbekannte Punkte sollen als offene Fragen ausgewiesen werden."
    ),
    "maßnahmenplan": (
        "Erstelle einen Maßnahmen‑/Umsetzungsplan. Für jede Anforderung, die noch nicht vollständig umgesetzt ist, sollen "
        "konkrete Maßnahmen formuliert werden. Strukturiere den Plan nach Priorität oder Zeitrahmen und nutze Aufzählungen. "
        "Fehlende Details werden als offene Fragen notiert."
    ),
    "sicherheitskonzept": (
        "Erstelle ein übergreifendes Sicherheitskonzept, das die Ergebnisse von Strukturanalyse, Schutzbedarfsfeststellung, "
        "Modellierung, Grundschutz‑Check, Risikoanalyse und Maßnahmenplan zusammenführt. Beginne direkt mit einer Einleitung "
        "über den Zweck des Konzepts und gliedere den Inhalt in die genannten Unterkapitel. Unbekannte Punkte sollen als offene "
        "Fragen aufgeführt werden."
    ),
}

# Fallback‑Skelette, falls das LLM nicht verfügbar ist
DEFAULT_TEMPLATES: Dict[str, str] = {
    "strukturanalyse": "# Strukturanalyse\n\nBeschreibe hier die Struktur des Informationsverbunds.\n",
    "schutzbedarf": (
        "# Schutzbedarfsfeststellung\n\n"
        "## Geschäftsprozesse\n\n"
        "1. Beispielprozess\n\n"
        "   - Schutzbedarf: normal\n"
        "   - OFFENE_FRAGE: Geschäftsprozesse; Beschreibe den Schutzbedarf für die wichtigsten Geschäftsprozesse.\n\n"
        "## Anwendungen\n\n"
        "1. Beispielanwendung\n\n"
        "   - Schutzbedarf: normal\n"
        "   - OFFENE_FRAGE: Anwendungen; Welche Anwendungen sind kritisch und welchen Schutzbedarf haben sie?\n\n"
        "## IT‑Systeme\n\n"
        "1. Beispielsystem\n\n"
        "   - Schutzbedarf: normal\n"
        "   - OFFENE_FRAGE: IT‑Systeme; Welche IT‑Systeme werden eingesetzt und wie ist ihr Schutzbedarf?\n"
    ),
    # Alias-Fallback für Schutzbedarfsfeststellung
    "schutzbedarfsfeststellung": (
        "# Schutzbedarfsfeststellung\n\n"
        "## Geschäftsprozesse\n\n"
        "1. Beispielprozess\n\n"
        "   - Schutzbedarf: normal\n"
        "   - OFFENE_FRAGE: Geschäftsprozesse; Beschreibe den Schutzbedarf für die wichtigsten Geschäftsprozesse.\n\n"
        "## Anwendungen\n\n"
        "1. Beispielanwendung\n\n"
        "   - Schutzbedarf: normal\n"
        "   - OFFENE_FRAGE: Anwendungen; Welche Anwendungen sind kritisch und welchen Schutzbedarf haben sie?\n\n"
        "## IT‑Systeme\n\n"
        "1. Beispielsystem\n\n"
        "   - Schutzbedarf: normal\n"
        "   - OFFENE_FRAGE: IT‑Systeme; Welche IT‑Systeme werden eingesetzt und wie ist ihr Schutzbedarf?\n"
    ),
    "modellierung": "# Modellierung\n\nStelle hier die Zielobjekte und ihre Beziehungen dar.\n",
    "grundschutz_check": "# IT‑Grundschutz‑Check\n\nUntersuche hier die Anforderungen der relevanten Bausteine und den Ist‑Stand.\n",
    "risikoanalyse": "# Risikoanalyse\n\nBewerte hier die Risiken basierend auf Gefährdungen und Schutzbedarf.\n",
    "maßnahmenplan": "# Maßnahmen‑/Umsetzungsplan\n\nLege hier Maßnahmen fest, um identifizierte Lücken zu schließen.\n",
    "sicherheitskonzept": "# Sicherheitskonzept\n\nFasse hier alle Ergebnisse in einem konsistenten Sicherheitskonzept zusammen.\n",
}

# Statische Vorlagen für alle FaSiKo‑Artefakte.
#
# Einige Nutzer wünschen ein festes Layout ohne KI‑Generierung. Diese
# Vorlagen definieren die grundlegende Struktur der Dokumente und
# enthalten Beispielpunkte sowie offene Fragen. Wenn für einen
# artifact_type eine statische Vorlage existiert, wird diese beim
# Generieren verwendet und das LLM übersprungen.
STATIC_TEMPLATES: Dict[str, str] = {
    "strukturanalyse": (
        "# Strukturanalyse\n\n"
        "## Informationsverbund\n\n"
        "1. Zielobjekte\n\n"
        "   - OFFENE_FRAGE: Struktur; Beschreibe die Zielobjekte des Informationsverbunds.\n\n"
        "## Beziehungen und Schnittstellen\n\n"
        "1. Beziehungen\n\n"
        "   - OFFENE_FRAGE: Struktur; Beschreibe die Beziehungen zwischen den Zielobjekten.\n\n"
        "2. Schnittstellen\n\n"
        "   - OFFENE_FRAGE: Struktur; Beschreibe die technischen Schnittstellen und Datenflüsse.\n\n"
        "## Zusammenfassung\n\n"
        "Fasse die wichtigsten Erkenntnisse der Strukturanalyse zusammen.\n"
    ),
    "schutzbedarf": (
        "# Schutzbedarfsfeststellung\n\n"
        "## Geschäftsprozesse\n\n"
        "1. Prozessname\n\n"
        "   - Schutzbedarf: [normal|hoch|sehr hoch]\n"
        "   - OFFENE_FRAGE: Geschäftsprozesse; Welche Geschäftsprozesse sind relevant und welchen Schutzbedarf haben sie?\n\n"
        "## Anwendungen\n\n"
        "1. Anwendung\n\n"
        "   - Schutzbedarf: [normal|hoch|sehr hoch]\n"
        "   - OFFENE_FRAGE: Anwendungen; Welche Anwendungen sind relevant und welchen Schutzbedarf haben sie?\n\n"
        "## IT‑Systeme\n\n"
        "1. System\n\n"
        "   - Schutzbedarf: [normal|hoch|sehr hoch]\n"
        "   - OFFENE_FRAGE: IT‑Systeme; Welche IT‑Systeme sind relevant und welchen Schutzbedarf haben sie?\n\n"
        "## Zusammenfassung\n\n"
        "Fasse die wichtigsten Ergebnisse der Schutzbedarfsfeststellung zusammen.\n"
    ),
    "schutzbedarfsfeststellung": (
        "# Schutzbedarfsfeststellung\n\n"
        "## Geschäftsprozesse\n\n"
        "1. Prozessname\n\n"
        "   - Schutzbedarf: [normal|hoch|sehr hoch]\n"
        "   - OFFENE_FRAGE: Geschäftsprozesse; Welche Geschäftsprozesse sind relevant und welchen Schutzbedarf haben sie?\n\n"
        "## Anwendungen\n\n"
        "1. Anwendung\n\n"
        "   - Schutzbedarf: [normal|hoch|sehr hoch]\n"
        "   - OFFENE_FRAGE: Anwendungen; Welche Anwendungen sind relevant und welchen Schutzbedarf haben sie?\n\n"
        "## IT‑Systeme\n\n"
        "1. System\n\n"
        "   - Schutzbedarf: [normal|hoch|sehr hoch]\n"
        "   - OFFENE_FRAGE: IT‑Systeme; Welche IT‑Systeme sind relevant und welchen Schutzbedarf haben sie?\n\n"
        "## Zusammenfassung\n\n"
        "Fasse die wichtigsten Ergebnisse der Schutzbedarfsfeststellung zusammen.\n"
    ),
    "modellierung": (
        "# Modellierung\n\n"
        "## Geschäftsprozesse\n\n"
        "- OFFENE_FRAGE: Modellierung; Beschreiben Sie die Geschäftsprozesse.\n\n"
        "## IT‑Systeme\n\n"
        "- OFFENE_FRAGE: Modellierung; Beschreiben Sie die IT‑Systeme.\n\n"
        "## Anwendungen\n\n"
        "- OFFENE_FRAGE: Modellierung; Beschreiben Sie die Anwendungen.\n\n"
        "## Netzsegmente\n\n"
        "- OFFENE_FRAGE: Modellierung; Beschreiben Sie die Netzsegmente und deren Beziehungen.\n\n"
        "## Zusammenfassung\n\n"
        "Fasse die Ergebnisse der Modellierung zusammen.\n"
    ),
    "grundschutz_check": (
        "# IT‑Grundschutz‑Check\n\n"
        "## Anforderungen und Ist‑Stand\n\n"
        "| Anforderung | Ist‑Stand | Offene Fragen |\n"
        "|---|---|---|\n"
        "| Beispielanforderung | Maßnahme vorhanden? | OFFENE_FRAGE: Grundschutz; Beschreibung der Maßnahme |\n\n"
        "## Zusammenfassung\n\n"
        "Fasse den Soll‑Ist‑Vergleich zusammen und nenne offene Fragen.\n"
    ),
    "risikoanalyse": (
        "# Risikoanalyse\n\n"
        "## Risikoidentifikation\n\n"
        "- OFFENE_FRAGE: Risikoidentifikation; Welche Gefährdungen wurden identifiziert?\n\n"
        "## Risikobewertung\n\n"
        "- OFFENE_FRAGE: Risikobewertung; Wie hoch ist das Risiko (Schadenshöhe, Eintrittswahrscheinlichkeit)?\n\n"
        "## Risikobehandlung\n\n"
        "- OFFENE_FRAGE: Risikobehandlung; Welche Maßnahmen sind zur Risikoreduzierung vorgesehen?\n\n"
        "## Zusammenfassung\n\n"
        "Fasse die Ergebnisse der Risikoanalyse zusammen.\n"
    ),
    "maßnahmenplan": (
        "# Maßnahmen- / Umsetzungsplan\n\n"
        "## Kurzfristige Maßnahmen\n\n"
        "- OFFENE_FRAGE: Maßnahmen; Welche Maßnahmen müssen kurzfristig umgesetzt werden?\n\n"
        "## Mittelfristige Maßnahmen\n\n"
        "- OFFENE_FRAGE: Maßnahmen; Welche Maßnahmen werden mittelfristig umgesetzt?\n\n"
        "## Langfristige Maßnahmen\n\n"
        "- OFFENE_FRAGE: Maßnahmen; Welche Maßnahmen werden langfristig umgesetzt?\n\n"
        "## Zusammenfassung\n\n"
        "Fasse die geplanten Maßnahmen zusammen.\n"
    ),
    "sicherheitskonzept": (
        "# Sicherheitskonzept\n\n"
        "## Einleitung\n\n"
        "Beschreibe den Zweck und Geltungsbereich des Sicherheitskonzepts.\n\n"
        "## Strukturanalyse\n\n"
        "(Zusammenfassung der Strukturanalyse)\n\n"
        "## Schutzbedarfsfeststellung\n\n"
        "(Zusammenfassung der Schutzbedarfsfeststellung)\n\n"
        "## Modellierung\n\n"
        "(Zusammenfassung der Modellierung)\n\n"
        "## IT‑Grundschutz‑Check\n\n"
        "(Zusammenfassung des IT‑Grundschutz‑Checks)\n\n"
        "## Risikoanalyse\n\n"
        "(Zusammenfassung der Risikoanalyse)\n\n"
        "## Maßnahmenplan\n\n"
        "(Zusammenfassung des Maßnahmenplans)\n\n"
        "## Zusammenfassung\n\n"
        "Fasse alle Ergebnisse in einer übergreifenden Zusammenfassung zusammen.\n"
    ),
    # Alias-Schlüssel (Umlaute und Bindestriche) verweisen auf dieselben
    # Inhalte wie die Originalschlüssel. Sie werden hier dupliziert,
    # damit die statischen Vorlagen für alternative Schreibweisen
    # automatisch bereitgestellt werden.
    "massnahmenplan": (
        "# Maßnahmen- / Umsetzungsplan\n\n"
        "## Kurzfristige Maßnahmen\n\n"
        "- OFFENE_FRAGE: Maßnahmen; Welche Maßnahmen müssen kurzfristig umgesetzt werden?\n\n"
        "## Mittelfristige Maßnahmen\n\n"
        "- OFFENE_FRAGE: Maßnahmen; Welche Maßnahmen werden mittelfristig umgesetzt?\n\n"
        "## Langfristige Maßnahmen\n\n"
        "- OFFENE_FRAGE: Maßnahmen; Welche Maßnahmen werden langfristig umgesetzt?\n\n"
        "## Zusammenfassung\n\n"
        "Fasse die geplanten Maßnahmen zusammen.\n"
    ),
    "grundschutz-check": (
        "# IT‑Grundschutz‑Check\n\n"
        "## Anforderungen und Ist‑Stand\n\n"
        "| Anforderung | Ist‑Stand | Offene Fragen |\n"
        "|---|---|---|\n"
        "| Beispielanforderung | Maßnahme vorhanden? | OFFENE_FRAGE: Grundschutz; Beschreibung der Maßnahme |\n\n"
        "## Zusammenfassung\n\n"
        "Fasse den Soll‑Ist‑Vergleich zusammen und nenne offene Fragen.\n"
    ),
}


async def _call_ollama_chat(messages: List[dict], model: str) -> str:
    """Sendet die Nachrichten an Ollama und liefert den Antworttext.

    Dieses Hilfsmodul kapselt den HTTP‑Aufruf, so dass im Falle
    unerwarteter Fehler ein klarer Exception‑Flow erzeugt wird.
    """

    url = f"{OLLAMA_URL}/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message") or {}
        return message.get("content") or ""


def _build_prompt(artifact_type: str, project_name: str) -> str:
    """Erstellt den finalen Prompt für das LLM.

    Ergänzt den projektspezifischen Kontext (Projektname) und den
    passenden Basisprompt aus ``PROMPT_TEMPLATES``. Gibt immer
    einen String zurück, der vom LLM als Benutzereingabe genutzt
    werden kann.
    """

    base = PROMPT_TEMPLATES.get(artifact_type, "")
    return (
        f"Du bist ein Assistent, der bei der Erstellung von IT‑Grundschutz‑"
        f"Dokumenten hilft. Projektname: {project_name}. {base}"
    )


async def generate_artifact_content(
    artifact_type: str, project_name: str
) -> Tuple[str, List[dict]]:
    """Erzeugt den Inhalt und offene Fragen für ein Artefakt.

    Es wird zunächst das große Modell (70B) verwendet. Falls der
    Aufruf fehlschlägt, wird in Entwicklungsumgebungen (ENV_PROFILE
    ungleich ``prod``) auf das kleinere 8B‑Modell ausgewichen. Im
    produktiven Betrieb wird bei Fehlern das statische Skelett
    verwendet. So bleibt das System robust bei fehlender
    Modellverfügbarkeit.

    Args:
        artifact_type: Typ des Artefakts (z. B. ``schutzbedarf``).
        project_name: Name des Projekts für Kontextinformationen.

    Returns:
        Tuple aus generiertem Markdown‑Inhalt und einer Liste von
        offenen Fragen (Dictionaries mit ``category`` und ``question``).
    """

    # Prüfe, ob es eine statische Vorlage für diesen Artefakt-Typ gibt.
    # Wenn ja, wird das LLM nicht genutzt. Dies stellt sicher, dass die
    # generierten Dokumente immer der erwarteten Struktur entsprechen.
    if artifact_type in STATIC_TEMPLATES:
        content = STATIC_TEMPLATES[artifact_type]
    else:
        prompt = _build_prompt(artifact_type, project_name)
        messages = [{"role": "user", "content": prompt}]
        content: str
        try:
            # Primär das große Modell verwenden
            content = await _call_ollama_chat(messages, MODEL_FASIKO_CREATE_70B)
        except Exception:
            # Fallback in Entwicklungsumgebungen: auf das kleinere 8B‑Modell
            if ENV_PROFILE != "prod":
                try:
                    content = await _call_ollama_chat(messages, MODEL_GENERAL_8B)
                except Exception:
                    # Bei erneuter Ausnahme: statisches Skelett
                    content = DEFAULT_TEMPLATES.get(artifact_type, "")
            else:
                # In Produktion: sofort auf statisches Skelett wechseln
                content = DEFAULT_TEMPLATES.get(artifact_type, "")

    # Nachbearbeitung: generische Einleitungen entfernen
    # Manche LLM‑Antworten enthalten einen unstrukturierten Einleitungstext,
    # der nicht Teil der eigentlichen Artefaktbeschreibung ist (z. B. „Das klingt
    # nach einem interessanten Projekt …“ oder Chat‑Floskeln). Um dies zu
    # vermeiden, überspringen wir alle Zeilen, bis eine erste Überschrift
    # (beginnend mit #, ##, ###) oder eine nummerierte/bullet‑Liste (z. B. „1. “,
    # „- “, „* “) erscheint.
    raw_lines = content.splitlines()
    start_index = 0
    for i, line in enumerate(raw_lines):
        stripped = line.lstrip()
        if (
            stripped.startswith("#")  # Markdown‑Überschrift
            or stripped.startswith("1.")  # nummerierte Liste (erste Ebene)
            or stripped.startswith("1 ")  # alternative Nummerierung ohne Punkt
            or stripped.startswith("- ")  # Bullet‑Liste
            or stripped.startswith("* ")  # Bullet‑Liste
        ):
            start_index = i
            break
    # Verwende nur den strukturierten Teil, verwerfe den Rest
    filtered_lines = raw_lines[start_index:]

    open_points: List[dict] = []
    lines: List[str] = []
    for line in filtered_lines:
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