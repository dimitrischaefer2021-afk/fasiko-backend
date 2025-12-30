"""
Einstiegspunkt für das FaSiKo‑Backend.

Dieses Modul instanziiert die FastAPI‑Anwendung und registriert
grundlegende Endpunkte. Weitere Router werden in späteren Blöcken
hinzugefügt. Beim Start der Anwendung wird die Datenbank initialisiert
(`init_db`), sofern keine Migration via Alembic ausgeführt wurde.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from .settings import APP_NAME
from .db import init_db

# Importiere Router
from .api.health import router as health_router
from .api.projects import router as projects_router
from .api.open_points import router as open_points_router
from .api.artifacts import router as artifacts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan‑Hook zum Initialisieren der Datenbank in Entwicklungsumgebungen.

    Im Produktionsmodus werden Migrationen via Alembic ausgeführt. Diese
    Funktion stellt sicher, dass in einfachen Umgebungen (z. B. SQLite
    während der Entwicklung) die Tabellen vorhanden sind.
    """
    try:
        init_db()
    except Exception:
        # Die Migrationen wurden möglicherweise bereits angewandt; ignoriere Fehler
        pass
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# Registriere alle Router unter dem Präfix /api/v1
app.include_router(health_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")
app.include_router(open_points_router, prefix="/api/v1")