from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Player, UserCache


class GameError(Exception):
    """A user-facing rejection of a game operation."""


async def cache_name(session: AsyncSession, user_id: int, name: str):
    statement = insert(UserCache).values(user_id=user_id, user_name=name)
    await session.execute(statement.on_conflict_do_update(
        index_elements=[UserCache.user_id], set_={"user_name": name},
    ))


async def player_name(session: AsyncSession, user_id: int) -> str:
    cached = await session.get(UserCache, user_id)
    return (cached.user_name if cached else None) or f"Игрок {user_id}"


async def get_player(session: AsyncSession, chat_id: int, user_id: int) -> Player:
    player = await session.get(Player, (chat_id, user_id))
    if player is None:
        player = Player(chat_id=chat_id, user_id=user_id, length=0, next_dick=0, pregnancy_available_at=0)
        session.add(player)
        await session.flush()
    return player
