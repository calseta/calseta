"""Unit tests for BaseRepository generic methods (Chunk 4.3).

These tests do NOT require a running database -- they exercise the
BaseRepository methods in isolation using a mocked AsyncSession and a
minimal SQLAlchemy model (so ``select()`` accepts it as a valid entity).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.repositories.base import BaseRepository

# ---------------------------------------------------------------------------
# Minimal SQLAlchemy model for testing
# ---------------------------------------------------------------------------


class _TestBase(DeclarativeBase):
    pass


class StubModel(_TestBase):
    """Minimal model used only inside this test module."""

    __tablename__ = "_test_base_repo_stub"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[str] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=True)


class StubRepository(BaseRepository[StubModel]):
    model = StubModel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> StubRepository:
    return StubRepository(db=mock_session)


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def _scalar_result(value: object) -> MagicMock:
    """Mock result whose .scalar_one_or_none() returns *value*."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalar_one_result(value: object) -> MagicMock:
    """Mock result whose .scalar_one() returns *value*."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _paginate_results(rows: list[object], total: int) -> list[MagicMock]:
    """Two mock results for paginate's count query + data query."""
    count_result = _scalar_one_result(total)

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    data_result = MagicMock()
    data_result.scalars.return_value = scalars_mock

    return [count_result, data_result]


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        sentinel = StubModel()
        mock_session.execute.return_value = _scalar_result(sentinel)

        result = await repo.get_by_id(42)

        assert result is sentinel
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.return_value = _scalar_result(None)

        result = await repo.get_by_id(999)

        assert result is None
        mock_session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_uuid
# ---------------------------------------------------------------------------


class TestGetByUuid:
    @pytest.mark.asyncio
    async def test_found(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        sentinel = StubModel()
        mock_session.execute.return_value = _scalar_result(sentinel)

        result = await repo.get_by_uuid(uuid4())

        assert result is sentinel
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.return_value = _scalar_result(None)

        result = await repo.get_by_uuid(uuid4())

        assert result is None
        mock_session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# count
# ---------------------------------------------------------------------------


class TestCount:
    @pytest.mark.asyncio
    async def test_no_filters(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.return_value = _scalar_one_result(7)

        result = await repo.count()

        assert result == 7
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_filter(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.return_value = _scalar_one_result(3)

        result = await repo.count(StubModel.name == "test")

        assert result == 3
        mock_session.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# paginate
# ---------------------------------------------------------------------------


class TestPaginate:
    @pytest.mark.asyncio
    async def test_first_page(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        rows = [StubModel(), StubModel()]
        mock_session.execute.side_effect = _paginate_results(rows, total=5)

        data, total = await repo.paginate(page=1, page_size=2)

        assert data == rows
        assert total == 5
        assert mock_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_results(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = _paginate_results([], total=0)

        data, total = await repo.paginate(page=1, page_size=50)

        assert data == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_with_filters(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        rows = [StubModel()]
        mock_session.execute.side_effect = _paginate_results(rows, total=1)

        data, total = await repo.paginate(
            StubModel.name == "filtered", page=1, page_size=10
        )

        assert data == rows
        assert total == 1

    @pytest.mark.asyncio
    async def test_with_ordering(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        rows = [StubModel()]
        mock_session.execute.side_effect = _paginate_results(rows, total=1)

        data, total = await repo.paginate(
            order_by=StubModel.id.desc(), page=1, page_size=10
        )

        assert data == rows
        assert total == 1

    @pytest.mark.asyncio
    async def test_offset_calculation(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        """Page 3 with page_size=10 should yield offset 20.

        We verify the two execute calls happen (count + data) and the
        method completes without error. The offset is baked into the
        Select object passed to session.execute.
        """
        mock_session.execute.side_effect = _paginate_results([], total=25)

        data, total = await repo.paginate(page=3, page_size=10)

        assert total == 25
        assert data == []
        assert mock_session.execute.await_count == 2


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_calls_delete_and_flush(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        obj = StubModel()

        await repo.delete(obj)

        mock_session.delete.assert_awaited_once_with(obj)
        mock_session.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# flush_and_refresh
# ---------------------------------------------------------------------------


class TestFlushAndRefresh:
    @pytest.mark.asyncio
    async def test_returns_same_object(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        obj = StubModel()

        result = await repo.flush_and_refresh(obj)

        assert result is obj
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(obj)

    @pytest.mark.asyncio
    async def test_flush_called_before_refresh(
        self, repo: StubRepository, mock_session: AsyncMock
    ) -> None:
        """flush() must be called before refresh()."""
        obj = StubModel()
        call_order: list[str] = []

        async def track_flush() -> None:
            call_order.append("flush")

        async def track_refresh(_obj: object) -> None:
            call_order.append("refresh")

        mock_session.flush.side_effect = track_flush
        mock_session.refresh.side_effect = track_refresh

        await repo.flush_and_refresh(obj)

        assert call_order == ["flush", "refresh"]
