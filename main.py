import asyncio
import logging
import random
import sqlite3
import time
import traceback

from contextlib import suppress
from typing import Optional

from aiogram import Bot, Dispatcher, F, exceptions, types
from aiogram.filters import Command
from aiogram.types import ContentType, LabeledPrice, PreCheckoutQuery

from config import bot_token, owners_id

logging.basicConfig(level=logging.INFO)

bot = Bot(token=bot_token)
dp = Dispatcher()
db = sqlite3.connect("database.db", autocommit=True, check_same_thread=False)
db.row_factory = sqlite3.Row
cur = db.cursor()
ONE_WEEK_IN_SECONDS = 3600 * 24 * 7

cur.execute(
    """CREATE TABLE IF NOT EXISTS user (
        chat_id INTEGER,
        user_id INTEGER,
        length INTEGER,
        next_dick INTEGER
    )
    """
)
cur.execute(
    """CREATE TABLE IF NOT EXISTS user_cache (
        user_id INTEGER UNIQUE NOT NULL,
        user_name TEXT
    )
    """
)
cur.execute(
    """CREATE TABLE IF NOT EXISTS banned_user (
        user_id INTEGER UNIQUE NOT NULL,
        is_banned INTEGER NOT NULL DEFAULT(1)
    )"""
)


def get_top_users(chat_id: int, limit: Optional[int] = None):
    cur.execute(f"""SELECT * FROM user WHERE chat_id = {chat_id} ORDER BY length DESC""" + (f" LIMIT {limit}" if limit is not None else ""))
    return list(map(dict, cur.fetchall()))


def is_banned_user(user_id: int):
    db_user = cur.execute("SELECT * FROM banned_user WHERE user_id = ?", (user_id, )).fetchone()
    return db_user is not None and db_user['is_banned']


@dp.message(F.migrate_to_chat_id)
@dp.message(F.migrate_from_chat_id)
async def migrate_to_chat_id_handler(message: types.Message):
    old_id, new_id = message.chat.id, (message.migrate_to_chat_id or message.migrate_from_chat_id)
    cur.execute(
        """UPDATE user SET chat_id = ? WHERE chat_id = ?""",
        (new_id, old_id)
    )
    cur.execute(
        """UPDATE user SET user_id = ? WHERE user_id = ?""",
        (new_id, old_id)
    )
    cur.execute(
        """UPDATE user_cache SET user_id = ? WHERE user_id = ?""",
        (new_id, old_id)
    )


@dp.message(Command("dick"))
@dp.channel_post(Command("dick"))
async def dick(message: types.Message):
    if message.chat.type == "private":
        return await message.reply("Данная команда доступна только в группах с ботом.")

    tg_user = message.sender_chat or message.from_user
    assert tg_user is not None

    cur.execute(
        f"""SELECT * FROM user WHERE user_id = {tg_user.id} AND chat_id = {message.chat.id}"""
    )

    user = dict(
        cur.fetchone()
        or {
            "chat_id": message.chat.id,
            "user_id": tg_user.id,
            "length": 0,
            "next_dick": 0,
            "fake": True,
        }
    )
    cur.execute(
        "SELECT * FROM user_cache WHERE user_id = ?", (tg_user.id,)
    )
    user_cache = cur.fetchone()
    if user_cache is None:
        cur.execute(
            "INSERT INTO user_cache (user_id, user_name) VALUES (?, ?)",
            (tg_user.id, tg_user.full_name)
        )
    else:
        cur.execute(
            "UPDATE user_cache SET user_name = ? WHERE user_id = ?",
            (tg_user.full_name, tg_user.id)
        )
    if user["next_dick"] > time.time():
        remaining = user["next_dick"] - time.time()
        return await message.reply(
            f"Ты уже играл!\nОжидай ещё {round(remaining // 3600)} часов, {round(remaining % 3600 // 60)} минут и {round(remaining % 3600 % 60)} секунд."
        )
    
    amount = int(random.randint(-5, 10))

    text = f"{tg_user.full_name}, твой писюн увеличился на {amount} см."
    if amount == 0:
        text = f"{tg_user.full_name}, твой писюн не изменился."
    if amount < 0:
        text = f"{tg_user.full_name}, твой писюн сократился на {amount * -1} см."

    next_dick = message.date.timestamp() + 3600 * 12
    print(next_dick)
    print(message.date)

    if user.get("fake", False):
        cur.execute(
            f"""INSERT INTO user (chat_id, user_id, length, next_dick) VALUES
            ({message.chat.id}, {tg_user.id}, {amount}, {next_dick})"""
        )
    else:
        cur.execute(
            f"""UPDATE user SET length = {user['length'] + amount}, next_dick = {next_dick} 
            WHERE user_id = {tg_user.id} AND chat_id = {message.chat.id}"""
        )

    chat_users = get_top_users(chat_id=message.chat.id)
    for count, u in enumerate(chat_users, start=1):
        if u["user_id"] == tg_user.id:
            break

    await message.reply(
        f"{text}\nТеперь размер составляет {(user['length'] + amount):,} см.\n"
        f"Теперь ты занимаешь {count} место в топе.\nСледующая попытка через 12 часов (с момента написания команды)."
    )


