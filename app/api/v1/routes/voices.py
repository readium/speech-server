from fastapi import APIRouter

from app.api.deps import VoiceCatalogDep
from app.api.errors import ErrorResponse
from app.schemas.voice import Voice

router = APIRouter(tags=["voices"])


@router.get(
    "/voices",
    response_model=list[Voice],
    summary="List available TTS voices",
    description=(
        "Returns all voices registered across enabled providers, "
        "optionally filtered by BCP-47 language tag prefix or provider id."
    ),
    responses={
        502: {"model": ErrorResponse, "description": "Provider unavailable"},
    },
    openapi_extra={
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "examples": {
                            "all_voices": {
                                "summary": "All voices",
                                "value": [
                                    {
                                        "label": "Fake Voice (English)",
                                        "voiceURI": "urn:readium:tts:fake:en-US-standard",
                                        "name": "fake-en-US",
                                        "language": "en-US",
                                        "provider": "fake",
                                        "engineVoiceId": "fake-en",
                                        "sampleRate": 22050,
                                        "mimeTypes": ["audio/wav"],
                                    }
                                ],
                            }
                        }
                    }
                }
            }
        }
    },
)
async def list_voices(
    catalog: VoiceCatalogDep,
    language: str | None = None,
    provider: str | None = None,
) -> list[Voice]:
    return catalog.list(language=language, provider=provider)
