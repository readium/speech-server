import base64

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import SynthesizerDep, require_ready
from app.api.errors import problem_response
from app.schemas.utterance import SynthesizeRequest

router = APIRouter(tags=["synthesize"])


@router.post(
    "/synthesize",
    response_model=None,
    dependencies=[Depends(require_ready)],
    summary="Synthesize speech from text or SSML",
    description=(
        "Accepts an utterance and returns an audio file. "
        "Set `boundary: true` to receive a JSON response with base64-encoded audio "
        "and word-level timing marks. "
        "Supported formats: `wav` (default), `mp3`, `opus`."
    ),
    responses={
        200: {
            "description": (
                "Binary audio (`boundary: false`, default) "
                "or `application/json` with base64 audio + boundaries (`boundary: true`)."
            ),
        },
        400: problem_response("Empty text, or no voice given and no default configured"),
        404: problem_response("Voice not found, or voice/language not supported here"),
        413: problem_response("Text exceeds max length"),
        415: problem_response("Unsupported audio format"),
        422: problem_response("Request schema validation error"),
        503: problem_response("Service starting up (models loading), or provider unavailable"),
    },
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "basic": {
                            "summary": "Basic request (wav default)",
                            "value": {
                                "id": "urn:uuid:019f1784-d800-7cc5-9f39-39c1e1ca6fdd",
                                "text": "Hello, this is a test.",
                                "language": "en",
                                "voice": "urn:readium:tts:pocket:alba",
                            },
                        },
                        "opus_32kbps": {
                            "summary": "OPUS at 32 kbps",
                            "value": {
                                "id": "urn:uuid:019f1784-d800-7cc5-9f39-39c1e1ca6fdd",
                                "text": "Hello, this is a test.",
                                "language": "en",
                                "voice": "urn:readium:tts:pocket:alba",
                                "output": {"format": "opus", "bitrate": 32},
                            },
                        },
                        "with_boundaries": {
                            "summary": "Request word-level timing marks",
                            "value": {
                                "id": "urn:uuid:019f178c-cc7c-7bb3-a39b-d185f43d3cc4",
                                "text": "Ceci est un test.",
                                "language": "fr",
                                "voice": "urn:readium:tts:pocket:estelle",
                                "boundary": True,
                            },
                        },
                        "with_context": {
                            "summary": "With prosody context and speed",
                            "value": {
                                "text": "She opened the door.",
                                "language": "en",
                                "voice": "urn:readium:tts:pocket:alba",
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
