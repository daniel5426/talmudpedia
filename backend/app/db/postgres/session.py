from __future__ import annotations

import logging
import time
from typing import AsyncGenerator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .engine import sessionmaker

logger = logging.getLogger(__name__)
DB_SESSION_SLOW_LOG_THRESHOLD_MS = 250


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Request-scoped async DB session with resilient teardown."""
    started_at = time.perf_counter()
    session = sessionmaker()
    created_ms = int((time.perf_counter() - started_at) * 1000)
    if created_ms >= DB_SESSION_SLOW_LOG_THRESHOLD_MS:
        logger.warning("db.session.create slow_ms=%s", created_ms)
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
            close_started_at = time.perf_counter()
            await session.close()
            close_ms = int((time.perf_counter() - close_started_at) * 1000)
            total_ms = int((time.perf_counter() - started_at) * 1000)
            if close_ms >= DB_SESSION_SLOW_LOG_THRESHOLD_MS or total_ms >= DB_SESSION_SLOW_LOG_THRESHOLD_MS:
                logger.warning("db.session.close close_ms=%s total_ms=%s", close_ms, total_ms)
        except SQLAlchemyError:
            logger.warning("DB session close failed; invalidating connection", exc_info=True)
            try:
                await session.invalidate()
            except SQLAlchemyError:
                logger.warning("DB session invalidate failed after close failure", exc_info=True)
