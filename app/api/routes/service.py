from fastapi import APIRouter

from app.api.deps import RegistryDep
from app.config.settings import settings
from app.domain.enums import AudioFormat
from app.schemas.service import (
    Limits,
    OutputCapabilities,
    ProviderCapabilities,
    ServiceCapabilities,
)

router = APIRouter(tags=["service"])


@router.get(
    "/service",
    response_model=ServiceCapabilities,
    summary="Server-wide capabilities",
    description=(
        "Server-wide, per-provider **capabilities** — kept separate from `/voices` so this isn't "
        "repeated on every voice: supported output formats + default, request limits, and per "
        "provider the installed-language summary plus default quality/controls (what the "
        "provider CAN do — `controls` includes `false` entries, unlike the enabled-only shape "
        "on `/voices`). The voices themselves are on `GET /voices`; full per-provider details "
        "(output specs, voice notes) live under `docs/providers/`."
    ),
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "output": {"formats": ["wav", "mp3", "opus"], "default": "wav"},
                        "limits": {"maxTextLength": 2000, "maxConcurrentSyntheses": 2},
                        "providers": [
                            {
                                "id": "pocket",
                                "installedLanguages": ["en", "fr"],
                                "quality": "veryHigh",
                                "controls": {
                                    "pitch": False,
                                    "speed": False,
                                    "ssml": False,
                                    "boundary": False,
                                },
                            }
                        ],
                    }
                }
            }
        }
    },
)
async def get_service_capabilities(registry: RegistryDep) -> ServiceCapabilities:
    providers = [
        ProviderCapabilities(
            id=provider.id,
            installedLanguages=sorted(provider.active_languages()),
            quality=provider.default_quality,
            controls=provider.default_controls.as_dict(),
        )
        for provider in registry.all()
    ]
    return ServiceCapabilities(
        output=OutputCapabilities(formats=list(AudioFormat), default=AudioFormat.WAV),
        limits=Limits(
            maxTextLength=settings.max_text_length,
            maxConcurrentSyntheses=settings.max_concurrent_syntheses,
        ),
        providers=providers,
    )
