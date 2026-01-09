"""
Einstiegspunkt für das FaSiKo-Backend.

Dieses Modul instanziiert die FastAPI-Anwendung und registriert die API-Router.
Beim Start der Anwendung wird die Datenbank initialisiert (`init_db`).

Block 09:
- Jobs Router (Export als Job)
- Export Download Router (ZIP Download)
Alle bestehenden Router bleiben erhalten.
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
from .api.jobs import router as jobs_router
from .api.export import router as export_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception:
        # Start nicht blockieren (Migrationen laufen via Alembic)
        pass
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# Alle Router unter /api/v1
app.include_router(health_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")
app.include_router(open_points_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(ready_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")