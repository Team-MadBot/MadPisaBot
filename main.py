import asyncio
import contextlib
import datetime
import logging
import random
import traceback

from aiogram import Bot, Dispatcher, F, exceptions, types
from aiogram.filters import Command
from aiogram.types import ContentType, LabeledPrice, PreCheckoutQuery
from aiogram.filters import IS_MEMBER, IS_NOT_MEMBER, ChatMemberUpdatedFilter

from db import ChatRepository, UserCacheRepository, ChatUserRepository, ThingForm
from config import bot_token, owners_id

logging.basicConfig(level=logging.INFO)

bot = Bot(token=bot_token)
dp = Dispatcher()


@dp.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def handle_group_join(event: types.ChatMemberUpdated):
    with contextlib.suppress(Exception):  # FIXME
        await ChatRepository.create_chat(event.chat.id)


@dp.message(F.migrate_to_chat_id)
@dp.message(F.migrate_from_chat_id)
async def migrate_to_chat_id_handler(message: types.Message):
    old_id, new_id = message.chat.id, message.migrate_to_chat_id
    assert new_id is not None

    await ChatRepository.update_chat_settings(current_chat_id=old_id, chat_id=new_id)
    await ChatUserRepository.migrate_user_id(old_user_id=old_id, new_user_id=new_id)
    await UserCacheRepository.migrate_user_id(old_user_id=old_id, new_user_id=new_id)


@dp.message(Command("luck"))
async def try_luck(message: types.Message):
    assert message.from_user is not None

    if message.chat.id == message.from_user.id:
        return await message.reply("Данная команда доступна только в группах с ботом.")

    tg_user = message.sender_chat or message.from_user

    user = await ChatUserRepository.get_or_create_user(
        chat_id=message.chat.id,
        user_id=tg_user.id
    )
    chat_info = await ChatRepository.get_or_create_chat(
        chat_id=message.chat.id,
        thing_name="писюн",
        thing_metric="см"
    )
    await UserCacheRepository.get_and_update_user_cache(
        user_id=tg_user.id,
        user_name=tg_user.full_name
    )
    if user.cooldown_timestamp > datetime.datetime.now():
        remaining = user.cooldown_timestamp - datetime.datetime.now()
        return await message.reply(
            "Ты уже играл!\n"
            f"Ожидай ещё {round(remaining.total_seconds() // 3600)} часов, {round(remaining.total_seconds() % 3600 // 60)} минут и "
            f"{round(remaining.seconds)} секунд."
        )
    
    amount = int(random.randint(chat_info.random_min_value, chat_info.random_max_value))

    positive_change_text_forms = {
        ThingForm.MASCULINE: f"{tg_user.full_name}, твой {chat_info.thing_name} увеличился на {amount} {chat_info.thing_metric}.",
        ThingForm.FEMININE: f"{tg_user.full_name}, твоя {chat_info.thing_name} увеличилась на {amount} {chat_info.thing_metric}.",
        ThingForm.MIDDLE: f"{tg_user.full_name}, твоё {chat_info.thing_name} увеличилось на {amount} {chat_info.thing_metric}."
    }
    neutral_change_text_forms = {
        ThingForm.MASCULINE: f"{tg_user.full_name}, твой {chat_info.thing_name} не изменился.",
        ThingForm.FEMININE: f"{tg_user.full_name}, твоя {chat_info.thing_name} не изменилась.",
        ThingForm.MIDDLE: f"{tg_user.full_name}, твоё {chat_info.thing_name} не изменилось."
    }
    negative_change_text_forms = {
        ThingForm.MASCULINE: f"{tg_user.full_name}, твой {chat_info.thing_name} сократился на {amount * -1} {chat_info.thing_metric}.",
        ThingForm.FEMININE: f"{tg_user.full_name}, твоя {chat_info.thing_name} сократилась на {amount * -1} {chat_info.thing_metric}.",
        ThingForm.MIDDLE: f"{tg_user.full_name}, твоё {chat_info.thing_name} сократилось на {amount * -1} {chat_info.thing_metric}."
    }

    current_text_forms = {
        ThingForm.MASCULINE: f"Теперь {chat_info.thing_name} равен {(user.thing_value + amount):,} {chat_info.thing_metric}.",
        ThingForm.FEMININE: f"Теперь {chat_info.thing_name} равна {(user.thing_value + amount):,} {chat_info.thing_metric}.",
        ThingForm.MIDDLE: f"Теперь {chat_info.thing_name} равно {(user.thing_value + amount):,} {chat_info.thing_metric}."
    }

    change_text = positive_change_text_forms[chat_info.thing_form]
    if amount == 0:
        change_text = neutral_change_text_forms[chat_info.thing_form]
    if amount < 0:
        change_text = negative_change_text_forms[chat_info.thing_form]

    await ChatUserRepository.set_new_cooldown(chat_id=message.chat.id, user_id=tg_user.id)
    await ChatUserRepository.increment_user_value(chat_id=message.chat.id, user_id=tg_user.id, increment=amount)

    await message.reply(
        f"{change_text}\n{current_text_forms[chat_info.thing_form]}\n"
        f"Следующая попытка через 12 часов."
    )


