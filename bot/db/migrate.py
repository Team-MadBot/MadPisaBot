import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from bot.db.session import make_engine

logger = logging.getLogger(__name__)


async def migrate(url: str) -> Path | None:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).with_name("migrations")))
    head = ScriptDirectory.from_config(config).get_current_head()
    engine = make_engine(url)
    backup = None
    try:
        async with engine.connect() as connection:
            revision = await connection.run_sync(lambda c: MigrationContext.configure(c).get_current_revision())
            if revision == head:
                return None
            tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
            await connection.rollback()
            if tables:
                filename = make_url(url).database
                if not filename or filename == ":memory:":
                    raise RuntimeError("Для миграции существующих данных требуется файловая SQLite-БД.")
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
                backup = Path(filename).resolve().with_name(f"{Path(filename).name}.backup-{stamp}")
                # VACUUM INTO takes a consistent SQLite snapshot, including WAL data.
                await connection.exec_driver_sql("VACUUM INTO ?", (str(backup),))
                await connection.commit()
                logger.info("Резервная копия БД: %s", backup)
            await connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                def upgrade(sync_connection):
                    config.attributes["connection"] = sync_connection
                    command.upgrade(config, "head")

                await connection.run_sync(upgrade)
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
    finally:
        await engine.dispose()
    return backup


if __name__ == "__main__":
    from config import database_url

    logging.basicConfig(level=logging.INFO)
    asyncio.run(migrate(database_url))
