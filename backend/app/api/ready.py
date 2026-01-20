"""
Ready‑Endpoint des FaSiKo‑Backends (Block 06).

Dieser Endpunkt prüft die Betriebsbereitschaft des Systems. Er
testet, ob die Datenbank erreichbar ist, ob die LLM‑Modelle über
Ollama verfügbar sind und ob der SearXNG‑Dienst antwortet.
Die Ergebnisse werden als Liste von `ReadyComponent` zurückgegeben.
"""

from __future__ import annotations

import asyncio
from typing import List

import httpx  # hinzugefügt für den SearXNG‑Check

from sqlalchemy import text
from fastapi import APIRouter

from ..schemas import ReadyOut, ReadyComponent
from ..settings import (
    ENV_PROFILE,
    MODEL_GENERAL_8B,
    MODEL_FASIKO_CREATE_70B,
    SEARXNG_URL,
)
from ..llm_client import call_llm
from ..db import engine

router = APIRouter(tags=["ready"])

async def _check_database() -> ReadyComponent:
    """Prüft die Verbindung zur Datenbank mittels SELECT 1."""
    name = "database"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ReadyComponent(name=name, status="ok")
    except Exception as exc:
        return ReadyComponent(name=name, status="error", message=str(exc))

async def _check_ollama_model(model_name: str) -> ReadyComponent:
    """Prüft, ob ein bestimmtes LLM‑Modell über den zentralen Client verfügbar ist."""
    comp_name = f"llm_{model_name}"
    messages = [{"role": "user", "content": "ping"}]
    try:
        # Versuche über den gemeinsamen Client eine Antwort zu erhalten.
        await call_llm(messages=messages, model=model_name)
        return ReadyComponent(name=comp_name, status="ok")
    except Exception as exc:
        # In der Entwicklungsumgebung ist das große 70B‑Modell optional.
        # Wenn es nicht geladen ist oder der Modellname nicht existiert,
        # geben wir einen Warnstatus zurück, damit der gesamte Ready‑Check
        # nicht fehlschlägt. In Produktion bleibt es ein Fehler.
        if ENV_PROFILE != "prod" and model_name == MODEL_FASIKO_CREATE_70B:
            return ReadyComponent(name=comp_name, status="warn", message=str(exc))
        return ReadyComponent(name=comp_name, status="error", message=str(exc))

async def _check_searxng() -> ReadyComponent:
    """Prüft, ob der SearXNG‑Service erreichbar ist."""
    name = "searxng"
    url = f"{SEARXNG_URL}/"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
        return ReadyComponent(name=name, status="ok")
    except Exception as exc:
        return ReadyComponent(name=name, status="error", message=str(exc))

@router.get("/ready", response_model=ReadyOut)
async def ready() -> ReadyOut:
    """Führt alle Prüfungen durch und gibt das Ergebnis zurück."""
    tasks: List[asyncio.Future[ReadyComponent]] = []
    # Datenbank prüfen
    tasks.append(asyncio.create_task(_check_database()))
    # LLM‑Modelle prüfen (8B & 70B)
    tasks.append(asyncio.create_task(_check_ollama_model(MODEL_GENERAL_8B)))
    tasks.append(asyncio.create_task(_check_ollama_model(MODEL_FASIKO_CREATE_70B)))
    # SearXNG prüfen
    tasks.append(asyncio.create_task(_check_searxng()))
    results = await asyncio.gather(*tasks)
    # Ergebnis zurückgeben (kein automatischer Fallback hier; Fallback‑Logik ist in generator.py implementiert)
    return ReadyOut(components=results)