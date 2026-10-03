"""Incident analysis HTTP endpoint and application error mapping."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_embedding_service, get_llm_service
from app.db.database import get_db_session
from app.repositories.document_repository import DocumentRepository
from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from app.services.analysis_service import AnalysisService, KnowledgeBaseEmptyError
from app.services.embedding_service import EmbeddingService
from app.services.llm_service import (
    LLMConfigurationError,
    LLMProviderError,
    LLMResponseError,
    LLMService,
)

router = APIRouter(prefix="/api/v1/analyze", tags=["analysis"])


def get_analysis_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    embedding_service: Annotated[EmbeddingService, Depends(get_embedding_service)],
    llm_service: Annotated[LLMService, Depends(get_llm_service)],
) -> AnalysisService:
    return AnalysisService(
        session,
        DocumentRepository(),
        embedding_service,
        llm_service,
        request.app.state.rag_max_context_chars,
    )


@router.post("", response_model=AnalyzeResponse)
async def analyze_incident(
    data: AnalyzeRequest,
    service: Annotated[AnalysisService, Depends(get_analysis_service)],
) -> AnalyzeResponse:
    try:
        return await service.analyze(data.incident, data.top_k)
    except KnowledgeBaseEmptyError:
        raise HTTPException(
            status_code=409,
            detail="No relevant knowledge base documents are available",
        ) from None
    except LLMConfigurationError:
        raise HTTPException(
            status_code=503, detail="LLM provider is not configured"
        ) from None
    except LLMProviderError:
        raise HTTPException(
            status_code=502, detail="LLM provider request failed"
        ) from None
    except LLMResponseError:
        raise HTTPException(
            status_code=502, detail="LLM provider returned an invalid analysis"
        ) from None
