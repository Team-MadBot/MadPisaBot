import random

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Child, FamilyRequest, Marriage, MarriageMember, Player, Pregnancy
from bot.services.common import GameError, get_player, player_name
from bot.time import (
    HOUR, POSTPARTUM_COOLDOWN, PREGNANCY_DURATION, REQUEST_DURATION,
    availability, duration, moscow_time,
)


async def current_marriage(session: AsyncSession, chat_id: int, user_id: int) -> Marriage | None:
    member = await session.get(MarriageMember, (chat_id, user_id))
    return await session.get(Marriage, member.marriage_id) if member else None


async def require_marriage(session: AsyncSession, chat_id: int, user_id: int) -> Marriage:
    marriage = await current_marriage(session, chat_id, user_id)
    if marriage is None or marriage.ended_at is not None:
        raise GameError("У тебя нет действующего брака в этом чате.")
    return marriage


async def family_children(session: AsyncSession, chat_id: int, marriage_id: int) -> list[Child]:
    return list(await session.scalars(
        select(Child).where(Child.chat_id == chat_id, Child.marriage_id == marriage_id)
        .order_by(Child.id)
    ))


async def process_births(session: AsyncSession, now: float, chat_id: int | None = None):
    query = select(Pregnancy).where(Pregnancy.status == "active", Pregnancy.due_at <= now)
    if chat_id is not None:
        query = query.where(Pregnancy.chat_id == chat_id)
    pregnancies = list(await session.scalars(query.order_by(Pregnancy.due_at, Pregnancy.id)))
    for pregnancy in pregnancies:
        marriage = await session.get(Marriage, pregnancy.marriage_id)
        if marriage is None or marriage.ended_at is not None:
            pregnancy.status = "cancelled"
            continue
        carrier = await session.get(Player, (pregnancy.chat_id, pregnancy.carrier_id))
        carrier.pregnancy_available_at = pregnancy.due_at + POSTPARTUM_COOLDOWN
        session.add(Child(
            chat_id=pregnancy.chat_id, pregnancy_id=pregnancy.id, marriage_id=marriage.id,
            first_parent_id=marriage.first_id, second_parent_id=marriage.second_id,
            born_at=pregnancy.due_at, length=0, next_dick=0, notify_after=0,
        ))
        pregnancy.status = "born"
    await session.flush()


async def create_request(
    session: AsyncSession, chat_id: int, initiator_id: int, kind: str, now: float,
    target_id: int | None = None, child_id: int | None = None,
) -> FamilyRequest:
    marriage = None
    if kind == "marry":
        if target_id is None or target_id == 0:
            raise GameError("Ответь на сообщение игрока или укажи его ID: /marry <id>.")
        if target_id == initiator_id:
            raise GameError("Нельзя пожениться с самим собой.")
        for user_id in (initiator_id, target_id):
            if await current_marriage(session, chat_id, user_id):
                raise GameError("Один из игроков уже состоит в браке в этом чате.")
        recipient_id = target_id
    else:
        marriage = await require_marriage(session, chat_id, initiator_id)
        recipient_id = initiator_id if kind == "divorce" else marriage.partner(initiator_id)
        if kind == "sex" and marriage.next_sex > now:
            raise GameError(f"Следующий /sex: {availability(marriage.next_sex, now)}")
        if kind == "orphanage":
            child = await session.get(Child, child_id) if child_id is not None else None
            if child is None or child.chat_id != chat_id or child.marriage_id != marriage.id:
                raise GameError("Этот ребёнок не принадлежит вашей семье.")
        if kind not in {"sex", "divorce", "orphanage"}:
            raise GameError("Неизвестное семейное действие.")

    existing = await session.scalar(select(FamilyRequest).where(
        FamilyRequest.chat_id == chat_id, FamilyRequest.kind == kind,
        FamilyRequest.initiator_id == initiator_id, FamilyRequest.recipient_id == recipient_id,
        FamilyRequest.child_id == child_id, FamilyRequest.status == "pending",
        FamilyRequest.expires_at > now,
    ).order_by(FamilyRequest.id))
    if existing:
        raise GameError(f"Такое предложение уже ожидает ответа: №{existing.id}.")
    request = FamilyRequest(
        chat_id=chat_id, kind=kind, initiator_id=initiator_id, recipient_id=recipient_id,
        marriage_id=marriage.id if marriage else None, child_id=child_id,
        created_at=now, expires_at=now + REQUEST_DURATION, status="pending",
    )
    session.add(request)
    await session.flush()
    return request


