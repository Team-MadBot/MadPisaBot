import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher

from bot.db import Database
from bot.db.migrate import migrate
from bot.handlers import admin, family, feedback, game, migration, payments
from bot.handlers.common import GameErrorMiddleware
from bot.services.family import process_births
from bot.time import utc_now
from bot.worker import birth_worker
from config import bot_token, database_url


def create_dispatcher(database: Database) -> Dispatcher:
    dispatcher = Dispatcher(database=database)
    for observer in (dispatcher.message, dispatcher.channel_post, dispatcher.callback_query):
        observer.outer_middleware(GameErrorMiddleware())
    dispatcher.include_routers(
        migration.router, game.router, family.router, admin.router, payments.router, feedback.router,
    )
    return dispatcher


async def main():
    logging.basicConfig(level=logging.INFO)
    if not bot_token:
        raise RuntimeError("Задайте BOT_TOKEN в .env или переменных окружения.")
    bot = Bot(token=bot_token)
    database = None
    worker = None
    try:
        await migrate(database_url)
        database = Database(database_url)
        async with database.transaction() as session:
            await process_births(session, utc_now())
        dispatcher = create_dispatcher(database)
        worker = asyncio.create_task(birth_worker(database, bot), name="birth-worker")
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        if worker:
            worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker
        if database:
            await database.close()
        await bot.session.close()
