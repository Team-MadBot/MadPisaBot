from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert

from bot.db import Database
from bot.db.models import BannedUser
from bot.handlers.common import integer
from bot.services.common import GameError
from config import owners_id

router = Router(name="feedback")


@router.message(Command("feedback"), F.chat.type == "private")
async def feedback(message: types.Message, command: CommandObject, database: Database):
    async with database.read() as session:
        banned = await session.get(BannedUser, message.from_user.id)
        if banned and banned.is_banned:
            return
    if not command.args:
        raise GameError(
            "Напишите сообщение владельцу бота после /feedback.\n"
            "Пример: /feedback Хочу предложить изменение.\n"
            "Если файлов несколько, отправляйте их по одному."
        )
    forwarded = await message.forward(owners_id[0])
    await forwarded.reply(f"ID отправителя: {message.from_user.id}")
    await message.reply("Передал сообщение владельцу!")


@router.message(Command("banfeedback", "unbanfeedback"), F.from_user.id.in_(owners_id))
async def feedback_ban(message: types.Message, command: CommandObject, database: Database):
    args = (command.args or "").split()
    if len(args) != 1:
        raise GameError(f"Использование: /{command.command} <id>.")
    user_id = integer(args[0], "Укажи корректный ID.")
    banned = command.command.lower() == "banfeedback"
    async with database.transaction() as session:
        if banned:
            await session.execute(insert(BannedUser).values(user_id=user_id, is_banned=1)
                                  .on_conflict_do_update(index_elements=[BannedUser.user_id], set_={"is_banned": 1}))
        else:
            await session.execute(delete(BannedUser).where(BannedUser.user_id == user_id))
    await message.reply("Уничтожено!" if banned else "Реабилитирован!")