@dp.message(Command("info"))
@dp.channel_post(Command("info"))
async def info(message: types.Message):
    if message.chat.type == "private":
        return await message.reply("Данная команда доступна только в группах с ботом.")

    user = (
        (message.sender_chat or message.from_user)
        if message.reply_to_message is None
        else (
            message.reply_to_message.sender_chat or message.reply_to_message.from_user
        )
    )
    cur.execute(
        f"""SELECT * FROM user WHERE user_id = {user.id} AND chat_id = {message.chat.id}"""
    )

    db_user = cur.fetchone()
    if db_user is None:
        text = (
            "Этот игрок ещё ни разу не играл, поэтому его волына равна 0 см. Скажи ему использовать /dick для игры."
            if message.reply_to_message
            else "Ты ещё ни разу не играл, поэтому твоя волына равна 0 см. Используй /dick для игры."
        )
        return await message.reply(text)

    remaining = (db_user["next_dick"] or 0) - round(time.time())
    remaining_text = f"через {round(remaining // 3600)} часов, {round(remaining % 3600 // 60)} минут и {round(remaining % 3600 % 60)} секунд."
    if remaining <= 0:
        remaining_text = "сейчас!"

    chat_users = get_top_users(message.chat.id)
    for count, u in enumerate(chat_users, start=1):
        if u["user_id"] == user.id:
            break

    thing_name = (
        "твой писюн эквивалентен"
        if db_user["length"] >= 0
        else "в твою пизду поместится"
    )
    text = (
        f"{user.full_name}, {thing_name} {abs(db_user['length']):,} см.\n"
        f"Ты занимаешь {count} место в топе.\n"
        f"Следующий /dick: {remaining_text}"
    )

    await message.reply(text)
    cur.execute(
        "SELECT * FROM user_cache WHERE user_id = ?", (user.id,)
    )
    user_cache = cur.fetchone()
    if user_cache is None:
        cur.execute(
            "INSERT INTO user_cache (user_id, user_name) VALUES (?, ?)",
            (user.id, user.full_name)
        )
    else:
        cur.execute(
            "UPDATE user_cache SET user_name = ? WHERE user_id = ?",
            (user.full_name, user.id)
        )


