"""Shared HTTP dependencies."""

from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db_session
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.readiness import check_database


def get_embedding_service(request: Request) -> EmbeddingService:
    return cast(EmbeddingService, request.app.state.embedding_service)


def get_llm_service(request: Request) -> LLMService:
    return cast(LLMService, request.app.state.llm_service)


async def get_database_ready(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> bool:
    return await check_database(session)
