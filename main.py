import asyncio
import datetime
import logging
import random
import sqlite3
import time
import traceback

from aiogram import Bot, Dispatcher, F, exceptions, types
from aiogram.filters import Command
from aiogram.types import ContentType, LabeledPrice, PreCheckoutQuery
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER, ChatMemberUpdatedFilter

from config import bot_token, owners_id, get_fake_chat_info

logging.basicConfig(level=logging.INFO)

bot = Bot(token=bot_token)
dp = Dispatcher()
db = sqlite3.connect("database.db", autocommit=True)
db.row_factory = sqlite3.Row
cur = db.cursor()

cur.execute(
    """CREATE TABLE IF NOT EXISTS user (
        chat_id INTEGER,
        user_id INTEGER,
        value INTEGER,
        cooldown_until INTEGER
    );"""
)
cur.execute(
    """CREATE TABLE IF NOT EXISTS chat (
        chat_id INTEGER UNIQUE NOT NULL,
        thing_name TEXT NOT NULL DEFAULT("ум"),
        thing_metric TEXT NOT NULL DEFAULT("IQ"),
        min_value INTEGER NOT NULL DEFAULT(-5),
        max_value INTEGER NOT NULL DEFAULT(10) 
    );"""
)
cur.execute(
    """CREATE TABLE IF NOT EXISTS user_cache (
        user_id INTEGER UNIQUE NOT NULL,
        user_name TEXT
    );"""
)


def get_top_users(chat_id: int):
    cur.execute(f"""SELECT * FROM user WHERE chat_id = {chat_id}""")
    return sorted(
        [dict(row) for row in cur.fetchall()], key=lambda u: u["value"], reverse=True
    )


@dp.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def handle_group_join(event: types.ChatMemberUpdated):
    if cur.execute("SELECT * FROM chat WHERE chat_id = ?", (event.chat.id,)).fetchone() is not None:
        return
    
    cur.execute("INSERT INTO chat (chat_id) VALUES (?)", (event.chat.id, ))


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


