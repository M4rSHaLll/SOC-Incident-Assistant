import threading
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.config import EMBEDDING_DIMENSION
from app.main import create_app
from app.services.embedding_service import EmbeddingService

pytestmark = pytest.mark.anyio


async def test_embedding_is_float_list_off_event_loop(
    fake_embedding_model: MagicMock,
) -> None:
    encode_threads: list[int] = []

    def encode(*args: object, **kwargs: object) -> list[int]:
        encode_threads.append(threading.get_ident())
        return [1] + [0] * (EMBEDDING_DIMENSION - 1)

    fake_embedding_model.encode.side_effect = encode
    service = EmbeddingService("test-model", EMBEDDING_DIMENSION)
    await service.load_model()

    embedding = await service.embed_text("SSH brute force")

    assert isinstance(embedding, list)
    assert len(embedding) == EMBEDDING_DIMENSION
    assert all(isinstance(value, float) for value in embedding)
    assert encode_threads[0] != threading.get_ident()


async def test_rejects_wrong_output_dimension(fake_embedding_model: MagicMock) -> None:
    fake_embedding_model.encode.return_value = [1.0, 0.0]
    service = EmbeddingService("test-model", EMBEDDING_DIMENSION)
    await service.load_model()

    with pytest.raises(ValueError, match="Expected 384"):
        await service.embed_text("text")


async def test_rejects_model_dimension_mismatch(
    fake_embedding_model: MagicMock,
) -> None:
    fake_embedding_model.get_embedding_dimension.return_value = 768
    service = EmbeddingService("test-model", EMBEDDING_DIMENSION)

    with pytest.raises(ValueError, match="Model dimension"):
        await service.load_model()


def test_rejects_config_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="Database schema requires dimension 384"):
        EmbeddingService("test-model", 768)


@pytest.mark.parametrize("value", [0.0, float("nan"), float("inf")])
async def test_rejects_invalid_cosine_vector(
    fake_embedding_model: MagicMock, value: float
) -> None:
    fake_embedding_model.encode.return_value = [value] * EMBEDDING_DIMENSION
    service = EmbeddingService("test-model", EMBEDDING_DIMENSION)
    await service.load_model()

    with pytest.raises(ValueError, match="finite and nonzero"):
        await service.embed_text("text")


async def test_requires_loaded_model() -> None:
    service = EmbeddingService("test-model", EMBEDDING_DIMENSION)
    with pytest.raises(RuntimeError, match="load_model"):
        await service.embed_text("text")


def test_lifespan_loads_model_once(
    fake_embedding_model: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader = MagicMock(return_value=fake_embedding_model)
    monkeypatch.setattr(EmbeddingService, "_load_model", loader)

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200

    loader.assert_called_once()
