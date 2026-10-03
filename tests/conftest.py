from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import EMBEDDING_DIMENSION
from app.schemas.analysis import LLMIncidentAnalysis
from app.services.embedding_service import EmbeddingService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_embedding_model(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    model = MagicMock()
    model.get_embedding_dimension.return_value = EMBEDDING_DIMENSION
    model.encode.return_value = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
    monkeypatch.setattr(EmbeddingService, "_load_model", lambda self: model)
    return model


@pytest.fixture
def fake_embedding_service() -> AsyncMock:
    service = AsyncMock(spec=EmbeddingService)
    service.embed_text.return_value = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
    return service


@pytest.fixture
def analysis_result() -> LLMIncidentAnalysis:
    return LLMIncidentAnalysis(
        summary="Repeated SSH authentication failures require investigation.",
        severity="high",
        likely_attack_type="Possible SSH brute force",
        recommended_actions=["Review successful authentication events."],
    )
