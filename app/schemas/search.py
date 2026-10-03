"""Semantic retrieval request and response payloads."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    limit: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    document_id: int
    title: str
    content: str
    category: str | None
    similarity: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
