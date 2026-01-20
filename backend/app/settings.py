"""
Einstellungen für das FaSiKo‑Backend.

Alle Konfigurationswerte werden aus Umgebungsvariablen gelesen. Eine
Beispiel‑Konfigurationsdatei befindet sich in `.env.example` im
Projekt‑Root. Die meisten Werte haben sinnvolle Standardwerte, damit
die Anwendung im Entwicklungsmodus ohne weitere Anpassungen startet.
"""

import os
from typing import List, Optional


def get_env(name: str, default: str) -> str:
    """Liest eine Umgebungsvariable und liefert einen Default, wenn sie leer ist."""
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value != "" else default


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------
APP_NAME: str = get_env("APP_NAME", "FaSiKo‑Studio Backend")
ENV_PROFILE: str = get_env("ENV_PROFILE", "dev")

# ---------------------------------------------------------------------------
# Datenbank
# ---------------------------------------------------------------------------
# Standard: SQLite; wird in späteren Blöcken auf PostgreSQL umgestellt.
DATABASE_URL: str = get_env("DATABASE_URL", "sqlite:////data/app.db")

# ---------------------------------------------------------------------------
# Verzeichnisse
# ---------------------------------------------------------------------------
# Speicherorte für verschiedene Upload‑Typen und Exporte (werden via Docker‑Volumes bereitgestellt)
UPLOAD_DIR: str = get_env("UPLOAD_DIR", "/data/uploads")
OPENPOINT_DIR: str = get_env("OPENPOINT_DIR", "/data/openpoints")
CHAT_DIR: str = get_env("CHAT_DIR", "/data/chat")
EXPORT_DIR: str = get_env("EXPORT_DIR", "/data/exports")

# ---------------------------------------------------------------------------
# BSI‑Katalog‑Verzeichnis (Block 18)
# ---------------------------------------------------------------------------
# Pfad, unter dem hochgeladene BSI‑PDFs gespeichert werden. Beim Hochladen eines
# neuen Katalogs wird hier eine Datei abgelegt und anschließend vollständig
# verarbeitet. Pro Upload wird automatisch eine neue Versionsnummer vergeben.
BSI_CATALOG_DIR: str = get_env("BSI_CATALOG_DIR", "/data/bsi_catalogs")

# ---------------------------------------------------------------------------
# Grenzwerte
# ---------------------------------------------------------------------------
# Maximale Upload‑Größe in Bytes (Default: 30 MB)
MAX_UPLOAD_BYTES: int = int(get_env("MAX_UPLOAD_BYTES", str(30 * 1024 * 1024)))
# Maximale Anzahl von Quellen pro Projekt
MAX_SOURCES_PER_PROJECT: int = int(get_env("MAX_SOURCES_PER_PROJECT", "50"))
# Maximale parallele Jobs (LLM‑Generierung, Exporte)
MAX_PARALLEL_JOBS: int = int(get_env("MAX_PARALLEL_JOBS", "3"))
# Maximal zulässige Job‑Laufzeit in Sekunden
JOB_TIMEOUT: int = int(get_env("JOB_TIMEOUT", "1800"))

# ---------------------------------------------------------------------------
# LLM‑Konfiguration
# ---------------------------------------------------------------------------
# Basis‑URL des Ollama‑Servers
OLLAMA_URL: str = get_env("OLLAMA_URL", "http://ollama:11434").rstrip("/")
# Modell für Chats (8‑B)
#
# Hinweis: Ab 2025/2026 existieren die Modellbezeichnungen "llama3.1" bzw.
# "llama3.2" nicht mehr in der ollama‑Bibliothek. Stattdessen werden die
# Instruct‑Modelle ohne Unterversion veröffentlicht. Um 404‑Fehler zu
# vermeiden, verwenden wir hier als Standard "llama3:8b" und "llama3:70b".
OLLAMA_CHAT_MODEL: str = get_env("OLLAMA_CHAT_MODEL", "llama3:8b")
# Modell für die initiale FaSiKo‑Erstellung (70‑B)
MODEL_FASIKO_CREATE_70B: str = get_env("MODEL_FASIKO_CREATE_70B", "llama3:70b")
# Modell für Bearbeitungen (8‑B)
MODEL_GENERAL_8B: str = get_env("MODEL_GENERAL_8B", "llama3:8b")

# ---------------------------------------------------------------------------
# SearXNG‑Konfiguration
# ---------------------------------------------------------------------------
# URL des selbst gehosteten SearXNG‑Services
SEARXNG_URL: str = get_env("SEARXNG_URL", "http://searxng:8080")
# Maximale Anzahl an Suchergebnissen, die an den Benutzer zurückgegeben werden
WEBSEARCH_MAX_RESULTS: int = int(get_env("WEBSEARCH_MAX_RESULTS", "5"))
# Timeout für Websuche in Sekunden
WEBSEARCH_TIMEOUT: int = int(get_env("WEBSEARCH_TIMEOUT", "15"))
# Maximale Länge der Suchanfragen
WEBSEARCH_MAX_QUERY_LENGTH: int = int(get_env("WEBSEARCH_MAX_QUERY_LENGTH", "200"))

# ---------------------------------------------------------------------------
# Sicherheit / API‑Schlüssel
# ---------------------------------------------------------------------------
API_KEY_ENABLED: bool = get_env("API_KEY_ENABLED", "false").lower() in {"1", "true", "yes"}
# Optionaler API‑Schlüssel (wenn aktiviert)
API_KEY: Optional[str] = os.getenv("API_KEY")

# CORS‑Konfiguration: Komma‑separierte Liste von erlaubten Ursprüngen. Ein "*" erlaubt alle.
CORS_ALLOWED_ORIGINS: List[str] = [
    origin.strip()
    for origin in get_env("CORS_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]