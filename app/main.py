from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.v1.router import v1_router
from app.api.v1.routes.health import router as health_router
from app.config.settings import settings
from app.core.concurrency import init_semaphore
from app.core.registry import ProviderRegistry
from app.core.voice_catalog import VoiceCatalog
from app.logging.config import RequestLoggingMiddleware, configure_logging
from app.providers.fake import FakeProvider


def _build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    enabled = {p.strip() for p in settings.enabled_providers.split(",")}
    if "fake" in enabled:
        registry.register(FakeProvider())
    # Phase 2+: pocket, kokoro, elevenlabs, azure registered here
    return registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging(settings.log_level)
    init_semaphore(settings.max_concurrent_syntheses)

    registry = _build_registry()
    catalog = VoiceCatalog(registry)
    await catalog.load()

    app.state.registry = registry
    app.state.voice_catalog = catalog
    app.state.ready = True
    yield
    app.state.ready = False


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
            {"name": "voices", "description": "List available TTS voices."},
            {"name": "synthesize", "description": "Convert text/SSML to audio."},
        ],
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
