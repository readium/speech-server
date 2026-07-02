import json
import logging
import logging.handlers
import sys
import time
import uuid
from queue import SimpleQueue

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "ts": self.formatTime(record, self.datefmt),
        }
        # Prefer structured fields attached to the record over the message string
        extra = getattr(record, "fields", None)
        if extra:
            log.update(extra)
        else:
            log["message"] = record.getMessage()
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log)


def configure_logging(level: str = "INFO") -> logging.handlers.QueueListener:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(JsonFormatter())

    # QueueHandler enqueues records instantly (non-blocking on the event loop).
    # QueueListener drains the queue in a background daemon thread.
    log_queue: SimpleQueue[logging.LogRecord] = SimpleQueue()
    queue_handler = logging.handlers.QueueHandler(log_queue)

    listener = logging.handlers.QueueListener(log_queue, stream_handler, respect_handler_level=True)
    listener.start()

    logging.root.handlers = [queue_handler]
    logging.root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").propagate = False

    return listener


_access_logger = logging.getLogger("app.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.monotonic()
        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        _access_logger.info(
            "",
            extra={
                "fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                    "client_ip": request.client.host if request.client else None,
                }
            },
        )
        response.headers["X-Request-Id"] = request_id
        return response
