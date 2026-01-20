"""
Zentraler LLM‑Client für das FaSiKo‑Backend.

Dieser Client kapselt alle Aufrufe an den Ollama‑Server. In
früheren Versionen wurde eine Reihe von Endpoints (``/api/chat``,
``/api/generate`` und ``/v1/chat/completions``) ausprobiert, um mit
verschiedenen Ollama‑Releases kompatibel zu sein. Seit Block 20
wurden diese Fallbacks jedoch entfernt, da sich in der Praxis
herausgestellt hat, dass nur der klassische Chat‑Endpoint
``/api/chat`` zuverlässig verfügbar ist. Der Client verwendet daher
ausschließlich diesen Endpunkt. Sollte in Zukunft eine andere
Ollama‑Version eine neue API einführen, kann die Fallback‑Liste hier
entsprechend erweitert werden.

Die Funktion ``call_llm`` nimmt eine Liste von Nachrichten im
OpenAI‑Format (``{"role": ..., "content": ...}``) und einen
Modellnamen entgegen. Sie versucht, eine sinnvolle Antwort vom LLM
über den Endpunkt ``/api/chat`` zu erhalten und gibt den
Antworttext zurück. Wenn keine Antwort geliefert werden kann, wird
eine Ausnahme ausgelöst.

Das Modul wird von ``chat.py``, ``generator.py``, ``ready.py`` und
``normalizer.py`` genutzt, um alle LLM‑Aufrufe zentral zu bündeln.
"""

from __future__ import annotations

from typing import List, Dict, Optional

import httpx

from .settings import OLLAMA_URL, ENV_PROFILE


async def _extract_api_chat(data: Dict) -> Optional[str]:
    """Extrahiert die Antwort aus dem /api/chat‑Format."""
    message = data.get("message") or {}
    content = message.get("content")
    return content.strip() if isinstance(content, str) and content.strip() else None


async def _extract_api_generate(data: Dict) -> Optional[str]:
    """Extrahiert die Antwort aus dem /api/generate‑Format."""
    content = data.get("response")
    return content.strip() if isinstance(content, str) and content.strip() else None


async def _extract_openai(data: Dict) -> Optional[str]:
    """Extrahiert die Antwort aus dem OpenAI‑kompatiblen Format."""
    choices = data.get("choices")
    if choices and isinstance(choices, list):
        message = choices[0].get("message")
        if message:
            content = message.get("content")
            return content.strip() if isinstance(content, str) and content.strip() else None
    return None


async def call_llm(messages: List[Dict[str, str]], model: str) -> str:
    """Sendet Nachrichten an das Ollama‑LLM und liefert den Antworttext.

    Die Funktion versucht unterschiedliche Endpoints, um sowohl ältere
    als auch neuere Ollama‑Versionen zu unterstützen. Beim
    ``/api/generate``‑Fallback werden mehrere Nachrichten zu einem
    einfachen Prompt zusammengeführt.

    Args:
        messages: Liste der Nachrichten, jeweils mit ``role`` und
            ``content``. Es muss mindestens eine ``user``‑Nachricht
            enthalten sein. ``system``‑Nachrichten werden bei
            ``/api/generate`` als ``system`` genutzt.
        model: Name des zu verwendenden Modells (z. B. ``llama3:8b``).

    Returns:
        Den vom LLM generierten Antworttext (bereinigt von führenden
        und nachfolgenden Leerzeichen).

    Raises:
        Exception: Wenn keiner der Endpoints eine erfolgreiche Antwort
            liefert.
    """
    if not messages:
        raise ValueError("messages must not be empty")
    # Modellnamen normalisieren: Ab 2025 existieren die Unterversionsbezeichnungen
    # (z. B. "llama3.1:8b") in Ollama nicht mehr. In der Entwicklungsumgebung
    # wird ein solcher Name automatisch auf die neue Schreibweise ("llama3:8b")
    # abgebildet. In der Produktion führt die Angabe eines unbekannten Modells
    # zu einem Fehler. Dies verhindert stille Fallbacks.
    if "llama3.1" in model:
        if ENV_PROFILE != "prod":
            model = model.replace("llama3.1", "llama3")
        else:
            raise Exception(
                f"Ungültiger Modellname '{model}'. Bitte verwenden Sie die neue Bezeichnung ohne Unterversion, z. B. 'llama3:8b'."
            )
    # Extrahiere Prompt und System für den /api/generate‑Fallback
    system_parts: List[str] = []
    user_parts: List[str] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_parts.append(content)
    prompt = "\n\n".join(user_parts) if user_parts else ""
    system = "\n\n".join(system_parts) if system_parts else None
    # Prepare endpoint definitions: (path, payload_builder, extractor)
    async def build_chat_payload() -> Dict:
        return {"model": model, "messages": messages, "stream": False}

    async def build_generate_payload() -> Dict:
        payload: Dict[str, str | bool] = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        return payload

    async def build_openai_payload() -> Dict:
        return {"model": model, "messages": messages, "stream": False}

    # Für unsere aktuelle Ollama‑Version ist nur der klassische Chat‑Endpoint
    # verfügbar. Der /api/generate‑ und der OpenAI‑kompatible Endpunkt
    # (/v1/chat/completions) liefern 404‑Fehler. Daher nutzen wir ausschließlich
    # /api/chat. Sollte sich dies in Zukunft ändern, kann das Fallback hier
    # wieder aktiviert werden.
    endpoints = [
        ("/api/chat", build_chat_payload, _extract_api_chat),
    ]
    async with httpx.AsyncClient() as client:
        for path, payload_builder, extractor in endpoints:
            url = f"{OLLAMA_URL}{path}"
            try:
                payload = await payload_builder()
                resp = await client.post(url, json=payload, timeout=600)
                # Wenn der Endpunkt nicht existiert, versuchen wir den nächsten
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                data = resp.json()
                # Versuche den extrahierten Inhalt abzurufen. Die Extraktor-Funktion
                # gibt entweder einen String (ggf. leer) oder None zurück. Ein
                # leerer String bedeutet, dass das LLM keine Änderungen
                # vorgenommen hat. In diesem Fall betrachten wir die Antwort
                # ebenfalls als gültig und geben den leeren String zurück. Nur
                # wenn None zurückkommt, probieren wir den nächsten Endpunkt.
                content = await extractor(data)
                if content is not None:
                    return content
            except httpx.HTTPStatusError as http_err:
                # Bei 404 probieren wir den nächsten Endpunkt
                if http_err.response.status_code == 404:
                    continue
                # Ansonsten brechen wir ab und versuchen andere Endpunkte
                continue
            except Exception:
                # Bei sonstigen Fehlern versuchen wir den nächsten Endpunkt
                continue
    # Wenn keiner der Endpunkte eine Antwort lieferte, werfen wir eine Ausnahme
    raise Exception("No valid LLM endpoint responded")