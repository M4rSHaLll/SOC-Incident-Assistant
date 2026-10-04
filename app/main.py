"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.analysis import router as analysis_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.middleware import log_request
from app.api.search import router as search_router
from app.core.config import Settings
from app.core.logging import configure_logging
from app.db.database import create_database
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService


def create_app() -> FastAPI:
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        engine, session_factory = create_database(settings.database_url)
        app.state.db_session_factory = session_factory
        try:
            embedding_service = EmbeddingService(
                settings.embedding_model_name, settings.embedding_dimension
            )
            await embedding_service.load_model()
            app.state.embedding_service = embedding_service
            client = httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
            try:
                app.state.llm_service = LLMService(
                    client,
                    settings.llm_base_url,
                    settings.llm_api_key,
                    settings.llm_model,
                    settings.llm_timeout_seconds,
                )
                app.state.rag_max_context_chars = settings.rag_max_context_chars
                yield
            finally:
                await client.aclose()
        finally:
            await engine.dispose()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.middleware("http")(log_request)
    app.include_router(health_router)
    app.include_router(documents_router)
    app.include_router(search_router)
    app.include_router(analysis_router)
    return app


app = create_app()
