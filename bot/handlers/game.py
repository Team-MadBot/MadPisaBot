from aiogram import Router, types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from sqlalchemy import select

from bot.db import Database
from bot.db.models import Player, UserCache
from bot.handlers.common import display_name, group_identity, identity, reply_long
from bot.services import game
from bot.services.common import cache_name
from bot.services.family import process_births
from bot.time import utc_now

router = Router(name="game")


@router.message(Command("dick"))
@router.channel_post(Command("dick"))
async def dick(message: types.Message, database: Database):
    actor = group_identity(message)
    async with database.transaction() as session:
        now = utc_now()
        await process_births(session, now, message.chat.id)
        await cache_name(session, actor.id, display_name(actor))
        result = await game.play(session, message.chat.id, actor.id, display_name(actor), now)
    await reply_long(message, result)


@router.message(Command("info"))
@router.channel_post(Command("info"))
async def info(message: types.Message, database: Database):
    group_identity(message)
    actor = identity(message.reply_to_message or message)
    async with database.transaction() as session:
        now = utc_now()
        await process_births(session, now, message.chat.id)
        await cache_name(session, actor.id, display_name(actor))
        result = await game.info(session, message.chat.id, actor.id, display_name(actor), now)
    await reply_long(message, result)


@router.message(Command("top", "top_dick"))
@router.channel_post(Command("top", "top_dick"))
async def top(message: types.Message, database: Database):
    group_identity(message)
    async with database.read() as session:
        leaders = (await session.execute(
            select(Player.user_id, UserCache.user_name).outerjoin(UserCache, Player.user_id == UserCache.user_id)
            .where(Player.chat_id == message.chat.id)
            .order_by(Player.length.desc(), Player.user_id).limit(15)
        )).all()
        missing = [user_id for user_id, name in leaders if name is None]
    resolved = []
    for user_id in missing:
        try:
            chat = await message.bot.get_chat(user_id)
        except TelegramAPIError:
            continue
        resolved.append((user_id, chat.full_name))
    async with database.transaction() as session:
        await process_births(session, utc_now(), message.chat.id)
        for user_id, name in resolved:
            await cache_name(session, user_id, name)
        result = await game.top_players(session, message.chat.id)
    await reply_long(message, result)
