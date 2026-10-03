"""Validated LLM output and public incident analysis payloads."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class LLMIncidentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: NonEmptyText
    severity: Literal["low", "medium", "high", "critical"]
    likely_attack_type: NonEmptyText
    recommended_actions: list[NonEmptyText] = Field(min_length=1)


class AnalyzeRequest(BaseModel):
    incident: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=10000)
    ]
    top_k: int = Field(default=5, ge=1, le=10)


class SourceDocument(BaseModel):
    document_id: int
    title: str
    category: str | None
    similarity: float


class AnalyzeResponse(LLMIncidentAnalysis):
    sources: list[SourceDocument]
