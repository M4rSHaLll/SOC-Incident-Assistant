"""Retrieve reference documents and generate validated incident analysis."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_repository import DocumentRepository
from app.schemas.analysis import AnalyzeResponse
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService
from app.services.prompt_builder import build_context, build_prompt

logger = logging.getLogger(__name__)


class KnowledgeBaseEmptyError(Exception):
    """No usable reference context is available."""


class AnalysisService:
    def __init__(
        self,
        session: AsyncSession,
        repository: DocumentRepository,
        embedding_service: EmbeddingService,
        llm_service: LLMService,
        max_context_chars: int,
    ) -> None:
        self.session = session
        self.repository = repository
        self.embedding_service = embedding_service
        self.llm_service = llm_service
        self.max_context_chars = max_context_chars

    async def analyze(self, incident: str, top_k: int) -> AnalyzeResponse:
        logger.info("Incident analysis started; top_k=%s", top_k)
        embedding = await self.embedding_service.embed_text(incident)
        matches = await self.repository.search_similar(self.session, embedding, top_k)
        logger.info("Retrieved %s documents for analysis", len(matches))
        context, sources = build_context(matches, self.max_context_chars)
        if not sources:
            raise KnowledgeBaseEmptyError(
                "No relevant knowledge base documents are available"
            )
        system_prompt, user_prompt = build_prompt(incident, context)
        analysis = await self.llm_service.generate_analysis(system_prompt, user_prompt)
        logger.info("Incident analysis completed; sources=%s", len(sources))
        return AnalyzeResponse(**analysis.model_dump(), sources=sources)
