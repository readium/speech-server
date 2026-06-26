from fastapi import APIRouter

from app.api.v1.routes.synthesize import router as synthesize_router
from app.api.v1.routes.voices import router as voices_router

v1_router = APIRouter()
v1_router.include_router(voices_router)
v1_router.include_router(synthesize_router)
