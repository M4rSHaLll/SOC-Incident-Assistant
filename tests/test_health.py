import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.mark.usefixtures("fake_embedding_model")
def test_health() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
