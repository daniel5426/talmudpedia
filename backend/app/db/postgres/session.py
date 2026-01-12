from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from .engine import sessionmaker

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()
