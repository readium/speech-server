from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config.settings import settings
from app.drivers import ffmpeg as ffmpeg_driver

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 when the process is running.",
)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/readyz",
    response_model=HealthResponse,
    responses={503: {"description": "Service not ready"}},
    summary="Readiness probe",
    description="Returns 200 when the app is ready (models loaded, deps available). 503 otherwise.",
)
async def readyz(request: Request) -> JSONResponse:
    ready: bool = getattr(request.app.state, "ready", False)
    if not ready:
        return JSONResponse(status_code=503, content={"status": "not ready"})
    if not ffmpeg_driver.is_available(settings.ffmpeg_bin):
        return JSONResponse(status_code=503, content={"status": "ffmpeg not found"})
    registry = getattr(request.app.state, "registry", None)
    if registry:
        for provider in registry.all():
            if not await provider.health():
                return JSONResponse(
                    status_code=503,
                    content={"status": f"provider '{provider.id}' not ready"},
                )
    return JSONResponse(status_code=200, content={"status": "ok"})
