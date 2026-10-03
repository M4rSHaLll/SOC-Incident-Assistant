from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_embedding_service
from app.db.database import get_db_session
from app.main import create_app
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository

pytestmark = pytest.mark.usefixtures("fake_embedding_model")


@pytest.fixture
def search_repository(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    search = AsyncMock(
        return_value=[
            (
                Document(
                    id=1,
                    title="SSH brute force",
                    content="Multiple failed ssh login attempts.",
                    category="credential_access",
                ),
                0.25,
            )
        ]
    )
    monkeypatch.setattr(DocumentRepository, "search_similar", search)
    return search


@pytest.fixture
def client(
    fake_embedding_service: AsyncMock, search_repository: AsyncMock
) -> Iterator[TestClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedding_service
    with TestClient(app) as test_client:
        yield test_client


def test_search(
    client: TestClient, fake_embedding_service: AsyncMock, search_repository: AsyncMock
) -> None:
    response = client.post(
        "/api/v1/search", json={"query": "  failed ssh  ", "limit": 3}
    )

    assert response.status_code == 200
    assert response.json() == {
        "query": "failed ssh",
        "results": [
            {
                "document_id": 1,
                "title": "SSH brute force",
                "content": "Multiple failed ssh login attempts.",
                "category": "credential_access",
                "similarity": 0.75,
            }
        ],
    }
    fake_embedding_service.embed_text.assert_awaited_once_with("failed ssh")
    assert search_repository.call_args.args[1:] == (
        fake_embedding_service.embed_text.return_value,
        3,
    )


def test_search_empty_results(client: TestClient, search_repository: AsyncMock) -> None:
    search_repository.return_value = []

    response = client.post("/api/v1/search", json={"query": "failed ssh"})

    assert response.status_code == 200
    assert response.json() == {"query": "failed ssh", "results": []}
    assert search_repository.call_args.args[2] == 5


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"query": ""},
        {"query": " \n\t"},
        {"query": "ssh", "limit": 0},
        {"query": "ssh", "limit": 21},
        {"query": "ssh", "limit": "invalid"},
    ],
)
def test_search_validation(
    client: TestClient, fake_embedding_service: AsyncMock, payload: dict[str, object]
) -> None:
    response = client.post("/api/v1/search", json=payload)

    assert response.status_code == 422
    fake_embedding_service.embed_text.assert_not_awaited()