@dp.message(Command("top", "top_dick"))
@dp.channel_post(Command("top", "top_dick"))
async def top(message: types.Message):
    if message.chat.type == "private":
        return await message.reply("Данная команда доступна только в группах с ботом.")

    users = get_top_users(message.chat.id, limit=15)

    text = "Топ 15 пипис:\n\n"
    count = 0
    for count, user in enumerate(users, start=1):
        user_name = None
        cur.execute(
            "SELECT * FROM user_cache WHERE user_id = ?", (user["user_id"],)
        )
        user_cache = cur.fetchone()
        if user_cache is not None:
            user_name = user_cache["user_name"]
        else:
            try:
                user_name = (await bot.get_chat(user["user_id"])).full_name
            except exceptions.TelegramBadRequest:
                traceback.print_exc()
        text += f"{count}. {user_name or 'Неизвестный'}: {user['length']:,} см.\n"
        if user_cache is None and user_name is not None:
            cur.execute(
                "INSERT INTO user_cache (user_id, user_name) VALUES (?, ?)", 
                (user["user_id"], user_name)
            )

    await message.reply(text)


@dp.message(Command("giveuserlink"))
async def giveuserlink(message: types.Message):
    args = message.text.split(" ")

    if len(args) < 1:
        return await message.reply("Введи ID пользователя!")

    try:
        int(args[1])
    except ValueError:
        return await message.reply("Введи корректный ID!")

    await message.reply(f"[Тык](tg://user?id={args[1]})", parse_mode="Markdown")


@dp.message(Command("editsize"), F.from_user.id.in_(owners_id))
@dp.channel_post(Command("editsize"), F.from_user.id.in_(owners_id))
async def editsize(message: types.Message):
    args = message.text.split(" ")
    if len(args) < 2:
        return await message.reply("Введи, на сколько см изменить")

    if message.reply_to_message is None and len(args) < 3:
        return await message.reply(
            "Ответь на сообщение человека, кому надо изменить размер, либо укажите ID следующим аргументом!"
        )
    if len(args) < 3:
        args.append(0)
    try:
        int(args[1])
        int(args[2])
    except ValueError:
        return await message.reply("Невозможно перевести один из аргументов в число!")

    user = (
        int(args[2])
        or (
            message.reply_to_message.sender_chat or message.reply_to_message.from_user
        ).id
    )

    cur.execute(
        "SELECT * FROM user WHERE user_id = ? AND chat_id = ?", (user, message.chat.id)
    )
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO user (chat_id, user_id, length) VALUES (?, ?, ?)",
            (message.chat.id, user, int(args[1])),
        )
    else:
        cur.execute(
            "UPDATE user SET length = length + ? WHERE chat_id = ? AND user_id = ?",
            (args[1], message.chat.id, user),
        )

    await message.reply(
        f"Размер пиписьки изменён у {'пользователя с ID ' + str(user) if message.reply_to_message is None else (
            message.reply_to_message.sender_chat or message.reply_to_message.from_user
        ).full_name}"
    )


@dp.message(Command("buy"))
async def buy_kd_reset(message: types.Message):
    if message.chat.id != message.from_user.id:
        return await message.reply("Покупка возможна только в личных сообщениях бота.")

    await message.reply_invoice(
        title="Сброс кд",
        description="Сброс срока /dick. Если КД прошло - звёзды улетят впустую!!!!",
        payload=f"KD_RESET_{(message.sender_chat or message.from_user).id}",
        provider_token=None,
        is_flexible=False,
        currency="XTR",
        prices=[LabeledPrice(label="Сброс КД", amount=2)],
    )


@dp.pre_checkout_query()
async def handle_pre_checkout(query: PreCheckoutQuery):
    cur.execute(
        "SELECT * FROM user WHERE user_id = ?",
        (int(query.invoice_payload.removeprefix("KD_RESET_")),),
    )
    if cur.fetchone() is None:
        await query.answer(False)

    await query.answer(True)


