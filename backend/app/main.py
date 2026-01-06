"""
Einstiegspunkt für das FaSiKo-Backend.

Dieses Modul instanziiert die FastAPI-Anwendung und registriert die API-Router.
Beim Start der Anwendung wird die Datenbank initialisiert (`init_db`).

Wichtig:
- Alle Endpunkte laufen unter /api/v1/...
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .settings import APP_NAME
from .db import init_db

# Router Imports
from .api.health import router as health_router
from .api.projects import router as projects_router
from .api.artifacts import router as artifacts_router
from .api.open_points import router as open_points_router
from .api.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/Shutdown Hook.
    Initialisiert DB (falls nötig). Migrationen via Alembic sind möglich;
    init_db darf dabei nicht „hart“ scheitern.
    """
    try:
        init_db()
    except Exception:
        # Falls Migrationen bereits sauber angewandt wurden oder init_db intern anders läuft,
        # blockieren wir den Start nicht.
        pass
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# Alle Router unter /api/v1
app.include_router(health_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")
app.include_router(open_points_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")