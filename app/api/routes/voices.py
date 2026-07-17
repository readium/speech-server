from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import VoiceCatalogDep, require_ready
from app.api.errors import problem_response
from app.schemas.voice import Voice

router = APIRouter(tags=["voices"])


@router.get(
    "/voices",
    response_model=list[Voice],
    response_model_exclude_none=True,
    dependencies=[Depends(require_ready)],
    summary="List available TTS voices",
    description=(
        "The voices **actually installed** on this deployment (realtime) — each voice's "
        "`language` and `otherLanguages` reflect what's loaded now, bounded by `LANGUAGES` + "
        "`VOICE_LANGUAGES`. Model-level `quality`/`controls` are merged in per voice; `controls` "
        "lists only the enabled ones. Optionally filtered by language or provider; supports "
        "pagination via `offset` and `limit`. Response headers `X-Total-Count`, `X-Offset`, "
        "`X-Limit` reflect the full result set size."
    ),
    responses={
        503: problem_response("Service starting up (models loading)"),
        502: problem_response("Provider unavailable"),
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
                                        "name": "Alba",
                                        "originalName": "alba",
                                        "provider": "pocket",
                                        "identifier": "urn:readium:tts:pocket:alba",
                                        "language": "en-US",
                                        "otherLanguages": [],
                                        "gender": "male",
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
