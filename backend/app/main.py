"""
Einstiegspunkt für das FaSiKo‑Backend.

Dieses Modul instanziiert die FastAPI‑Anwendung und registriert alle API‑
Router. Beim Start der Anwendung wird die Datenbank initialisiert (`init_db`).

Für Block 07 wurde der Jobs‑Router hinzugefügt. Die bestehenden Router aus
Block 06 (Health, Projects, Artifacts, Open Points, Chat, Ready) bleiben
unverändert erhalten.
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
from .api.ready import router as ready_router
from .api.jobs import router as jobs_router  # Neu: Jobs‑Router
from .api.export import router as export_router  # Neu: Export‑Router
from .api.bsi import router as bsi_router  # Neu: BSI‑Baustein‑Router
from .api.sources import router as sources_router  # Neu: Quellen‑Router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup/Shutdown Hook.
    Initialisiert die Datenbank (falls erforderlich). Migrationen via Alembic
    sind möglich; ein Fehler in `init_db` blockiert den Start nicht.
    """
    try:
        init_db()
    except Exception:
        # Falls Migrationen bereits sauber angewandt wurden oder init_db intern
        # anders läuft, blockieren wir den Start nicht.
        pass
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# Alle Router unter /api/v1 registrieren
app.include_router(health_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")
app.include_router(open_points_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(ready_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")  # Registrierung des Jobs‑Routers
app.include_router(export_router, prefix="/api/v1")  # Registrierung des Export‑Routers
app.include_router(bsi_router, prefix="/api/v1")  # Registrierung des BSI‑Routers
app.include_router(sources_router, prefix="/api/v1")  # Registrierung des Quellen‑Routers