async def request_text(session: AsyncSession, request: FamilyRequest) -> str:
    initiator = await player_name(session, request.initiator_id)
    recipient = await player_name(session, request.recipient_id)
    descriptions = {
        "marry": f"👨‍❤️‍👨 {initiator} предлагает {recipient} пожениться!",
        "sex": f"👬 {initiator} предлагает супругу {recipient} заняться сексом.",
        "divorce": (
            f"{initiator}, подтвердить развод? Дети останутся в детдоме до нового брака "
            "между вами в этом чате. Текущие беременности будут отменены."
        ),
        "orphanage": (
            f"{initiator} предлагает {recipient} сдать ребёнка №{request.child_id} в детдом. "
            "Ребёнок будет удалён навсегда, вместе с именем и статистикой."
        ),
    }
    return (
        f"{descriptions[request.kind]}\n\nПредложение №{request.id}.\n"
        f"Подтверждает: {recipient} (ID {request.recipient_id}).\n"
        f"/accept {request.id} — согласиться; /decline {request.id} — отказаться.\n"
        "Можно отправить /accept или /decline ответом на это сообщение.\n"
        f"Срок ответа: {moscow_time(request.expires_at)}."
    )


async def marry(session: AsyncSession, request: FamilyRequest, now: float) -> str:
    chat_id = request.chat_id
    first_id, second_id = sorted((request.initiator_id, request.recipient_id))
    for user_id in (first_id, second_id):
        if await current_marriage(session, chat_id, user_id):
            raise GameError("Один из игроков уже вступил в другой брак.")
        await get_player(session, chat_id, user_id)
    # Remarrying the same spouse does not bypass the pair's hourly cooldown.
    next_sex = await session.scalar(select(func.max(Marriage.next_sex)).where(
        Marriage.chat_id == chat_id, Marriage.first_id == first_id, Marriage.second_id == second_id,
    )) or 0
    marriage = Marriage(
        chat_id=chat_id, first_id=first_id, second_id=second_id,
        started_at=now, next_sex=next_sex,
    )
    session.add(marriage)
    await session.flush()
    session.add_all([
        MarriageMember(chat_id=chat_id, user_id=user_id, marriage_id=marriage.id)
        for user_id in (first_id, second_id)
    ])
    restored = await session.execute(update(Child).where(
        Child.chat_id == chat_id, Child.marriage_id.is_(None),
        Child.first_parent_id == first_id, Child.second_parent_id == second_id,
    ).values(marriage_id=marriage.id))
    await session.execute(update(FamilyRequest).where(
        FamilyRequest.chat_id == chat_id, FamilyRequest.status == "pending",
        FamilyRequest.kind == "marry",
        or_(FamilyRequest.initiator_id.in_((first_id, second_id)),
            FamilyRequest.recipient_id.in_((first_id, second_id))),
    ).values(status="cancelled"))
    first = await player_name(session, first_id)
    second = await player_name(session, second_id)
    text = f"👨‍❤️‍👨 {first} и {second} теперь мужья!"
    if restored.rowcount:
        text += f"\nИз детдома вернулись ваши дети: {restored.rowcount}. Имена и статистика сохранены."
    return text


async def divorce(session: AsyncSession, marriage: Marriage, now: float) -> str:
    marriage.ended_at = now
    await session.execute(update(Child).where(
        Child.chat_id == marriage.chat_id, Child.marriage_id == marriage.id,
    ).values(marriage_id=None))
    await session.execute(update(Pregnancy).where(
        Pregnancy.chat_id == marriage.chat_id, Pregnancy.marriage_id == marriage.id,
        Pregnancy.status == "active",
    ).values(status="cancelled"))
    await session.execute(delete(MarriageMember).where(
        MarriageMember.chat_id == marriage.chat_id, MarriageMember.marriage_id == marriage.id,
    ))
    await session.execute(update(FamilyRequest).where(
        FamilyRequest.chat_id == marriage.chat_id, FamilyRequest.marriage_id == marriage.id,
        FamilyRequest.status == "pending",
    ).values(status="cancelled"))
    return (
        "Брак расторгнут. Дети сохраняются в детдоме и вернутся при новом браке между "
        "теми же игроками в этом чате. Текущие беременности отменены."
    )


