import random

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Player
from bot.services.common import get_player, player_name
from bot.services.family import current_marriage, family_children, family_info
from bot.time import DICK_COOLDOWN, availability


def catchup_bonus(leader: int, length: int, roll: int) -> int:
    if roll <= 0:
        return 0
    # r * (max(1, (L - 42) / 420) - 1), rounded half up using integers.
    numerator = roll * max(0, leader - 462)
    rounded = (numerator + 210) // 420
    return min(rounded, max(0, leader - 42 - (length + roll)))


async def rank(session: AsyncSession, player: Player) -> int:
    await session.flush()
    return 1 + (await session.scalar(select(func.count()).select_from(Player).where(
        Player.chat_id == player.chat_id,
        or_(Player.length > player.length,
            (Player.length == player.length) & (Player.user_id < player.user_id)),
    )))


async def play(session: AsyncSession, chat_id: int, user_id: int, name: str, now: float) -> str:
    player = await get_player(session, chat_id, user_id)
    lines = []
    if player.next_dick <= now:
        leader = await session.scalar(select(func.max(Player.length)).where(Player.chat_id == chat_id))
        amount = random.randint(-5, 10)
        bonus = catchup_bonus(leader, player.length, amount)
        bonus_string = f" Бонус поддержки: +{bonus} см." if bonus > 0 else ""
        player.length += amount + bonus
        player.next_dick = now + DICK_COOLDOWN
        thing_name = "твой писюн увеличился" if player.length >= 0 else "твоя пизда увеличилась"
        lines.extend([
            f"{name}, {thing_name} на {abs(amount)} см." + bonus_string,
            f"Теперь размер составляет {player.length:,} см.",
            f"Теперь ты занимаешь {await rank(session, player)} место в топе.",
        ])
    else:
        lines.append(f"{name}, ты уже играл!")
    lines.append(f"Следующий /dick: {availability(player.next_dick, now)}")
    marriage = await current_marriage(session, chat_id, user_id)
    if marriage:
        for child in await family_children(session, chat_id, marriage.id):
            if child.next_dick <= now:
                amount = random.randint(-5, 10)
                child.length += amount
                child.next_dick = now + DICK_COOLDOWN
                lines.append(
                    f"• {child.display_name} (ID {child.id}): {amount:+} см, "
                    f"теперь {child.length:,} см. Следующий /dick: {availability(child.next_dick, now)}"
                )
    return "\n".join(lines)


async def info(session: AsyncSession, chat_id: int, user_id: int, name: str, now: float) -> str:
    player = await session.get(Player, (chat_id, user_id))
    if player is None:
        return f"{name} ещё не играл: размер 0 см. Используй /dick для игры.\n👬 В этом чате брака нет."
    thing_name = "твой писюн эквивалентен" if player.length >= 0 else "в твою пизду поместится"
    lines = [
        f"{name}, {thing_name} {abs(player.length):,} см.",
        f"Место в топе: {await rank(session, player)}.",
        f"Следующий /dick: {availability(player.next_dick, now)}",
        "",
        *await family_info(session, chat_id, user_id, now),
    ]
    if not await current_marriage(session, chat_id, user_id) and player.pregnancy_available_at > now:
        lines.append(f"Пауза после родов: {availability(player.pregnancy_available_at, now)}")
    return "\n".join(lines)


async def top_players(session: AsyncSession, chat_id: int) -> str:
    players = await session.scalars(select(Player).where(Player.chat_id == chat_id)
                                    .order_by(Player.length.desc(), Player.user_id).limit(15))
    lines = ["Топ 15 пипис:", ""]
    for position, player in enumerate(players, 1):
        name = await player_name(session, player.user_id)
        lines.append(f"{position}. {name}: {player.length:,} см.")
    return "\n".join(lines)
