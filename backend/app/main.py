from contextlib import asynccontextmanager
from fastapi import FastAPI

from .settings import APP_NAME
from .db import init_db
from .api.health import router as health_router
from .api.projects import router as projects_router
from .api.artifacts import router as artifacts_router
from .api.open_points import router as open_points_router
from .api.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

app.include_router(health_router, prefix="/api")
app.include_router(projects_router, prefix="/api")
app.include_router(artifacts_router, prefix="/api")
app.include_router(open_points_router, prefix="/api")
app.include_router(chat_router, prefix="/api")