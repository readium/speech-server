from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import SynthesizerDep
from app.api.errors import ErrorResponse
from app.schemas.utterance import SynthesizeRequest

router = APIRouter(tags=["synthesize"])


@router.post(
    "/synthesize",
    summary="Synthesize speech from text or SSML",
    description=(
        "Accepts an utterance and returns an audio file. "
        "Phase 1: WAV only. mp3/opus available after ffmpeg integration (Phase 3)."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Empty or whitespace text"},
        404: {"model": ErrorResponse, "description": "Voice URI not found"},
        415: {"model": ErrorResponse, "description": "Unsupported audio format"},
        422: {"model": ErrorResponse, "description": "Request schema validation error"},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "basic_wav": {
                            "summary": "Basic WAV synthesis",
                            "value": {
                                "text": "Hello, world!",
                                "voice": "urn:readium:tts:fake:en-US-standard",
                                "format": "wav",
                            },
                        },
                        "with_prosody": {
                            "summary": "With speed and context",
                            "value": {
                                "text": "She opened the door.",
                                "voice": "urn:readium:tts:fake:en-US-standard",
                                "format": "wav",
                                "language": "en-US",
                                "speed": 0.9,
                                "prev_utterance": "It was a dark night.",
                                "next_utterance": "The room was cold.",
                            },
                        },
                    }
                }
            }
        }
    },
)
async def synthesize(
    request: SynthesizeRequest,
    synthesizer: SynthesizerDep,
) -> StreamingResponse:
    audio_bytes, content_type = await synthesizer.synthesize(request)
    ext = content_type.split("/")[-1].replace("mpeg", "mp3").replace("ogg", "ogg")
    return StreamingResponse(
        iter([audio_bytes]),
        media_type=content_type,
        headers={"Content-Disposition": f"attachment; filename=speech.{ext}"},
    )
