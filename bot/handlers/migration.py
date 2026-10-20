import logging

from aiogram import F, Router, types

from bot.db import Database
from bot.services.chat_migration import migrate_chat
from bot.services.family import process_births
from bot.time import utc_now

router = Router(name="chat_migration")
logger = logging.getLogger(__name__)


@router.message(F.migrate_to_chat_id | F.migrate_from_chat_id)
async def migrated(message: types.Message, database: Database):
    if message.migrate_to_chat_id:
        old_id, new_id = message.chat.id, message.migrate_to_chat_id
    else:
        old_id, new_id = message.migrate_from_chat_id, message.chat.id
    async with database.transaction() as session:
        await process_births(session, utc_now(), old_id)
        await migrate_chat(session, old_id, new_id)
    logger.info("Чат перенесён: %s -> %s", old_id, new_id)
