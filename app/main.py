"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import Settings
from app.db.database import create_database


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine, session_factory = create_database(settings.database_url)
        app.state.db_session_factory = session_factory
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(documents_router)
    return app


app = create_app()
