"""Document use cases and transaction boundaries."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate


class DocumentNotFoundError(Exception):
    def __init__(self, document_id: int) -> None:
        super().__init__(f"Document {document_id} not found")


class DocumentService:
    def __init__(
        self, session: AsyncSession, repository: DocumentRepository
    ) -> None:
        self.session = session
        self.repository = repository

    async def create_document(self, data: DocumentCreate) -> Document:
        async with self.session.begin():
            document = await self.repository.create(self.session, data)
        return document

    async def get_document(self, document_id: int) -> Document:
        document = await self.repository.get_by_id(self.session, document_id)
        if document is None:
            raise DocumentNotFoundError(document_id)
        return document

    async def list_documents(self, limit: int, offset: int) -> list[Document]:
        return await self.repository.list(self.session, limit, offset)
