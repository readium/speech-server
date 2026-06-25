from fastapi import APIRouter

from app.api.v1.routes.health import router as health_router

v1_router = APIRouter()

# Health routes are unversioned; included here for grouping but mounted at root in main.py
# Phase 1+ will add: voices_router, synthesize_router
_ = health_router  # imported but mounted at root level — see main.py