@dp.message(Command("info"))
async def info(message: types.Message):
    assert message.from_user is not None

    if message.chat.id == message.from_user.id:
        return await message.reply("Данная команда доступна только в группах с ботом.")

    tg_user = (
        (message.sender_chat or message.from_user)
        if message.reply_to_message is None
        else (
            message.reply_to_message.sender_chat or message.reply_to_message.from_user
        )
    )
    assert tg_user is not None

    db_user = await ChatUserRepository.get_user(chat_id=message.chat.id, user_id=tg_user.id)
    chat_info = await ChatRepository.get_or_create_chat(
        chat_id=message.chat.id,
        thing_name="писюн",
        thing_metric="см"
    )
    if db_user is None:
        your_thing_forms = {
            ThingForm.MASCULINE: "твой",
            ThingForm.FEMININE: "твоя",
            ThingForm.MIDDLE: "твоё",
        }
        is_equal_forms = {
            ThingForm.MASCULINE: "равен",
            ThingForm.FEMININE: "равна",
            ThingForm.MIDDLE: "равно",
        }
        text = (
            (
                f"Этот игрок ещё ни разу не играл, поэтому его {chat_info.thing_form} {is_equal_forms[chat_info.thing_form]} 0 {chat_info.thing_metric}.\n"
                "Скажи ему использовать /luck для игры."
            ) if message.reply_to_message else (
                f"Ты ещё ни разу не играл, поэтому {your_thing_forms[chat_info.thing_form]} {chat_info.thing_name} {is_equal_forms[chat_info.thing_form]} "
                "0 {chat_info['thing_metric']}.\nИспользуй /luck для игры."
            )
        )
        return await message.reply(text)

    remaining = db_user.cooldown_timestamp - datetime.datetime.now()
    remaining_text = f"через {round(remaining.total_seconds() // 3600)} часов, {round(remaining.total_seconds() % 3600 // 60)} минут и {round(remaining.seconds)} секунд."
    if remaining.total_seconds() <= 0:
        remaining_text = "сейчас!"

    current_text_forms = {
        ThingForm.MASCULINE: f"твой {chat_info.thing_name} равен {(db_user.thing_value):,} {chat_info.thing_metric}.",
        ThingForm.FEMININE: f"твоя {chat_info.thing_name} равна {(db_user.thing_value):,} {chat_info.thing_metric}.",
        ThingForm.MIDDLE: f"твоё {chat_info.thing_name} равно {(db_user.thing_value):,} {chat_info.thing_metric}."
    }
    text = (
        f"{tg_user.full_name}, {current_text_forms[chat_info.thing_form]}\n"
        f"Следующий /luck: {remaining_text}"
    )

    await message.reply(text)
    await UserCacheRepository.get_and_update_user_cache(user_id=tg_user.id, user_name=tg_user.full_name)


