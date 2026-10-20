from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from sqlalchemy import update

from bot.db import Database
from bot.db.models import FamilyRequest
from bot.handlers.common import display_name, group_identity, identity, integer, reply_long
from bot.services import family
from bot.services.common import GameError, cache_name
from bot.time import utc_now

router = Router(name="family")


@router.message(Command("marry", "divorce", "sex", "orphanage"))
@router.channel_post(Command("marry", "divorce", "sex", "orphanage"))
async def propose(message: types.Message, command: CommandObject, database: Database):
    actor = group_identity(message)
    kind = command.command.lower()
    args = (command.args or "").split()
    target = None
    target_id = child_id = None
    if kind == "marry":
        if len(args) > 1:
            raise GameError("Использование: /marry <id> или /marry ответом на сообщение игрока.")
        if args:
            target_id = integer(args[0], "Укажи корректный ID игрока.")
        elif message.reply_to_message:
            target = identity(message.reply_to_message)
            target_id = target.id
        if target_id == message.bot.id or (isinstance(target, types.User) and target.is_bot):
            raise GameError("Бот не может подтвердить брак.")
    elif kind == "orphanage":
        if len(args) != 1:
            raise GameError("Использование: /orphanage <id ребёнка>. Ребёнок будет удалён навсегда.")
        child_id = integer(args[0], "Укажи корректный ID ребёнка.")
    elif args:
        raise GameError(f"Использование: /{kind} без аргументов.")
    async with database.transaction() as session:
        now = utc_now()
        await family.process_births(session, now, message.chat.id)
        await cache_name(session, actor.id, display_name(actor))
        if target:
            await cache_name(session, target.id, display_name(target))
        request = await family.create_request(
            session, message.chat.id, actor.id, kind, now, target_id=target_id, child_id=child_id,
        )
        text = await family.request_text(session, request)
    keyboard = None
    if request.recipient_id > 0:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="Согласиться", callback_data=f"family:accept:{request.id}"),
            types.InlineKeyboardButton(text="Отказаться", callback_data=f"family:decline:{request.id}"),
        ]])
    try:
        sent = await message.reply(text, reply_markup=keyboard)
    except Exception:
        async with database.transaction() as session:
            await session.execute(update(FamilyRequest).where(
                FamilyRequest.id == request.id, FamilyRequest.status == "pending",
            ).values(status="cancelled"))
        raise
    async with database.transaction() as session:
        await session.execute(update(FamilyRequest).where(FamilyRequest.id == request.id)
                              .values(message_id=sent.message_id))


@router.message(Command("accept", "decline"))
@router.channel_post(Command("accept", "decline"))
async def respond(message: types.Message, command: CommandObject, database: Database):
    actor = group_identity(message)
    args = (command.args or "").split()
    request_id = message_id = None
    if len(args) > 1:
        raise GameError("Укажи один номер предложения или ответь на предложение бота без аргументов.")
    if args:
        request_id = integer(args[0], "Укажи корректный номер предложения.")
    elif message.reply_to_message:
        # The DB mapping proves this is the exact proposal sent by this bot in this chat.
        message_id = message.reply_to_message.message_id
    async with database.transaction() as session:
        now = utc_now()
        await family.process_births(session, now, message.chat.id)
        await cache_name(session, actor.id, display_name(actor))
        result = await family.respond(
            session, message.chat.id, actor.id, now, command.command.lower() == "accept",
            request_id=request_id, message_id=message_id,
        )
    await reply_long(message, result)


@router.callback_query(F.data.startswith("family:"))
async def respond_button(query: types.CallbackQuery, database: Database):
    if not isinstance(query.message, types.Message) or query.message.chat.type == "private":
        raise GameError("Предложение недоступно.")
    parts = query.data.split(":")
    if len(parts) != 3 or parts[1] not in {"accept", "decline"}:
        raise GameError("Неизвестное действие.")
    request_id = integer(parts[2], "Некорректный номер предложения.")
    async with database.transaction() as session:
        now = utc_now()
        await family.process_births(session, now, query.message.chat.id)
        await cache_name(session, query.from_user.id, query.from_user.full_name)
        result = await family.respond(
            session, query.message.chat.id, query.from_user.id, now, parts[1] == "accept",
            request_id=request_id, message_id=query.message.message_id,
        )
    await query.answer("Предложение обработано.")
    await reply_long(query.message, result)
    await query.message.edit_reply_markup(reply_markup=None)


@router.message(Command("namechild"))
@router.channel_post(Command("namechild"))
async def name_child(message: types.Message, command: CommandObject, database: Database):
    actor = group_identity(message)
    args = (command.args or "").split(maxsplit=1)
    if len(args) != 2:
        raise GameError("Использование: /namechild <id ребёнка> <имя>.")
    child_id = integer(args[0], "Укажи корректный ID ребёнка.")
    async with database.transaction() as session:
        await family.process_births(session, utc_now(), message.chat.id)
        result = await family.name_child(session, message.chat.id, actor.id, child_id, args[1])
    await reply_long(message, result)


@router.message(Command("couples"))
@router.channel_post(Command("couples"))
async def couples(message: types.Message, command: CommandObject, database: Database):
    group_identity(message)
    args = (command.args or "").split()
    if len(args) > 2:
        raise GameError("Использование: /couples [duration|children] [страница].")
    order = args[0] if args else "duration"
    page = integer(args[1], "Укажи номер страницы от 1.") if len(args) == 2 else 1
    async with database.transaction() as session:
        now = utc_now()
        await family.process_births(session, now, message.chat.id)
        result = await family.couples(session, message.chat.id, order, page, now)
    await reply_long(message, result)
