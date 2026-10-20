from aiogram import BaseMiddleware, types

from bot.services.common import GameError


def identity(message: types.Message):
    actor = message.sender_chat or message.from_user
    if actor is None:
        raise GameError("Не удалось определить отправителя.")
    return actor


def display_name(actor) -> str:
    return actor.full_name if isinstance(actor, types.User) else (actor.title or str(actor.id))


def group_identity(message: types.Message):
    if message.chat.type == "private":
        raise GameError("Данная команда доступна только в группах и каналах с ботом.")
    return identity(message)


def integer(value: str, usage: str) -> int:
    try:
        number = int(value)
        if not -(2**63) <= number < 2**63:
            raise ValueError
        return number
    except ValueError:
        raise GameError(usage) from None


def chunks(text: str, limit: int = 3500) -> list[str]:
    result = []
    current = ""
    size = 0
    for line in text.splitlines(keepends=True):
        line_size = len(line.encode("utf-16-le")) // 2
        if size + line_size > limit and current:
            result.append(current)
            current, size = "", 0
        if line_size > limit:
            for char in line:
                char_size = 2 if ord(char) > 0xFFFF else 1
                if size + char_size > limit:
                    result.append(current)
                    current, size = "", 0
                current += char
                size += char_size
        else:
            current += line
            size += line_size
    if current.strip():
        result.append(current)
    return result


async def reply_long(message: types.Message, text: str):
    for part in chunks(text):
        await message.reply(part)


class GameErrorMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except GameError as error:
            if isinstance(event, types.CallbackQuery):
                await event.answer(str(error)[:180], show_alert=True)
            elif isinstance(event, types.Message):
                await reply_long(event, str(error))
