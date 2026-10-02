from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.documents import get_document_service
from app.main import create_app
from app.models.document import Document
from app.schemas.document import DocumentCreate
from app.services.document_service import DocumentNotFoundError, DocumentService


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
