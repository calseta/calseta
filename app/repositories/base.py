"""Base repository providing the DI pattern for all repositories."""

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """
    Base class for all repositories. Receives a SQLAlchemy async session via DI.
    Never imports or creates a session — always receives one as a constructor argument.

    Usage:
        class AlertRepository(BaseRepository):
            async def get_by_uuid(self, uuid: str) -> Alert | None:
                result = await self.db.execute(...)
                return result.scalar_one_or_none()
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
