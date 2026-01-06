"""
Websuche für das FaSiKo‑Backend.

Diese Version bricht Suchanfragen nach kurzer Zeit ab. Die Spracheinstellung
wird nicht übergeben, damit sie keine Engines blockiert. Bei Fehlern oder
Timeouts liefert sie einfach eine leere Liste zurück.
"""

from __future__ import annotations

import httpx
from typing import List, Dict

from .settings import (
    SEARXNG_URL,
    WEBSEARCH_MAX_RESULTS,
    WEBSEARCH_TIMEOUT,
    WEBSEARCH_MAX_QUERY_LENGTH,
)

async def searxng_search(query: str) -> List[Dict[str, str]]:
    if not query:
        return []
    # Länge begrenzen
    if len(query) > WEBSEARCH_MAX_QUERY_LENGTH:
        query = query[:WEBSEARCH_MAX_QUERY_LENGTH]
    url = f"{SEARXNG_URL}/search"
    params = {
        "q": query,
        "format": "json",
        # keine language-Angabe, um Fehler zu vermeiden
    }
    try:
        # Nur kurze Zeit auf eine Antwort warten
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=WEBSEARCH_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []
    results = data.get("results") or []
    items: List[Dict[str, str]] = []
    for res in results[:WEBSEARCH_MAX_RESULTS]:
        title = res.get("title") or ""
        url_ = res.get("url") or ""
        # kein snippet mehr -> nur Titel und URL
        items.append({"title": title, "url": url_})
    return items