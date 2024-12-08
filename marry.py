import random

from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

from main import dp, cur
from config import get_fake_base, escape_markdown


@dp.message(Command("marry"))
async def marry_handler(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return await message.reply("Данная команда доступна тольк в группах с ботом!")
    if message.reply_to_message is None:
        return await message.reply("Ответьте на сообщение пользователя, с которым хотите пожениться.")
    if message.sender_chat is not None or message.reply_to_message.sender_chat is not None:
        return await message.reply("Свадьба возможно только между людьми!")
    if message.from_user.id == message.reply_to_message.from_user.id:
        return await message.reply(
            "Сва́дьба, сва́дебный обря́д, свадебный ритуал — один из семейных обрядов (ритуалов),"
            " оформляющий вступление в брак двух различных людей."
        )
    if message.reply_to_message.from_user.is_bot:
        return await message.reply(
            "Боты бесчувственны: даже не пытайся."
        )
    
    master_user = message.from_user
    slave_user = message.reply_to_message.from_user

    cur.execute(
        "SELECT * FROM user WHERE chat_id = ? AND (user_id = ? OR user_id = ?)",
        (message.chat.id, master_user.id, slave_user.id)
    )
    newlyweds = list(map(dict, cur.fetchall()))
    for usr in newlyweds:
        if usr["married_with"] is not None:
            return await message.reply(
                "Вы или упомянутый Вами пользователь уже имеет партнёра."
            )
    
    return await message.reply(
        f"{slave_user.mention_markdown()}, {master_user.mention_markdown()} хочет пожениться на Вас\\!\n"
        "Пожалуйста, ответьте на это предложение, нажав соответствующую кнопку\\.",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Согласиться", 
                        callback_data=f"marry_accept_{master_user.id}_{slave_user.id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отказаться",
                        callback_data=f"marry_deny_{master_user.id}_{slave_user.id}"
                    )
                ]
            ]
        )
    )


@dp.callback_query(F.data.startswith("marry_accept"))
async def accept_marriage_handler(query: types.CallbackQuery):
    args = query.data.split("_")
    master_user_id = int(args[2])
    slave_user_id = int(args[3])
    await query.answer()
    if query.from_user.id != slave_user_id:
        return

    cur.execute(
        "SELECT * FROM user WHERE chat_id = ? AND (user_id = ? OR user_id = ?)", 
        (query.message.chat.id, master_user_id, slave_user_id)
    )
    newlyweds = list(map(dict, cur.fetchall()))
    for usr in newlyweds:
        if usr["married_with"] is not None:
            return await query.message.reply(
                "К сожалению, Вы опоздали: Вы либо Ваш любимчик уже нашёл себе пару."
            )
    
    if len(newlyweds) == 0:
        newlyweds = [
            get_fake_base(
                chat_id=query.message.chat.id,
                user_id=master_user_id
            ),
            get_fake_base(
                chat_id=query.message.chat.id,
                user_id=slave_user_id
            )
        ]
    if len(newlyweds) == 1:
        newlyweds.append(
            get_fake_base(
                chat_id=query.message.chat.id,
                user_id=master_user_id if newlyweds[0]["user_id"] == slave_user_id else slave_user_id
            )
        )
    
    for usr in newlyweds:
        if usr.get("fake", False):
            cur.execute(
                "INSERT INTO user (chat_id, user_id, married_with) VALUES (?, ?, ?)",
                (query.message.chat.id, usr["user_id"], master_user_id if usr["user_id"] == slave_user_id else slave_user_id)
            )
        else:
            cur.execute(
                "UPDATE user SET married_with = ? WHERE chat_id = ? AND user_id = ?",
                (master_user_id if usr["user_id"] == slave_user_id else slave_user_id, query.message.chat.id, usr["user_id"])
            )
    
    await query.message.edit_text(
        "Свадьба успешно состоялась. Горько!"
    )


@dp.callback_query(F.data.startswith("marry_deny"))
async def deny_marriage_handler(query: types.CallbackQuery):
    await query.answer()
    if str(query.from_user.id) not in query.data:
        return
    
    args = query.data.split("_")
    slave_user_id = int(args[3])
    text = "отказался(-ась) от предложения" if query.from_user.id == slave_user_id else "отменил(-а) предложение"
    
    await query.message.edit_text(
        f"Пользователь {query.from_user.mention_markdown()} {text} свадьбы\\.",
        parse_mode="MarkdownV2",
        reply_markup=None
    )


@dp.message(Command("divorce"))
async def divorce_handler(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return await message.reply("Данная команда доступна тольк в группах с ботом!")
    if message.sender_chat is not None:
        return await message.reply("Каналы и группы лишены права на секс.")

    cur.execute("SELECT * FROM user WHERE chat_id = ? AND user_id = ?", (message.chat.id, message.from_user.id))
    usr = cur.fetchone()
    if usr is None or usr["married_with"] is None:
        return await message.reply("Да ты холостяк! С кем ты собрался разводиться?")

    cur.execute(
        "UPDATE user SET married_with = ? WHERE chat_id = ? AND (user_id = ? or user_id = ?)", 
        (None, message.chat.id, message.from_user.id, usr["married_with"])
    )
    cur.execute(
        "SELECT user_name FROM user_cache WHERE user_id = ?",
        (usr["married_with"], )
    )
    married_with_name = cur.fetchone()["user_name"]
    await message.reply(
        f"[{escape_markdown(married_with_name)}](tg://user?id={usr['married_with']}), Ваш\\(\\-а\\) супруг\\(\\-а\\) бросил\\(\\-а\\) Вас||\\(\\-а\\)||\\. Поплачь\\.",
        parse_mode="MarkdownV2"
    )


@dp.message(Command("sex"))
async def sex_handler(message: types.Message):
    cur.execute(
        "SELECT * FROM user WHERE chat_id = ? AND user_id = ?",
        (message.chat.id, message.from_user.id)
    )
    usr = cur.fetchone() or get_fake_base(
        chat_id=message.chat,
        user_id=message.from_user.id
    )
    if usr["married_with"] is None:
        return await message.reply("Поздравляю! Вы успешно заработали мазоли на руке!")
    
    if random.randint(0, 1):
        return await message.reply_photo(
            "AgACAgIAAyEFAASK87KeAAIC-Gc-JjHbvM8o5BYoaXHjpk7EIIOLAAL_6jEb-FnxSasr9gZS_JDIAQADAgADcwADNgQ"
        )
    
    cur.execute("SELECT user_name FROM user_cache WHERE user_id = ?", (usr["married_with"], ))
    married_with_name = cur.fetchone()["user_name"]
    await message.reply(
        f"[{escape_markdown(married_with_name)}](tg://user?id={usr["married_with"]}), Ваш партнёр выполнил Вам пробитие\\! Наслаждайтесь\\!",
        parse_mode="MarkdownV2"
    )
