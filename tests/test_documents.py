from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_embedding_service
from app.api.documents import get_document_service
from app.db.database import get_db_session
from app.main import create_app
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate
from app.services.document_service import DocumentNotFoundError, DocumentService

pytestmark = pytest.mark.usefixtures("fake_embedding_model")


@pytest.fixture
def document() -> Document:
    return Document(
        id=1,
        title="Phishing playbook",
        content="Inspect the sender and isolate suspicious attachments.",
        category="phishing",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def service(document: Document) -> AsyncMock:
    mock = AsyncMock(spec=DocumentService)
    mock.create_document.return_value = document
    mock.get_document.return_value = document
    mock.list_documents.return_value = [document]
    return mock


@pytest.fixture
def client(service: AsyncMock) -> Iterator[TestClient]:
    app = create_app()

    def override_service() -> AsyncMock:
        return service

    app.dependency_overrides[get_document_service] = override_service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def expected_document() -> dict[str, object]:
    return {
        "id": 1,
        "title": "Phishing playbook",
        "content": "Inspect the sender and isolate suspicious attachments.",
        "category": "phishing",
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_create_document(
    client: TestClient, service: AsyncMock, expected_document: dict[str, object]
) -> None:
    payload = {
        "title": "Phishing playbook",
        "content": "Inspect the sender and isolate suspicious attachments.",
        "category": "phishing",
    }

    response = client.post("/api/v1/documents", json=payload)

    assert response.status_code == 201
    assert response.json() == expected_document
    service.create_document.assert_awaited_once_with(DocumentCreate(**payload))


def test_create_document_without_category(
    client: TestClient, service: AsyncMock, document: Document
) -> None:
    document.category = None
    payload = {"title": "  Phishing playbook  ", "content": "  Keep evidence.\n"}

    response = client.post("/api/v1/documents", json=payload)

    assert response.status_code == 201
    assert response.json()["category"] is None
    service.create_document.assert_awaited_once_with(
        DocumentCreate(title="Phishing playbook", content="Keep evidence.")
    )
    assert service.create_document.call_args.args[0].content == "Keep evidence."


def test_get_document(
    client: TestClient, service: AsyncMock, expected_document: dict[str, object]
) -> None:
    response = client.get("/api/v1/documents/1")

    assert response.status_code == 200
    assert response.json() == expected_document
    service.get_document.assert_awaited_once_with(1)


def test_get_missing_document(client: TestClient, service: AsyncMock) -> None:
    service.get_document.side_effect = DocumentNotFoundError(999)

    response = client.get("/api/v1/documents/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document 999 not found"}
    service.get_document.assert_awaited_once_with(999)


def test_list_documents(
    client: TestClient, service: AsyncMock, expected_document: dict[str, object]
) -> None:
    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    assert response.json() == [expected_document]
    service.list_documents.assert_awaited_once_with(20, 0)


def test_list_documents_with_pagination(client: TestClient, service: AsyncMock) -> None:
    service.list_documents.return_value = []

    response = client.get("/api/v1/documents", params={"limit": 5, "offset": 10})

    assert response.status_code == 200
    assert response.json() == []
    service.list_documents.assert_awaited_once_with(5, 10)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": "Title"},
        {"content": "Content"},
        {"title": "", "content": "Content"},
        {"title": "   ", "content": "Content"},
        {"title": "x" * 256, "content": "Content"},
        {"title": "Title", "content": ""},
        {"title": "Title", "content": " \n\t"},
        {"title": "Title", "content": "Content", "category": "x" * 101},
    ],
)
def test_create_document_rejects_invalid_body(
    client: TestClient, service: AsyncMock, payload: dict[str, object]
) -> None:
    response = client.post("/api/v1/documents", json=payload)

    assert response.status_code == 422
    service.create_document.assert_not_awaited()


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "invalid"},
        {"offset": "-1"},
    ],
)
def test_list_documents_rejects_invalid_pagination(
    client: TestClient, service: AsyncMock, params: dict[str, str]
) -> None:
    response = client.get("/api/v1/documents", params=params)

    assert response.status_code == 422
    service.list_documents.assert_not_awaited()


@pytest.mark.parametrize("document_id", ["0", "-1", "invalid"])
def test_get_document_rejects_invalid_id(
    client: TestClient, service: AsyncMock, document_id: str
) -> None:
    response = client.get(f"/api/v1/documents/{document_id}")

    assert response.status_code == 422
    service.get_document.assert_not_awaited()


def test_create_document_generates_embedding(
    fake_embedding_service: AsyncMock,
    document: Document,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    session = AsyncSession()
    persist = AsyncMock(return_value=document)
    monkeypatch.setattr(DocumentRepository, "create", persist)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedding_service

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents",
            json={"title": "Phishing playbook", "content": "Keep evidence."},
        )

    assert response.status_code == 201
    assert "embedding" not in response.json()
    fake_embedding_service.embed_text.assert_awaited_once_with("Keep evidence.")
    persist.assert_awaited_once_with(
        session,
        DocumentCreate(title="Phishing playbook", content="Keep evidence."),
        fake_embedding_service.embed_text.return_value,
    )
    assert not session.in_transaction()


@pytest.mark.anyio
async def test_embedding_failure_does_not_persist(
    fake_embedding_service: AsyncMock,
) -> None:
    fake_embedding_service.embed_text.side_effect = ValueError("Invalid embedding")
    repository = AsyncMock(spec=DocumentRepository)
    async with AsyncSession() as session:
        service = DocumentService(session, repository, fake_embedding_service)
        with pytest.raises(ValueError, match="Invalid embedding"):
            await service.create_document(DocumentCreate(title="Title", content="Text"))
        repository.create.assert_not_awaited()
        assert not session.in_transaction()