async def sex(session: AsyncSession, marriage: Marriage, now: float) -> str:
    if marriage.next_sex > now:
        raise GameError(f"Следующий /sex: {availability(marriage.next_sex, now)}")
    marriage.next_sex = now + HOUR
    first = await session.get(Player, (marriage.chat_id, marriage.first_id))
    second = await session.get(Player, (marriage.chat_id, marriage.second_id))
    carrier = (
        random.choice((first, second)) if first.length == second.length
        else min((first, second), key=lambda player: player.length)
    )
    pregnancy = await session.scalar(select(Pregnancy.id).where(
        Pregnancy.chat_id == marriage.chat_id, Pregnancy.carrier_id == carrier.user_id,
        Pregnancy.status == "active",
    ))
    result = "👬 Вы занялись сексом."
    if pregnancy is not None:
        result += "\nУ супруга с меньшим размером уже есть беременность."
    elif carrier.pregnancy_available_at > now:
        result += f"\nДля новой беременности ещё действует пауза после родов: {availability(carrier.pregnancy_available_at, now)}"
    elif random.random() < 0.25:
        session.add(Pregnancy(
            chat_id=marriage.chat_id, marriage_id=marriage.id, carrier_id=carrier.user_id,
            conceived_at=now, due_at=now + PREGNANCY_DURATION, status="active",
        ))
        name = await player_name(session, carrier.user_id)
        result += f"\n🫃 {name} забеременел! Роды: {moscow_time(now + PREGNANCY_DURATION)}."
    else:
        result += "\nБеременность не наступила."
    return result + f"\nСледующий /sex: {availability(marriage.next_sex, now)}"


async def respond(
    session: AsyncSession, chat_id: int, actor_id: int, now: float, accept: bool,
    request_id: int | None = None, message_id: int | None = None,
) -> str:
    query = select(FamilyRequest).where(FamilyRequest.chat_id == chat_id)
    if request_id is not None:
        query = query.where(FamilyRequest.id == request_id)
        if message_id is not None:
            query = query.where(FamilyRequest.message_id == message_id)
    elif message_id is not None:
        query = query.where(FamilyRequest.message_id == message_id)
    else:
        raise GameError("Укажи номер предложения или ответь на сообщение бота с предложением.")
    request = await session.scalar(query)
    if request is None:
        raise GameError("Предложение в этом чате не найдено.")
    if (request.initiator_id != actor_id and request.recipient_id != actor_id) or (request.initiator_id == actor_id and accept):
        raise GameError("Это предложение должен подтвердить его адресат от своего имени.")
    if request.status != "pending":
        raise GameError("Это предложение уже обработано или отменено.")
    if request.expires_at <= now:
        request.status = "expired"
        return "Срок предложения истёк. Создайте новое."
    if not accept:
        request.status = "declined"
        return f"Предложение №{request.id} отклонено или отменено."
    try:
        if request.kind == "marry":
            result = await marry(session, request, now)
        else:
            marriage = await require_marriage(session, chat_id, request.initiator_id)
            if marriage.id != request.marriage_id:
                raise GameError("Предложение относится к уже завершённому браку.")
            if request.kind == "divorce":
                result = await divorce(session, marriage, now)
            elif request.kind == "sex":
                result = await sex(session, marriage, now)
            else:
                child = await session.get(Child, request.child_id)
                if child is None or child.chat_id != chat_id or child.marriage_id != marriage.id:
                    raise GameError("Этот ребёнок больше не принадлежит вашей семье.")
                await session.delete(child)
                await session.execute(update(FamilyRequest).where(
                    FamilyRequest.chat_id == chat_id, FamilyRequest.child_id == request.child_id,
                    FamilyRequest.kind == "orphanage", FamilyRequest.status == "pending",
                ).values(status="cancelled"))
                result = f"Ребёнок №{request.child_id} сдан в детдом и удалён. Восстановить его нельзя."
        request.status = "accepted"
        return result
    except GameError as error:
        request.status = "cancelled"
        return f"Предложение отменено: {error}"


