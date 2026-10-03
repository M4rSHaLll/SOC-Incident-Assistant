"""HTTP endpoints and dependency wiring for knowledge base documents."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_embedding_service
from app.db.database import get_db_session
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentRead
from app.services.document_service import DocumentNotFoundError, DocumentService
from app.services.embedding_service import EmbeddingService

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def get_document_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
) -> DocumentService:
    return DocumentService(session, DocumentRepository(), embedding_service)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    data: DocumentCreate,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Document:
    return await service.create_document(data)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    service: Annotated[DocumentService, Depends(get_document_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Document]:
    return await service.list_documents(limit, offset)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: Annotated[int, Path(ge=1)],
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> Document:
    try:
        return await service.get_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
