"""FastAPI application entry point."""

import logging

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import Settings


def create_app() -> FastAPI:
    settings = Settings()
    logging.basicConfig(level=settings.log_level.upper())

    app = FastAPI(title=settings.app_name)
    app.include_router(health_router)
    return app


app = create_app()
