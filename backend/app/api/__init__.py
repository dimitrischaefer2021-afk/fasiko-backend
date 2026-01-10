"""Router‑Paket für das FaSiKo‑Backend (Minimalversion).

Dieses Paket gruppiert alle FastAPI‑Router. Für Block 06 werden nur
Health‑ und Ready‑Router bereitgestellt. Weitere Router (z. B. für
Projekte, Artefakte, offene Punkte und Chat) werden in späteren
Blöcken ergänzt.
"""

from fastapi import APIRouter

from .health import router as health_router
from .ready import router as ready_router
from .jobs import router as jobs_router
from .export import router as export_router  # Export‑Router für Download
from .bsi import router as bsi_router  # BSI‑Router (Block 11)


def get_api_router() -> APIRouter:
    """Erstellt einen übergeordneten Router für alle Endpunkte."""

    api_router = APIRouter()
    api_router.include_router(health_router)
    api_router.include_router(ready_router)
    api_router.include_router(jobs_router)
    api_router.include_router(export_router)
    api_router.include_router(bsi_router)
    return api_router