async def name_child(
    session: AsyncSession, chat_id: int, actor_id: int, child_id: int, name: str,
) -> str:
    name = name.strip()
    if not 1 <= len(name) <= 64 or any(ord(char) < 32 for char in name):
        raise GameError("Имя должно содержать от 1 до 64 символов, без переносов строк.")
    marriage = await require_marriage(session, chat_id, actor_id)
    child = await session.get(Child, child_id)
    if child is None or child.chat_id != chat_id or child.marriage_id != marriage.id:
        raise GameError("Этот ребёнок не принадлежит вашей семье.")
    child.name = name
    return f"Ребёнка №{child.id} теперь зовут {name}."


async def family_info(session: AsyncSession, chat_id: int, user_id: int, now: float) -> list[str]:
    marriage = await current_marriage(session, chat_id, user_id)
    if marriage is None:
        return ["👬 В этом чате ты не состоишь в браке."]
    partner = await player_name(session, marriage.partner(user_id))
    lines = [
        f"👨‍❤️‍👨 Муж: {partner}.",
        f"В браке {duration(now - marriage.started_at)} (с {moscow_time(marriage.started_at)}).",
        f"Следующий /sex: {availability(marriage.next_sex, now)}",
    ]
    pregnancies = await session.scalars(select(Pregnancy).where(
        Pregnancy.chat_id == chat_id, Pregnancy.marriage_id == marriage.id, Pregnancy.status == "active",
    ).order_by(Pregnancy.due_at))
    for pregnancy in pregnancies:
        name = await player_name(session, pregnancy.carrier_id)
        lines.append(f"🫃 {name}: роды {moscow_time(pregnancy.due_at)} (через {duration(pregnancy.due_at - now)}).")
    for spouse_id in (marriage.first_id, marriage.second_id):
        player = await session.get(Player, (chat_id, spouse_id))
        if player.pregnancy_available_at > now:
            name = await player_name(session, spouse_id)
            lines.append(f"{name}: пауза после родов до {moscow_time(player.pregnancy_available_at)}.")
    children = await family_children(session, chat_id, marriage.id)
    lines.append(f"Детей в семье: {len(children)}.")
    for child in children:
        lines.append(
            f"• {child.display_name} (ID {child.id}), возраст {duration(now - child.born_at)}, "
            f"размер {child.length:,} см; следующий /dick: {availability(child.next_dick, now)}"
        )
    return lines


async def couples(session: AsyncSession, chat_id: int, order: str, page: int, now: float) -> str:
    if order not in {"duration", "children"} or page < 1:
        raise GameError("Использование: /couples [duration|children] [страница от 1].")
    total = await session.scalar(select(func.count()).select_from(Marriage).where(
        Marriage.chat_id == chat_id, Marriage.ended_at.is_(None),
    ))
    if (page - 1) * 10 >= total:
        return "На этой странице нет пар."
    count = func.count(Child.id).label("children_count")
    query = (
        select(Marriage, count)
        .outerjoin(Child, (Child.marriage_id == Marriage.id) & (Child.chat_id == Marriage.chat_id))
        .where(Marriage.chat_id == chat_id, Marriage.ended_at.is_(None))
        .group_by(Marriage.id)
    )
    if order == "children":
        query = query.order_by(count.desc())
    query = query.order_by(Marriage.started_at, Marriage.id).offset((page - 1) * 10).limit(10)
    rows = (await session.execute(query)).all()
    if not rows:
        return "На этой странице нет пар."
    lines = [f"👨‍❤️‍👨 Пары чата — {'по длительности брака' if order == 'duration' else 'по числу детей'}:"]
    for position, (marriage, children_count) in enumerate(rows, (page - 1) * 10 + 1):
        first = await player_name(session, marriage.first_id)
        second = await player_name(session, marriage.second_id)
        lines.append(
            f"{position}. {first} и {second}: {duration(now - marriage.started_at)}, детей: {children_count}."
        )
    lines.append(f"Страница {page}/{max(1, (total + 9) // 10)}. /couples {order} <страница>")
    return "\n".join(lines)
