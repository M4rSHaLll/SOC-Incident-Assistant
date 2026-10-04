"""Document persistence without transaction ownership."""

from __future__ import annotations

import builtins

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import Label

from app.models.document import Document
from app.schemas.document import DocumentCreate


class DocumentRepository:
    async def create(
        self, session: AsyncSession, data: DocumentCreate, embedding: list[float]
    ) -> Document:
        document = Document(**data.model_dump(), embedding=embedding)
        session.add(document)
        await session.flush()
        return document

    async def get_by_id(
        self, session: AsyncSession, document_id: int
    ) -> Document | None:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self, session: AsyncSession, limit: int, offset: int
    ) -> list[Document]:
        result = await session.execute(
            select(Document).order_by(Document.id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def search_similar(
        self, session: AsyncSession, query_embedding: builtins.list[float], limit: int
    ) -> builtins.list[tuple[Document, float]]:
        distance: Label[float] = Document.embedding.cosine_distance(
            query_embedding
        ).label("distance")
        result = await session.execute(
            select(Document, distance)
            .where(Document.embedding.is_not(None))
            .order_by(distance, Document.id)
            .limit(limit)
        )
        return [(document, float(distance)) for document, distance in result.all()]
