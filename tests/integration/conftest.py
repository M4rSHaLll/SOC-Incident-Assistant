from collections.abc import AsyncIterator

import pytest
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def test_database_url() -> URL:
    settings = Settings()
    if not settings.test_database_url:
        pytest.skip("Set TEST_DATABASE_URL to a separately migrated PostgreSQL test DB")

    url = make_url(settings.test_database_url)
    if url.drivername != "postgresql+asyncpg":
        pytest.fail("TEST_DATABASE_URL must use postgresql+asyncpg")
    if not url.database or not url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL database name must end with _test")
    if url.database == make_url(settings.database_url).database:
        pytest.fail("TEST_DATABASE_URL must use a different database from DATABASE_URL")
    return url


@pytest.fixture
async def db_session(test_database_url: URL) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(test_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
