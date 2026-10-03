"""Semantic search endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_embedding_service
from app.db.database import get_db_session
from app.repositories.document_repository import DocumentRepository
from app.schemas.search import SearchRequest, SearchResponse
from app.services.embedding_service import EmbeddingService
from app.services.search_service import SearchService

router = APIRouter(prefix="/api/v1/search", tags=["search"])


def get_search_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> SearchService:
    return SearchService(session, DocumentRepository(), embedding_service)


@router.post("", response_model=SearchResponse)
async def search_documents(
    data: SearchRequest,
    service: Annotated[SearchService, Depends(get_search_service)],
) -> SearchResponse:
    return await service.search(data.query, data.limit)
