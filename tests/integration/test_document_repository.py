import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import EMBEDDING_DIMENSION
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentCreate

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture
def embedding() -> list[float]:
    return [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)


async def test_create_document(
    db_session: AsyncSession, embedding: list[float]
) -> None:
    repository = DocumentRepository()
    data = DocumentCreate(
        title="Phishing playbook", content="Inspect attachments.", category="phishing"
    )

    async with db_session.begin():
        document = await repository.create(db_session, data, embedding)

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
    assert stored.embedding == pytest.approx(embedding)


async def test_get_existing_document(
    db_session: AsyncSession, embedding: list[float]
) -> None:
    repository = DocumentRepository()
    created = await repository.create(
        db_session,
        DocumentCreate(title="Playbook", content="Keep evidence."),
        embedding,
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


async def test_list_documents(db_session: AsyncSession, embedding: list[float]) -> None:
    repository = DocumentRepository()
    # Existing rows need not be deleted to check ordering and pagination.
    existing_count = await db_session.scalar(select(func.count()).select_from(Document))
    created = [
        await repository.create(
            db_session,
            DocumentCreate(title=f"Playbook {index}", content="Keep evidence."),
            embedding,
        )
        for index in range(3)
    ]

    documents = await repository.list(db_session, limit=2, offset=existing_count)
    remaining = await repository.list(db_session, limit=2, offset=existing_count + 2)
    empty = await repository.list(db_session, limit=2, offset=existing_count + 3)

    assert [document.id for document in documents] == [created[0].id, created[1].id]
    assert [document.id for document in remaining] == [created[2].id]
    assert empty == []


async def test_transaction_rollback_on_error(
    db_session: AsyncSession, embedding: list[float]
) -> None:
    repository = DocumentRepository()

    with pytest.raises(RuntimeError, match="Abort document creation"):
        async with db_session.begin():
            document = await repository.create(
                db_session,
                DocumentCreate(title="Rolled back", content="Keep evidence."),
                embedding,
            )
            document_id = document.id
            raise RuntimeError("Abort document creation")

    assert await repository.get_by_id(db_session, document_id) is None
    # A rolled-back session remains usable for the next transaction.
    document = await repository.create(
        db_session,
        DocumentCreate(title="After rollback", content="Keep evidence."),
        embedding,
    )
    assert document.id > 0


async def test_semantic_search_order_and_limit(db_session: AsyncSession) -> None:
    repository = DocumentRepository()
    # The dedicated test DB should contain no committed vectors from other suites.
    count = await db_session.scalar(
        select(func.count())
        .select_from(Document)
        .where(Document.embedding.is_not(None))
    )
    assert count == 0, "Use a test database without committed embedded documents"
    first = await repository.create(
        db_session,
        DocumentCreate(title="Closest", content="First document."),
        [1.0, 0.0] + [0.0] * 382,
    )
    second = await repository.create(
        db_session,
        DocumentCreate(title="Less similar", content="Second document."),
        [0.0, 1.0] + [0.0] * 382,
    )
    query = [1.0, 0.0] + [0.0] * 382

    matches = await repository.search_similar(db_session, query, limit=2)
    limited = await repository.search_similar(db_session, query, limit=1)

    assert [document.id for document, _ in matches] == [first.id, second.id]
    assert [distance for _, distance in matches] == pytest.approx([0.0, 1.0])
    assert [1.0 - distance for _, distance in matches] == pytest.approx([1.0, 0.0])
    assert [document.id for document, _ in limited] == [first.id]


async def test_rejects_new_document_without_embedding(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        async with db_session.begin():
            db_session.add(Document(title="Missing vector", content="Text"))
            await db_session.flush()
