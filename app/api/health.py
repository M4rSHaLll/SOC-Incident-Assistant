"""Application health endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.api.dependencies import get_database_ready

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", responses={503: {"description": "Database unavailable"}})
async def ready(
    response: Response,
    database_ready: Annotated[bool, Depends(get_database_ready)],
) -> dict[str, str]:
    if not database_ready:
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ready"}