@dp.message(Command("top"))
async def top(message: types.Message):
    assert message.from_user is not None

    if message.chat.id == message.from_user.id:
        return await message.reply("Данная команда доступна только в группах с ботом.")

    users = await ChatUserRepository.get_top_users(chat_id=message.chat.id)
    chat_info = await ChatRepository.get_or_create_chat(
        chat_id=message.chat.id,
        thing_name="писюн",
        thing_metric="см"
    )

    text = "Топ этого чата:\n\n"
    for count, user in enumerate(users, start=1):
        user_name = None
        user_cache = await UserCacheRepository.get_user_cache_by_id(user_id=user.user_id)
        if user_cache is not None:
            user_name = user_cache.user_name
        else:
            try:
                user_name = (await bot.get_chat(user.user_id)).full_name
            except exceptions.TelegramBadRequest:
                traceback.print_exc()
        text += f"{count}. {user_name or 'Неизвестный'}: {user.thing_value:,} {chat_info.thing_metric}.\n"
        if user_cache is None and user_name is not None:
            await UserCacheRepository.create_user_cache(user_id=user.user_id, user_name=user_name)

    await message.reply(text)


@dp.message(Command("giveuserlink"))
async def giveuserlink(message: types.Message):
    assert message.text is not None
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
    assert message.text is not None
    args = message.text.split(" ")
    if len(args) < 2:
        return await message.reply("Введите, на сколько нужно изменить значение")

    if len(args) < 3:
        args.append('0')
    try:
        int(args[1])
        int(args[2])
    except ValueError:
        return await message.reply("Невозможно перевести один из аргументов в число!")

    user = int(args[2])

    if not user and message.reply_to_message is not None:
        assert message.reply_to_message.from_user is not None
        user = (message.reply_to_message.sender_chat or message.reply_to_message.from_user).id
    else:
        return await message.reply(
            "Ответьте на сообщение человека, кому надо изменить значение, либо укажите ID следующим аргументом!"
        )
    
    await ChatUserRepository.get_or_create_user(chat_id=message.chat.id, user_id=user)
    await ChatUserRepository.increment_user_value(chat_id=message.chat.id, user_id=user, increment=int(args[1]))

    await message.reply(
        f"Значение изменено у {'пользователя с ID ' + str(user) if message.reply_to_message is None else (
            message.reply_to_message.sender_chat or message.reply_to_message.from_user
        ).full_name}"
    )


@dp.message(Command("buy"))
async def buy_kd_reset(message: types.Message):
    assert message.from_user is not None
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
    if (await ChatUserRepository.get_any_user(int(query.invoice_payload.removeprefix("KD_RESET_")))) is None:
        await query.answer(False)

    await query.answer(True)


@dp.message(
    F.content_type == ContentType.SUCCESSFUL_PAYMENT,
    F.successful_payment.invoice_payload.startswith("KD_RESET_"),
)
async def on_success(message: types.Message):
    assert message.successful_payment is not None
    assert message.from_user is not None

    await ChatUserRepository.reset_cooldown(int(message.successful_payment.invoice_payload.removeprefix("KD_RESET_")))
    await message.reply("Оплата получена! КД снято.")
    await bot.send_message(
        owners_id[0],
        f"Пользователь с ID {message.from_user.id} ({message.from_user.full_name}) "
        f"оплатил снятие КД на /luck для пользователя/канала с ID {message.successful_payment.invoice_payload.removeprefix("KD_RESET_")}",
    )


@dp.message(Command("refund"), F.from_user.id.in_(owners_id))
async def refund_stars(message: types.Message):
    assert message.text is not None
    assert message.bot is not None
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
    assert message.bot is not None
    alert = message.md_text.removeprefix("/sendalert").removeprefix(" ")
    if alert == "":
        return await message.reply("А чё рассылать-то?")

    chats_id = await ChatRepository.get_all_chats()

    msg = await message.reply("Начинаю рассылку...")
    for c_id in chats_id:
        try:
            await message.bot.send_message(
                c_id.chat_id, "*Объявление:*\n\n" + alert, parse_mode="MarkdownV2"
            )
        except Exception:
            traceback.print_exc()
            print(c_id)
        await asyncio.sleep(0.034)

    await msg.edit_text("Рассылка завершена!")


if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
