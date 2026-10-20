import asyncio
import json
import logging

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from sqlalchemy import select

from bot.db import Database
from bot.db.models import Player
from bot.handlers.common import display_name, group_identity, identity, integer
from bot.services.common import GameError, cache_name, get_player
from bot.services.family import process_births
from bot.time import utc_now
from config import owners_id

router = Router(name="admin")
logger = logging.getLogger(__name__)


@router.message(Command("giveuserlink"))
async def give_user_link(message: types.Message, command: CommandObject):
    args = (command.args or "").split()
    if len(args) != 1:
        raise GameError("Укажи ID пользователя: /giveuserlink <id>.")
    user_id = integer(args[0], "Введи корректный ID!")
    await message.reply(f'<a href="tg://user?id={user_id}">Тык</a>', parse_mode="HTML")


@router.message(Command("export"), F.chat.type != "private")
async def export_stats(message: types.Message, database: Database):
    if message.sender_chat or message.from_user is None or not isinstance(
        await message.chat.get_member(message.from_user.id), types.ChatMemberOwner,
    ):
        raise GameError(
            "Данную команду может использовать только владелец группы. "
            "Выдайте боту админку и отключите анонимность."
        )
    async with database.read() as session:
        users = await session.scalars(select(Player).where(Player.chat_id == message.chat.id))
        result = [
            {"chat_id": user.chat_id, "user_id": user.user_id, "length": user.length, "next_dick": user.next_dick}
            for user in users
        ]
    try:
        await message.bot.send_document(
            message.from_user.id,
            types.BufferedInputFile(json.dumps(result, ensure_ascii=False, indent=4).encode(), filename="stats.json"),
            caption=(
                "Вот сохранение для Вашей группы.\n\n"
                "- chat_id — ID чата;\n"
                "- user_id — ID пользователя, группы или канала;\n"
                "- length — длина в сантиметрах;\n"
                "- next_dick — время снятия задержки в UNIX-формате "
                "(секунды с 1 января 1970 г. 00:00:00 UTC)."
            ),
        )
    except Exception:
        logger.exception("Ошибка отправки экспорта")
        raise GameError("Не удалось отправить экспорт в ЛС. Откройте личные сообщения с ботом и попробуйте ещё раз.") from None
    await message.reply("Бот отправил экспорт Вам в личные сообщения.")


@router.message(Command("editsize"), F.from_user.id.in_(owners_id))
@router.channel_post(Command("editsize"), F.from_user.id.in_(owners_id))
async def edit_size(message: types.Message, command: CommandObject, database: Database):
    group_identity(message)
    args = (command.args or "").split()
    if not 1 <= len(args) <= 2 or (len(args) == 1 and not message.reply_to_message):
        raise GameError("Использование: /editsize <изменение> <id> или ответом на сообщение игрока.")
    amount = integer(args[0], "Укажи целое изменение размера.")
    target = identity(message.reply_to_message) if message.reply_to_message else None
    user_id = integer(args[1], "Укажи корректный ID!") if len(args) == 2 else target.id
    async with database.transaction() as session:
        await process_births(session, utc_now(), message.chat.id)
        player = await get_player(session, message.chat.id, user_id)
        player.length += amount
        if target and target.id == user_id:
            await cache_name(session, user_id, display_name(target))
    await message.reply(f"Размер пиписьки изменён у игрока с ID {user_id}.")


@router.message(Command("sendalert"), F.from_user.id.in_(owners_id))
async def send_alert(message: types.Message, command: CommandObject, database: Database):
    if not command.args:
        raise GameError("А чё рассылать-то?")
    alert = message.md_text.split(maxsplit=1)[1]
    async with database.read() as session:
        chat_ids = list(await session.scalars(select(Player.chat_id).distinct()))
    progress = await message.reply("Начинаю рассылку...")
    for chat_id in chat_ids:
        try:
            await message.bot.send_message(chat_id, "*Объявление:*\n\n" + alert, parse_mode="MarkdownV2")
        except Exception:
            logger.exception("Ошибка рассылки в чат %s", chat_id)
        await asyncio.sleep(0.034)
    await progress.edit_text("Рассылка завершена!")


@router.message(Command("sendto"), F.from_user.id.in_(owners_id))
async def send_to(message: types.Message, command: CommandObject):
    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        raise GameError("Использование: /sendto <id или @username> <сообщение>.")
    destination = args[0]
    try:
        destination = int(destination)
    except ValueError:
        pass
    text = message.md_text.split(maxsplit=2)[2]
    await message.bot.send_message(
        destination, "*Сообщение от владельца бота:*\n\n" + text, parse_mode="MarkdownV2",
    )
    await message.reply("Ответил.")
