"""Semantic retrieval orchestration."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.schemas.search import SearchResponse, SearchResult
from app.services.embedding_service import EmbeddingService


class SearchService:
    def __init__(
        self,
        session: AsyncSession,
        repository: DocumentRepository,
        embedding_service: EmbeddingService,
    ) -> None:
        self.session = session
        self.repository = repository
        self.embedding_service = embedding_service

    async def search(self, query: str, limit: int) -> SearchResponse:
        embedding = await self.embedding_service.embed_text(query)
        matches = await self.repository.search_similar(self.session, embedding, limit)
        return SearchResponse(
            query=query,
            results=[
                SearchResult(
                    document_id=document.id,
                    title=document.title,
                    content=document.content,
                    category=document.category,
                    similarity=1.0 - distance,
                )
                for document, distance in matches
            ],
        )
