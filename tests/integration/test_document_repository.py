import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_create_document(db_session: AsyncSession) -> None:
    repository = DocumentRepository()
    data = DocumentCreate(
        title="Phishing playbook", content="Inspect attachments.", category="phishing"
    )

    async with db_session.begin():
        document = await repository.create(db_session, data)

    assert document.id > 0
    assert document.title == data.title
    assert document.content == data.content
    assert document.category == data.category
    assert document.created_at.utcoffset() is not None
    document_id = document.id
    db_session.expunge_all()
    stored = await repository.get_by_id(db_session, document_id)
    assert stored is not None
    assert stored.title == data.title


async def test_get_existing_document(db_session: AsyncSession) -> None:
    repository = DocumentRepository()
    created = await repository.create(
        db_session, DocumentCreate(title="Playbook", content="Keep evidence.")
    )
    document_id = created.id
    db_session.expunge_all()

    document = await repository.get_by_id(db_session, document_id)

    assert document is not None
    assert document.id == document_id
    assert document.title == "Playbook"
    assert document.content == "Keep evidence."
    assert document.category is None


async def test_get_missing_document(db_session: AsyncSession) -> None:
    repository = DocumentRepository()
    highest_id = await db_session.scalar(
        select(func.coalesce(func.max(Document.id), 0))
    )

    document = await repository.get_by_id(db_session, highest_id + 1)

    assert document is None


async def test_list_documents(db_session: AsyncSession) -> None:
    repository = DocumentRepository()
    # Existing rows need not be deleted to check ordering and pagination.
    existing_count = await db_session.scalar(select(func.count()).select_from(Document))
    created = [
        await repository.create(
            db_session,
            DocumentCreate(title=f"Playbook {index}", content="Keep evidence."),
        )
        for index in range(3)
    ]

    documents = await repository.list(db_session, limit=2, offset=existing_count)
    remaining = await repository.list(db_session, limit=2, offset=existing_count + 2)
    empty = await repository.list(db_session, limit=2, offset=existing_count + 3)

    assert [document.id for document in documents] == [created[0].id, created[1].id]
    assert [document.id for document in remaining] == [created[2].id]
    assert empty == []


async def test_transaction_rollback_on_error(db_session: AsyncSession) -> None:
    repository = DocumentRepository()

    with pytest.raises(RuntimeError, match="Abort document creation"):
        async with db_session.begin():
            document = await repository.create(
                db_session,
                DocumentCreate(title="Rolled back", content="Keep evidence."),
            )
            document_id = document.id
            raise RuntimeError("Abort document creation")

    assert await repository.get_by_id(db_session, document_id) is None
    # A rolled-back session remains usable for the next transaction.
    document = await repository.create(
        db_session, DocumentCreate(title="After rollback", content="Keep evidence.")
    )
    assert document.id > 0
