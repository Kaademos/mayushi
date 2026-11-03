import logging
import re
import uuid

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def correlation_id(request: Request) -> str:
    """Reuse a well-formed inbound request id, otherwise mint one."""
    inbound = request.headers.get(REQUEST_ID_HEADER, "")
    return inbound if _VALID_REQUEST_ID.fullmatch(inbound) else uuid.uuid4().hex


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        request_id = correlation_id(request)
        logger.exception(
            "unhandled error on %s %s (request_id=%s)",
            request.method,
            request.url.path,
            request_id,
        )
        return JSONResponse(
            {
                "error": "internal_error",
                "message": "An unexpected error occurred.",
                "correlation_id": request_id,
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            headers={REQUEST_ID_HEADER: request_id},
        )
