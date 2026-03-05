from __future__ import annotations

import logging
from typing import AsyncGenerator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .engine import sessionmaker

logger = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped async DB session with resilient teardown."""
    session = sessionmaker()
    try:
        yield session
    except Exception:
        try:
            if session.in_transaction():
                await session.rollback()
        except SQLAlchemyError:
            logger.warning("DB session rollback failed during request exception handling", exc_info=True)
            try:
                await session.invalidate()
            except SQLAlchemyError:
                logger.warning("DB session invalidate failed after rollback failure", exc_info=True)
        raise
    finally:
        try:
            await session.close()
        except SQLAlchemyError:
            logger.warning("DB session close failed; invalidating connection", exc_info=True)
            try:
                await session.invalidate()
            except SQLAlchemyError:
                logger.warning("DB session invalidate failed after close failure", exc_info=True)
