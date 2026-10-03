from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import EMBEDDING_DIMENSION
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.analysis import LLMIncidentAnalysis
from app.schemas.document import DocumentCreate
from app.services.analysis_service import AnalysisService
from app.services.llm_service import LLMService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_analysis_retrieval_boundary(
    db_session: AsyncSession,
    fake_embedding_service: AsyncMock,
    analysis_result: LLMIncidentAnalysis,
) -> None:
    count = await db_session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.embedding.is_not(None))
    )
    assert count == 0, "Use a test DB without committed embedded documents"
    repository = DocumentRepository()
    closest = await repository.create(
        db_session,
        DocumentCreate(title="SSH response", content="Review successful logins."),
        [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1),
    )
    await repository.create(
        db_session,
        DocumentCreate(title="Other response", content="Other reference context."),
        [0.0, 1.0] + [0.0] * (EMBEDDING_DIMENSION - 2),
    )
    llm = AsyncMock(spec=LLMService)
    llm.generate_analysis.return_value = analysis_result
    service = AnalysisService(
        db_session, repository, fake_embedding_service, llm, 12000
    )

    result = await service.analyze("Repeated failed SSH logins", top_k=1)

    assert [source.document_id for source in result.sources] == [closest.id]
    assert result.sources[0].similarity == pytest.approx(1.0)
    llm.generate_analysis.assert_awaited_once()
    prompt = llm.generate_analysis.call_args.args[1]
    assert "Review successful logins." in prompt
    assert "Other reference context." not in prompt
