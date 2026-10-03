"""Shared HTTP dependencies."""

from fastapi import Request

from app.services.embedding_service import EmbeddingService
from app.services.llm_service import LLMService


def get_embedding_service(request: Request) -> EmbeddingService:
    return request.app.state.embedding_service


def get_llm_service(request: Request) -> LLMService:
    return request.app.state.llm_service
