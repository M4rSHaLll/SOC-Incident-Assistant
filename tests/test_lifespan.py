from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.embedding_service import EmbeddingService

pytestmark = pytest.mark.usefixtures("fake_embedding_model")


def test_http_client_closed_on_shutdown() -> None:
    app = create_app()
    with TestClient(app) as client:
        http_client = app.state.llm_service.client
        assert not http_client.is_closed
        assert client.get("/health").status_code == 200
    assert http_client.is_closed


def test_engine_disposed_if_model_startup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = AsyncMock()
    monkeypatch.setattr("app.main.create_database", lambda url: (engine, None))
    monkeypatch.setattr(
        EmbeddingService,
        "load_model",
        AsyncMock(side_effect=RuntimeError("load failed")),
    )
    with pytest.raises(RuntimeError, match="load failed"), TestClient(create_app()):
        pass
    engine.dispose.assert_awaited_once()


def test_engine_disposed_if_client_shutdown_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = AsyncMock()
    monkeypatch.setattr("app.main.create_database", lambda url: (engine, None))
    original_close = httpx.AsyncClient.aclose

    async def failing_close(client: httpx.AsyncClient) -> None:
        await original_close(client)
        raise RuntimeError("close failed")

    monkeypatch.setattr(httpx.AsyncClient, "aclose", failing_close)
    with pytest.raises(RuntimeError, match="close failed"), TestClient(create_app()):
        pass
    engine.dispose.assert_awaited_once()
