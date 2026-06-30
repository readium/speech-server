import base64

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import SynthesizerDep
from app.api.errors import ErrorResponse
from app.schemas.utterance import SynthesizeRequest

router = APIRouter(tags=["synthesize"])


@router.post(
    "/synthesize",
    response_model=None,
    summary="Synthesize speech from text or SSML",
    description=(
        "Accepts an utterance and returns an audio file. "
        "Set `boundary: true` to receive a JSON response with base64-encoded audio "
        "and word-level timing marks. "
        "Supported formats: `mp3` (default), `wav`, `opus`."
    ),
    responses={
        200: {
            "description": (
                "Binary audio (`boundary: false`, default) "
                "or `application/json` with base64 audio + boundaries (`boundary: true`)."
            ),
        },
        400: {"model": ErrorResponse, "description": "Empty or whitespace text"},
        404: {"model": ErrorResponse, "description": "Voice URI not found"},
        413: {"model": ErrorResponse, "description": "Text exceeds max length"},
        415: {"model": ErrorResponse, "description": "Unsupported audio format"},
        422: {"model": ErrorResponse, "description": "Request schema validation error"},
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "basic": {
                            "summary": "Basic request (mp3 default)",
                            "value": {
                                "id": "urn:uuid:019f1784-d800-7cc5-9f39-39c1e1ca6fdd",
                                "text": "Hello, this is a test.",
                                "language": "en",
                                "voice": "urn:readium:tts:pocket:en-alba",
                            },
                        },
                        "opus_32kbps": {
                            "summary": "OPUS at 32 kbps",
                            "value": {
                                "id": "urn:uuid:019f1784-d800-7cc5-9f39-39c1e1ca6fdd",
                                "text": "Hello, this is a test.",
                                "language": "en",
                                "voice": "urn:readium:tts:pocket:en-alba",
                                "output": {"format": "opus", "bitrate": 32},
                            },
                        },
                        "with_boundaries": {
                            "summary": "Request word-level timing marks",
                            "value": {
                                "id": "urn:uuid:019f178c-cc7c-7bb3-a39b-d185f43d3cc4",
                                "text": "Ceci est un test.",
                                "language": "fr",
                                "voice": "urn:readium:tts:pocket:fr-estelle",
                                "boundary": True,
                            },
                        },
                        "with_context": {
                            "summary": "With prosody context and speed",
                            "value": {
                                "text": "She opened the door.",
                                "language": "en",
                                "voice": "urn:readium:tts:pocket:en-alba",
                                "prev_utterance": "It was a dark night.",
                                "next_utterance": "The room was cold.",
                                "output": {"format": "mp3", "speed": 0.9},
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
) -> StreamingResponse | JSONResponse:
    audio_bytes, content_type, boundaries, boundaries_supported = await synthesizer.synthesize(
        request
    )

    if request.boundary:
        return JSONResponse(
            {
                "audio": base64.b64encode(audio_bytes).decode(),
                "format": request.output.format.value,
                "boundaries": [m.model_dump() for m in boundaries]
                if boundaries_supported
                else None,
            }
        )

    ext = content_type.split("/")[-1].replace("mpeg", "mp3")
    return StreamingResponse(
        iter([audio_bytes]),
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename=speech.{ext}"},
    )
