import http
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"
ERROR_BASE = "https://readium.org/speech-server/error#"


class ProblemDetail(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None


def problem_response(description: str) -> dict[str, Any]:
    return {"model": ProblemDetail, "description": description}


# --- exception hierarchy ---


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"
    title: str = "Internal Server Error"

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class RequestValidationFailed(AppError):
    status_code = 400
    code = "validation_failed"
    title = "Invalid Request"


class VoiceNotFound(AppError):
    status_code = 404
    code = "voice_not_found"
    title = "Voice Not Found"


class UnsupportedFormat(AppError):
    status_code = 415
    code = "unsupported_format"
    title = "Unsupported Format"


class PayloadTooLarge(AppError):
    status_code = 413
    code = "payload_too_large"
    title = "Payload Too Large"


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    title = "Too Many Requests"


class ProviderError(AppError):
    status_code = 502
    code = "provider_error"
    title = "Provider Error"


class ProviderTimeout(AppError):
    status_code = 504
    code = "provider_timeout"
    title = "Provider Timeout"


class ServiceNotReady(AppError):
    status_code = 503
    code = "service_not_ready"
    title = "Service Not Ready"


# --- helpers ---


def _problem_response(
    request: Request,
    status: int,
    type_: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    body = ProblemDetail(
        type=type_,
        title=title,
        status=status,
        detail=detail,
        instance=f"urn:uuid:{request.state.request_id}",
        errors=errors,
    )
    return JSONResponse(
        status_code=status,
        content=body.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


# --- error handlers ---


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        detail = f"{exc.message}: {exc.detail}" if exc.detail else exc.message
        return _problem_response(request, exc.status_code, ERROR_BASE + exc.code, exc.title, detail)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        title = http.HTTPStatus(exc.status_code).phrase
        return _problem_response(request, exc.status_code, "about:blank", title, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem_response(
            request,
            422,
            ERROR_BASE + "validation_failed",
            "Invalid Request",
            "Request validation failed",
            errors=jsonable_encoder(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger("app.errors").exception("Unhandled error")
        return _problem_response(
            request,
            AppError.status_code,
            ERROR_BASE + AppError.code,
            AppError.title,
            "An unexpected error occurred.",
        )
