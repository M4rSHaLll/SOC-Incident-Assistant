import logging
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

pytestmark = pytest.mark.usefixtures("fake_embedding_model")


@pytest.mark.parametrize(("path", "status"), [("/health", 200), ("/missing", 404)])
def test_generated_request_id(path: str, status: int) -> None:
    with TestClient(create_app()) as client:
        first = client.get(path)
        second = client.get(path)
    assert first.status_code == status
    assert UUID(first.headers["X-Request-ID"]).version == 4
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_request_log_preserves_id_without_sensitive_data(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO), TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/search?token=private-query",
            headers={
                "X-Request-ID": "client-request-42",
                "Authorization": "private-key",
            },
            json={"unexpected": "private-body"},
        )
    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "client-request-42"
    record = next(r for r in caplog.records if hasattr(r, "request_id"))
    assert record.request_id == "client-request-42"
    assert record.method == "POST"
    assert record.path == "/api/v1/search"
    assert record.status_code == 422
    assert record.duration_ms >= 0
    for secret in ("private-query", "private-key", "private-body"):
        assert secret not in caplog.text


def test_unexpected_failure_is_private_and_keeps_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()

    @app.get("/failing-test-route")
    async def failing_route() -> None:
        raise RuntimeError("private-error-details")

    with TestClient(app) as client:
        response = client.get(
            "/failing-test-route", headers={"X-Request-ID": "failed-request"}
        )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["X-Request-ID"] == "failed-request"
    assert "private-error-details" not in caplog.text
