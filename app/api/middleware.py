"""Request IDs and access logs without request bodies or query strings."""

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


async def log_request(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Raw DB/provider exceptions may include document content or credentials.
        logger.error("Unhandled request failure request_id=%r", request_id)
        response = JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )
    response.headers["X-Request-ID"] = request_id
    duration_ms = (perf_counter() - started_at) * 1000
    logger.info(
        "%s %r status_code=%s duration_ms=%.1f request_id=%r",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request_id,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response
