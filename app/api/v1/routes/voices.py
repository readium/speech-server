from fastapi import APIRouter, Query, Response

from app.api.deps import VoiceCatalogDep
from app.api.errors import ErrorResponse
from app.schemas.voice import Voice

router = APIRouter(tags=["voices"])


@router.get(
    "/voices",
    response_model=list[Voice],
    response_model_exclude_none=True,
    summary="List available TTS voices",
    description=(
        "Returns voices registered across enabled providers, "
        "optionally filtered by language or provider. "
        "Supports pagination via `offset` and `limit`. "
        "Response headers `X-Total-Count`, `X-Offset`, `X-Limit` reflect the full result set size."
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
                                        "source": "json",
                                        "label": "Alba (English)",
                                        "name": "pocket-en-alba",
                                        "originalName": "alba",
                                        "voiceURI": "urn:readium:tts:pocket:en-alba",
                                        "language": "en",
                                        "gender": "female",
                                        "quality": "normal",
                                        "pitchControl": False,
                                        "preloaded": True,
                                        "provider": "pocket",
                                        "engineVoiceId": "alba",
                                        "sampleRate": 24000,
                                        "mimeTypes": ["audio/mpeg", "audio/wav", "audio/ogg"],
                                        "boundary": False,
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
    response: Response,
    catalog: VoiceCatalogDep,
    language: str | None = None,
    provider: str | None = None,
    offset: int = Query(default=0, ge=0, description="Number of voices to skip"),
    limit: int | None = Query(default=None, ge=1, description="Max voices to return"),
) -> list[Voice]:
    all_voices = catalog.list(language=language, provider=provider)
    total = len(all_voices)
    page = all_voices[offset : offset + limit] if limit is not None else all_voices[offset:]
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Offset"] = str(offset)
    if limit is not None:
        response.headers["X-Limit"] = str(limit)
    return page
