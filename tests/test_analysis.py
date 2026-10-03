from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.analysis import get_analysis_service
from app.api.dependencies import get_embedding_service, get_llm_service
from app.db.database import get_db_session
from app.main import create_app
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.analysis import AnalyzeResponse, LLMIncidentAnalysis, SourceDocument
from app.services.analysis_service import AnalysisService, KnowledgeBaseEmptyError
from app.services.llm_service import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
    LLMService,
)

pytestmark = pytest.mark.usefixtures("fake_embedding_model")


@pytest.fixture
def analysis_service(analysis_result: LLMIncidentAnalysis) -> AsyncMock:
    service = AsyncMock(spec=AnalysisService)
    service.analyze.return_value = AnalyzeResponse(
        **analysis_result.model_dump(),
        sources=[
            SourceDocument(document_id=7, title="SSH", category=None, similarity=0.9)
        ],
    )
    return service


@pytest.fixture
def client(analysis_service: AsyncMock) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_analysis_service] = lambda: analysis_service
    with TestClient(app) as test_client:
        yield test_client


def test_analyze(client: TestClient, analysis_service: AsyncMock) -> None:
    response = client.post(
        "/api/v1/analyze",
        json={"incident": "  Repeated failed SSH logins  ", "top_k": 2},
    )
    assert response.status_code == 200
    assert response.json() == analysis_service.analyze.return_value.model_dump()
    analysis_service.analyze.assert_awaited_once_with("Repeated failed SSH logins", 2)
    assert "content" not in response.json()["sources"][0]


@pytest.mark.parametrize(
    "payload",
    [
        {"incident": "short"},
        {"incident": " " * 20},
        {"incident": "x" * 10001},
        {"incident": "Failed SSH logins", "top_k": 0},
        {"incident": "Failed SSH logins", "top_k": 11},
    ],
)
def test_analyze_validation(
    client: TestClient, analysis_service: AsyncMock, payload: dict[str, object]
) -> None:
    assert client.post("/api/v1/analyze", json=payload).status_code == 422
    analysis_service.analyze.assert_not_awaited()


@pytest.mark.parametrize(
    ("exception", "status", "detail"),
    [
        (
            KnowledgeBaseEmptyError,
            409,
            "No relevant knowledge base documents are available",
        ),
        (LLMConfigurationError, 503, "LLM provider is not configured"),
        (LLMProviderError, 502, "LLM provider request failed"),
        (LLMResponseError, 502, "LLM provider returned an invalid analysis"),
    ],
)
def test_analyze_errors(
    client: TestClient,
    analysis_service: AsyncMock,
    exception: type[Exception],
    status: int,
    detail: str,
) -> None:
    analysis_service.analyze.side_effect = exception("SECRET raw diagnostic")
    response = client.post("/api/v1/analyze", json={"incident": "Failed SSH logins"})
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_analysis_dependency_wiring(
    fake_embedding_service: AsyncMock,
    analysis_result: LLMIncidentAnalysis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    llm = AsyncMock(spec=LLMService)
    llm.generate_analysis.return_value = analysis_result
    search = AsyncMock(
        return_value=[(Document(id=1, title="SSH", content="Check logs."), 0.2)]
    )
    monkeypatch.setattr(DocumentRepository, "search_similar", search)

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            yield session

    app.dependency_overrides[get_db_session] = session_override
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedding_service
    app.dependency_overrides[get_llm_service] = lambda: llm
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyze", json={"incident": "Failed SSH logins"}
        )
    assert response.status_code == 200
    assert response.json()["sources"][0]["document_id"] == 1
    llm.generate_analysis.assert_awaited_once()
    fake_embedding_service.embed_text.assert_awaited_once_with("Failed SSH logins")
    assert search.call_args.args[2] == 5
