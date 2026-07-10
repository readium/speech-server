from fastapi import APIRouter

from app.api.routes.synthesize import router as synthesize_router
from app.api.routes.voices import router as voices_router

router = APIRouter()
router.include_router(voices_router)
router.include_router(synthesize_router)
