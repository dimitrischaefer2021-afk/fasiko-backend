from fastapi import APIRouter
from ..schemas import HealthOut
from ..settings import APP_NAME

router = APIRouter(tags=["health"])

@router.get("/health", response_model=HealthOut)
def health():
    return {"status": "ok", "app": APP_NAME}