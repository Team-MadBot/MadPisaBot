import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from sqlalchemy import select, update

from bot.db import Database
from bot.db.models import Child
from bot.services.common import player_name
from bot.services.family import process_births
from bot.time import moscow_time, utc_now

logger = logging.getLogger(__name__)


async def birth_tick(database: Database, bot: Bot):
    async with database.transaction() as session:
        now = utc_now()
        await process_births(session, now)
        children = list(await session.scalars(select(Child).where(
            Child.notified_at.is_(None), Child.notify_after <= now,
        ).order_by(Child.born_at, Child.id).limit(20)))
        notifications = []
        for child in children:
            first = await player_name(session, child.first_parent_id)
            second = await player_name(session, child.second_parent_id)
            text = (
                f"👨‍👨‍👦 У {first} и {second} родился {child.display_name} (ID {child.id})!\n"
                f"Дата рождения: {moscow_time(child.born_at)}.\n"
            )
            if child.marriage_id is None:
                text += "После развода ребёнок находится в детдоме до восстановления брака."
            else:
                text += f"Дать имя: /namechild {child.id} <имя>. Ребёнок готов сыграть вместе с родителем через /dick."
            notifications.append((child.id, child.chat_id, text))
            child.notify_after = now + 300
    for child_id, chat_id, text in notifications:
        try:
            await bot.send_message(chat_id, text)
        except TelegramRetryAfter as error:
            async with database.transaction() as session:
                await session.execute(update(Child).where(Child.id == child_id).values(
                    notify_after=utc_now() + max(60, error.retry_after),
                ))
            # Telegram's flood limit may apply to the whole bot.
            break
        except Exception:
            logger.exception("Не удалось отправить уведомление о рождении ребёнка %s", child_id)
        else:
            async with database.transaction() as session:
                await session.execute(update(Child).where(Child.id == child_id).values(notified_at=utc_now()))
        await asyncio.sleep(0.05)


async def birth_worker(database: Database, bot: Bot):
    while True:
        try:
            await birth_tick(database, bot)
        except Exception:
            logger.exception("Ошибка фоновой обработки родов")
        await asyncio.sleep(60)
