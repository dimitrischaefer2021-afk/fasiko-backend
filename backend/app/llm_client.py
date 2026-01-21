"""
Zentraler LLM-Client für das FaSiKo-Backend.

Der Client kapselt Aufrufe an den Ollama-Server. Für Block 22 verwenden wir
ausschließlich den klassischen Chat-Endpunkt:

- POST {OLLAMA_URL}/api/chat

Warum nur /api/chat?
- In der Praxis ist /api/chat über Ollama-Versionen hinweg am stabilsten.
- Andere Endpunkte (/api/generate, /v1/chat/completions) sind je nach Version
  nicht verfügbar oder verhalten sich anders.

call_llm(...) liefert den reinen Text der Antwort zurück (kann auch leer sein),
oder wirft eine Exception, wenn keine valide Antwort ermittelt werden konnte.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import httpx

from .settings import ENV_PROFILE, OLLAMA_URL


def _normalize_model_name(model: str) -> str:
    """Normalisiert Modellnamen für DEV/PROD.

    Beispiel:
    - DEV: "llama3.1:8b" -> "llama3:8b"
    - PROD: unbekannte Unterversionen führen zu Fehler (um stille Fallbacks zu vermeiden)
    """
    if "llama3.1" in model:
        if ENV_PROFILE != "prod":
            return model.replace("llama3.1", "llama3")
        raise Exception(
            f"Ungültiger Modellname '{model}'. Bitte verwenden Sie die Bezeichnung ohne Unterversion, z. B. 'llama3:8b'."
        )
    return model


def _extract_api_chat(data: Dict) -> Optional[str]:
    """Extrahiert die Antwort aus dem /api/chat-Format."""
    message = data.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        # Leerstring ist erlaubt (z. B. "keine Änderungen")
        return content.strip()
    return None


async def call_llm(messages: List[Dict[str, str]], model: str) -> str:
    """Sendet Nachrichten an Ollama und liefert den Antworttext.

    Args:
        messages: OpenAI-Format: [{"role": "system"|"user"|"assistant", "content": "..."}]
        model: Ollama-Modellname, z. B. "llama3:8b" oder "llama3:70b"

    Returns:
        Der Antworttext (trimmed). Kann leer sein.

    Raises:
        Exception: Wenn keine valide Antwort geliefert wurde.
    """
    if not messages:
        raise ValueError("messages must not be empty")

    model = _normalize_model_name(model)

    url = f"{OLLAMA_URL}/api/chat"
    payload: Dict = {
        "model": model,
        "messages": messages,
        "stream": False,
        # deterministisch (wichtig für Normalisierung)
        "options": {"temperature": 0.0},
    }

    timeout = httpx.Timeout(600.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        # explizit 404 behandeln (falsche URL / falscher Base-URL)
        if resp.status_code == 404:
            raise Exception("Ollama endpoint /api/chat not found (404). Prüfe OLLAMA_URL.")
        resp.raise_for_status()
        data = resp.json()
        content = _extract_api_chat(data)
        if content is None:
            raise Exception("No valid LLM content in response")
        return content
