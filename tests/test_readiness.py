from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_database_ready
from app.main import create_app
from app.services.readiness import check_database


@pytest.mark.usefixtures("fake_embedding_model")
@pytest.mark.parametrize(
    ("available", "status_code", "status"),
    [(True, 200, "ready"), (False, 503, "not_ready")],
)
def test_readiness(available: bool, status_code: int, status: str) -> None:
    app = create_app()
    app.dependency_overrides[get_database_ready] = lambda: available
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == status_code
    assert response.json() == {"status": status}


@pytest.mark.usefixtures("fake_embedding_model")
def test_liveness_does_not_check_database() -> None:
    def unexpected_check() -> bool:
        pytest.fail("Liveness must not check the database")

    app = create_app()
    app.dependency_overrides[get_database_ready] = unexpected_check
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.anyio
async def test_database_probe() -> None:
    session = AsyncMock(spec=AsyncSession)
    assert await check_database(session) is True
    session.execute.assert_awaited_once()
    assert str(session.execute.call_args.args[0]) == "SELECT 1"


@pytest.mark.anyio
@pytest.mark.parametrize("error", [OSError, TimeoutError])
async def test_database_probe_failure_is_private(
    error: type[Exception], caplog: pytest.LogCaptureFixture,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = error("private-connection-details")
    assert await check_database(session) is False
    assert "private-connection-details" not in caplog.text
