import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.errors import register_error_handlers
from app.api.router import router
from app.api.routes.health import router as health_router
from app.api.routes.service import router as service_router
from app.config.settings import settings
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.concurrency import init_semaphore
from app.core.registry import ProviderRegistry
from app.core.voice_catalog import VoiceCatalog
from app.logging.config import RequestLoggingMiddleware, configure_logging
from app.providers.pocket_tts import PocketTTSProvider

logger = logging.getLogger(__name__)


def _build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    enabled = {p.strip() for p in settings.enabled_providers.split(",")}
    if "pocket" in enabled:
        registry.register(PocketTTSProvider())
    return registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log_listener = configure_logging(settings.log_level)
    init_semaphore(settings.max_concurrent_syntheses)

    registry = _build_registry()
    catalog = VoiceCatalog(registry)
    breakers = CircuitBreakerRegistry(
        [p.id for p in registry.all()],
        settings.circuit_breaker_failure_threshold,
        settings.circuit_breaker_recovery_seconds,
    )

    app.state.registry = registry
    app.state.voice_catalog = catalog
    app.state.circuit_breakers = breakers
    app.state.ready = False

    # Load models OFF the startup path — otherwise ASGI startup blocks and the
    # server accepts no connections (not even /healthz, /readyz) until models are
    # ready. Warmup runs in the background; readiness flips to True when it finishes.
    # A failure here leaves the server up reporting 503 on /readyz, not crashed.
    async def _warmup() -> None:
        try:
            for provider in registry.all():
                await provider.load()
            await catalog.load()
            app.state.ready = True
            logger.info("Startup warmup complete — service ready")
        except Exception:
            logger.exception("Startup warmup failed — service will report not ready")

    warmup_task = asyncio.create_task(_warmup())
    try:
        yield
    finally:
        app.state.ready = False
        warmup_task.cancel()
        with suppress(asyncio.CancelledError):
            await warmup_task
        log_listener.stop()  # flush remaining records before process exits


def create_app() -> FastAPI:
    app = FastAPI(
        title="Readium Speech Server",
        version="0.1.0",
        description=(
            "Remote TTS HTTP service for the Readium ecosystem. "
            "Exposes voices and synthesis behind a uniform provider interface."
        ),
        openapi_tags=[
            {"name": "health", "description": "Liveness and readiness probes."},
            {"name": "service", "description": "Server-wide capabilities."},
            {"name": "voices", "description": "List available TTS voices."},
            {"name": "synthesize", "description": "Convert text/SSML to audio."},
        ],
        servers=[{"url": f"https://{settings.domain}"}]
        if settings.app_env == "production"
        else None,
        lifespan=lifespan,
    )

    if settings.app_env == "production":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[settings.domain, "localhost", "127.0.0.1"],
        )
    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(service_router)
    app.include_router(router)

    @app.get("/demo", include_in_schema=False)
    async def demo() -> FileResponse:
        return FileResponse("app/static/demo.html")

    return app


app = create_app()
