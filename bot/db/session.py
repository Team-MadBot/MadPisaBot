from contextlib import asynccontextmanager

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def make_engine(url: str):
    if not url.startswith("sqlite+aiosqlite:"):
        raise ValueError("DATABASE_URL должен использовать sqlite+aiosqlite.")
    engine = create_async_engine(url, connect_args={"timeout": 30})

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


class Database:
    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction(self):
        async with self.sessions() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    @asynccontextmanager
    async def read(self):
        async with self.sessions() as session:
            yield session

    async def close(self):
        await self.engine.dispose()