@dp.message(Command("luck"))
async def try_luck(message: types.Message):
    if message.chat.id == message.from_user.id:
        return await message.reply("Данная команда доступна только в группах с ботом.")

    tg_user = message.sender_chat or message.from_user
    cur.execute(
        f"""SELECT * FROM user WHERE user_id = {tg_user.id} AND chat_id = {message.chat.id}"""
    )

    user = dict(
        cur.fetchone()
        or {
            "chat_id": message.chat.id,
            "user_id": tg_user.id,
            "value": 0,
            "cooldown_until": 0,
            "fake": True,
        }
    )
    chat_info = dict(
        cur.execute("SELECT * FROM chat WHERE chat_id = ?", (message.chat.id,)).fetchone()
        or get_fake_chat_info(message.chat.id, thing_name="писюн", thing_metric="см")
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
    if user["cooldown_until"] > time.time():
        remaining = user["cooldown_until"] - time.time()
        return await message.reply(
            f"Ты уже играл!\nОжидай ещё {round(remaining // 3600)} часов, {round(remaining % 3600 // 60)} минут и {round(remaining % 3600 % 60)} секунд."
        )
    
    amount = int(random.randint(chat_info["min_value"], chat_info["max_value"]))

    text = f"{tg_user.full_name}, твой {chat_info['thing_name']} увеличился на {amount} {chat_info['thing_value']}."
    if amount == 0:
        text = f"{tg_user.full_name}, твой {chat_info['thing_name']} не изменился."
    if amount < 0:
        text = f"{tg_user.full_name}, твой {chat_info['thing_name']} сократился на {amount * -1} {chat_info['thing_metric']}."

    if user.get("fake", False):
        cur.execute(
            f"""INSERT INTO user (chat_id, user_id, value, cooldown_until) VALUES
            ({message.chat.id}, {tg_user.id}, {amount}, {int(datetime.datetime.now().timestamp() + 3600 * 12)})"""
        )
    else:
        cur.execute(
            f"""UPDATE user SET value = {user['value'] + amount}, cooldown_until = {int(datetime.datetime.now().timestamp() + 3600 * 12)} 
            WHERE user_id = {tg_user.id} AND chat_id = {message.chat.id}"""
        )

    chat_users = get_top_users(chat_id=message.chat.id)
    for count, u in enumerate(chat_users, start=1):
        if u["user_id"] == tg_user.id:
            break

    await message.reply(
        f"{text}\nТеперь размер составляет {(user['value'] + amount):,} {chat_info['thing_value']}.\n"
        f"Теперь ты занимаешь {count} место в топе.\nСледующая попытка через 12 часов."
    )
    if chat_info.get("fake", False):
        cur.execute(
            """INSERT INTO chat (chat_id, thing_name, thing_metric, min_value, max_value)
            VALUES (?, ?, ?, ?, ?)""",
            (chat_info["chat_id"], chat_info["thing_name"], chat_info["thing_metric"], chat_info["min_value"], chat_info["max_value"])
        )


@dp.message(Command("info"))
async def info(message: types.Message):
    if message.chat.id == message.from_user.id:
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
    chat_info = dict(
        cur.execute("SELECT * FROM chat WHERE chat_id = ?", (message.chat.id,)) or 
        get_fake_chat_info(message.chat.id, "писюн", "см")
    )
    if db_user is None:
        text = (
            f"Этот игрок ещё ни разу не играл, поэтому его {chat_info['thing_name']} равна 0 {chat_info['thing_metric']}. Скажи ему использовать /luck для игры."
            if message.reply_to_message
            else f"Ты ещё ни разу не играл, поэтому твой {chat_info['thing_name']} равна 0 {chat_info['thing_metric']}. Используй /luck для игры."
        )
        return await message.reply(text)

    remaining = (db_user["cooldown_until"] or 0) - round(time.time())
    remaining_text = f"через {round(remaining // 3600)} часов, {round(remaining % 3600 // 60)} минут и {round(remaining % 3600 % 60)} секунд."
    if remaining <= 0:
        remaining_text = "сейчас!"

    chat_users = get_top_users(message.chat.id)
    for count, u in enumerate(chat_users, start=1):
        if u["user_id"] == user.id:
            break

    thing_name = (
        "в твою пизду поместится"
        if db_user["value"] <= 0 and chat_info["thing_name"] == "писюн" 
        else f"твой {chat_info['thing_name']} эквивалентен"
    )
    text = (
        f"{user.full_name}, {thing_name} {(abs(db_user['value']) if chat_info['thing_name'] == 'писюн' else db_user['value']):,} {chat_info['thing_metric']}.\n"
        f"Ты занимаешь {count} место в топе.\n"
        f"Следующий /luck: {remaining_text}"
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
    if chat_info.get("fake", False):
        cur.execute(
            """INSERT INTO chat (chat_id, thing_name, thing_metric, min_value, max_value)
            VALUES (?, ?, ?, ?, ?)""",
            (chat_info["chat_id"], chat_info["thing_name"], chat_info["thing_metric"], chat_info["min_value"], chat_info["max_value"])
        )


@dp.message(Command("top"))
async def top(message: types.Message):
    if message.chat.id == message.from_user.id:
        return await message.reply("Данная команда доступна только в группах с ботом.")

    users = get_top_users(message.chat.id)
    chat_info = dict(
        cur.execute("SELECT * FROM chat WHERE chat_id = ?", (message.chat.id,)) or 
        get_fake_chat_info(message.chat.id, "писюн", "см")
    )

    text = "Топ этого чата:\n\n"
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
        text += f"{count}. {user_name or 'Неизвестный'}: {user['value']:,} {chat_info["thing_metric"]}.\n"
        if user_cache is None and user_name is not None:
            cur.execute(
                "INSERT INTO user_cache (user_id, user_name) VALUES (?, ?)", 
                (user["user_id"], user_name)
            )

    await message.reply(text)

    if chat_info.get("fake", False):
        cur.execute(
            """INSERT INTO chat (chat_id, thing_name, thing_metric, min_value, max_value)
            VALUES (?, ?, ?, ?, ?)""",
            (chat_info["chat_id"], chat_info["thing_name"], chat_info["thing_metric"], chat_info["min_value"], chat_info["max_value"])
        )


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
async def editsize(message: types.Message):
    args = message.text.split(" ")
    if len(args) < 2:
        return await message.reply("Введи, на сколько изменить")

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
            "INSERT INTO user (chat_id, user_id, value) VALUES (?, ?, ?)",
            (message.chat.id, user, int(args[1])),
        )
    else:
        cur.execute(
            "UPDATE user SET value = value + ? WHERE chat_id = ? AND user_id = ?",
            (args[1], message.chat.id, user),
        )

    await message.reply(
        f"Размер изменён у {'пользователя с ID ' + str(user) if message.reply_to_message is None else (
            message.reply_to_message.sender_chat or message.reply_to_message.from_user
        ).full_name}"
    )


@dp.message(Command("buy"))
async def buy_kd_reset(message: types.Message):
    if message.chat.id != message.from_user.id:
        return await message.reply("Покупка возможна только в личных сообщениях бота.")

    await message.reply_invoice(
        title="Сброс кд",
        description="Сброс срока /luck. Если КД прошло - звёзды улетят впустую!!!!",
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
        "UPDATE user SET cooldown_until = 0 WHERE user_id = ?",
        (int(message.successful_payment.invoice_payload.removeprefix("KD_RESET_")),),
    )

    await message.reply("Оплата получена! КД снято.")
    await bot.send_message(
        owners_id[0],
        f"Пользователь с ID {message.from_user.id} ({message.from_user.full_name}) "
        f"оплатил снятие КД на /luck для пользователя/канала с ID {message.successful_payment.invoice_payload.removeprefix("KD_RESET_")}",
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


if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