@dp.message(
    F.content_type == ContentType.SUCCESSFUL_PAYMENT,
    F.successful_payment.invoice_payload.startswith("KD_RESET_"),
)
async def on_success(message: types.Message):
    cur.execute(
        "UPDATE user SET next_dick = 0 WHERE user_id = ?",
        (int(message.successful_payment.invoice_payload.removeprefix("KD_RESET_")),),
    )

    await message.reply("Оплата получена! КД снято.")
    await bot.send_message(
        owners_id[0],
        f"Пользователь с ID {message.from_user.id} ({message.from_user.full_name}) "
        f"оплатил снятие КД на /dick для пользователя/канала с ID {message.successful_payment.invoice_payload.removeprefix("KD_RESET_")}",
    )


@dp.message(Command("refund"), F.from_user.id.in_(owners_id))
async def refund_stars(message: types.Message):
    user_id = int(message.text.split()[1])
    tr_id = message.text.split()[2]

    try:
        await message.bot.refund_star_payment(
            user_id=user_id, telegram_payment_charge_id=tr_id
        )
    except exceptions.TelegramBadRequest:
        return await message.reply(
            "Не найдено невозвращённой транзакции у данного пользователя с данным ID."
        )

    await message.reply("Деньги вернул.")


@dp.message(Command("sendalert"), F.from_user.id.in_(owners_id))
async def send_alert(message: types.Message):
    alert = message.md_text.removeprefix("/sendalert ")
    if alert == "":
        return await message.reply("А чё рассылать-то?")

    cur.execute("""SELECT DISTINCT chat_id FROM user""")
    chats_id = cur.fetchall()

    msg = await message.reply("Начинаю рассылку...")
    for c_id in chats_id:
        try:
            await message.bot.send_message(
                c_id["chat_id"], "*Объявление:*\n\n" + alert, parse_mode="MarkdownV2"
            )
        except Exception:
            traceback.print_exc()
            print(c_id)
        await asyncio.sleep(2)

    await msg.edit_text("Рассылка завершена!")


@dp.message(Command("feedback"), F.from_user.id == F.chat.id, ~F.from_user.id.func(is_banned_user))
async def feedback_cmd(message: types.Message):
    report_msg = message.md_text.removeprefix("/feedback")
    if report_msg == "":
        return await message.reply(
            "Напишите внутри команды сообщение, которое хотите отправить владельцу бота.\n"
            "Пример: /feedback Хочу, чтобы бот умел женить людей.\n"
            "ВНИМАНИЕ: Бот может переслать только один файл. Если Вам нужно отправить несколько файлов, отправляйте их по одному!"
        )

    msg = await message.forward(owners_id[0])
    await msg.reply(f"ID отправителя: {message.from_user.id}")
    await message.reply("Передал сообщение владельцу!")


@dp.message(Command("banfeedback"), F.from_user.id.in_(owners_id))
async def banfeedbackcmd(message: types.Message):
    args = message.text.split()[1:]
    if len(args) == 0:
        return await message.reply("Некого банить")
    
    user_id = args[0]
    cur.execute("INSERT INTO banned_user (user_id) VALUES (?)", (user_id,))
    await message.reply("Уничтожено!")


@dp.message(Command("unbanfeedback"), F.from_user.id.in_(owners_id))
async def unbanfeedbackcmd(message: types.Message):
    args = message.text.split()[1:]
    if len(args) == 0:
        return await message.reply("Некого разбанить")
    
    user_id = args[0]
    cur.execute("DELETE FROM banned_user WHERE user_id = ?", (user_id,))
    await message.reply("Реабилитирован!")


@dp.message(Command("sendto"), F.from_user.id.in_(owners_id))
async def sendtocmd(message: types.Message):
    args = message.md_text.split()[1:]
    if len(args) <= 1:
        return await message.reply("А чё отправлять-то и кому?")
    
    msg_text = message.md_text.removeprefix(f"/sendto {args[0]} ")
    sender_id = args[0].replace("\\", "")
    with suppress(ValueError):
        sender_id = int(sender_id)
    
    print(sender_id)

    await message.bot.send_message(
        sender_id, "*Сообщение от владельца бота:*\n\n" + msg_text, parse_mode="MarkdownV2"
    )
    await message.reply("Ответил")


if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
