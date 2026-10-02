"""Document API payloads."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class DocumentCreate(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    category: str | None = Field(default=None, max_length=100)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    category: str | None
    created_at: datetime
