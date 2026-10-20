import logging
from contextlib import suppress

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from sqlalchemy import select, update

from bot.db import Database
from bot.db.models import Player
from bot.handlers.common import display_name, identity, integer
from bot.services.common import GameError
from config import owners_id

router = Router(name="payments")
logger = logging.getLogger(__name__)
PREFIX = "KD_RESET_"


@router.message(Command("buy", "pay"))
async def buy_reset(message: types.Message, database: Database):
    if message.sender_chat is not None or message.from_user is None:
        raise GameError(
            "Для покупки используй личный аккаунт. Чтобы сбросить КД каналу или группе, "
            "ответь на их сообщение командой /buy от своего имени."
        )
    target = identity(message.reply_to_message or message)
    async with database.read() as session:
        exists = await session.scalar(select(Player.user_id).where(Player.user_id == target.id).limit(1))
    if exists is None:
        raise GameError(f"Игрок {display_name(target)} ещё не взаимодействовал с ботом. Сначала используй /dick.")
    try:
        await message.bot.send_invoice(
            chat_id=message.from_user.id,
            title=f"Сброс КД для {display_name(target)}"[:32],
            description="Сброс срока /dick во всех чатах. Если КД прошло — звёзды улетят впустую!",
            payload=f"{PREFIX}{target.id}", provider_token="", currency="XTR",
            prices=[types.LabeledPrice(label="Сброс КД", amount=2)],
        )
    except Exception:
        logger.exception("Не удалось отправить счёт")
        raise GameError("Не удалось отправить счёт. Открой личные сообщения с ботом и попробуй ещё раз.") from None
    if message.chat.id != message.from_user.id:
        await message.reply("Отправил Вам счёт за сброс КД в личные сообщения.")


@router.pre_checkout_query()
async def checkout(query: types.PreCheckoutQuery, database: Database):
    try:
        if not query.invoice_payload.startswith(PREFIX):
            raise ValueError
        user_id = int(query.invoice_payload[len(PREFIX):])
        if not -(2**63) <= user_id < 2**63:
            raise ValueError
    except ValueError:
        await query.answer(False, error_message="Неизвестный счёт.")
        return
    async with database.read() as session:
        exists = await session.scalar(select(Player.user_id).where(Player.user_id == user_id).limit(1))
    if exists is None or query.currency != "XTR" or query.total_amount != 2:
        await query.answer(False, error_message="Игрок или параметры счёта не найдены.")
        return
    await query.answer(True)


@router.message(F.successful_payment.invoice_payload.startswith(PREFIX))
async def paid(message: types.Message, database: Database):
    target_id = integer(message.successful_payment.invoice_payload[len(PREFIX):], "Неизвестный счёт.")
    async with database.transaction() as session:
        await session.execute(update(Player).where(Player.user_id == target_id).values(next_dick=0))
    await message.reply("Оплата получена! КД пользователю снято.")
    with suppress(Exception):
        await message.bot.send_message(
            owners_id[0],
            f"Пользователь с ID {message.from_user.id} ({message.from_user.full_name}) "
            f"оплатил снятие КД на /dick для пользователя/канала с ID {target_id}.",
        )
    with suppress(Exception):
        await message.bot.send_message(
            target_id,
            f"Пользователь {message.from_user.full_name} оплатил Вам сброс КД. "
            "Теперь Вы можете вновь прописать /dick во всех чатах с ботом!",
        )


@router.message(Command("refund"), F.from_user.id.in_(owners_id))
async def refund(message: types.Message, command: CommandObject):
    args = (command.args or "").split()
    if len(args) != 2:
        raise GameError("Использование: /refund <id пользователя> <id транзакции>.")
    user_id = integer(args[0], "Укажи корректный ID пользователя.")
    try:
        await message.bot.refund_star_payment(user_id=user_id, telegram_payment_charge_id=args[1])
    except TelegramBadRequest:
        raise GameError("Не найдено невозвращённой транзакции у данного пользователя с данным ID.") from None
    await message.reply("Деньги вернул.")
