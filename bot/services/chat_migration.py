from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Child, FamilyRequest, Marriage, MarriageMember, Player, Pregnancy, UserCache
from bot.services.common import GameError


async def migrate_chat(session: AsyncSession, old_id: int, new_id: int):
    if old_id == new_id:
        return
    rows = (await session.execute(select(Player.chat_id, Player.user_id).where(
        (Player.chat_id == old_id) | (Player.user_id == old_id),
    ))).all()
    has_old_requests = await session.scalar(select(FamilyRequest.id).where(
        (FamilyRequest.chat_id == old_id)
        | (FamilyRequest.initiator_id == old_id)
        | (FamilyRequest.recipient_id == old_id),
    ).limit(1))
    old_cache = await session.get(UserCache, old_id)
    # Telegram may deliver both migrate_to and migrate_from. The second event
    # must not invalidate proposals already created in the new supergroup.
    if not rows and has_old_requests is None and old_cache is None:
        return
    destinations = set()
    original = set(rows)
    for chat_id, user_id in rows:
        target = (new_id if chat_id == old_id else chat_id, new_id if user_id == old_id else user_id)
        if target in destinations or (target not in original and await session.get(Player, target)):
            raise GameError("Перенос чата остановлен: конфликт профилей. Обратитесь к владельцу бота.")
        destinations.add(target)
    # Foreign keys are deferred until commit so the whole graph can move together.
    for model in (Player, Marriage, MarriageMember, FamilyRequest, Pregnancy, Child):
        await session.execute(update(model).where(model.chat_id == old_id).values(chat_id=new_id))
    await session.execute(update(Player).where(Player.user_id == old_id).values(user_id=new_id))
    await session.execute(update(MarriageMember).where(MarriageMember.user_id == old_id).values(user_id=new_id))
    await session.execute(update(Pregnancy).where(Pregnancy.carrier_id == old_id).values(carrier_id=new_id))
    for model, first_column, second_column in (
        (Marriage, Marriage.first_id, Marriage.second_id),
        (Child, Child.first_parent_id, Child.second_parent_id),
    ):
        first = case((first_column == old_id, new_id), else_=first_column)
        second = case((second_column == old_id, new_id), else_=second_column)
        await session.execute(update(model).where(
            (first_column == old_id) | (second_column == old_id),
        ).values({first_column: func.min(first, second), second_column: func.max(first, second)}))
    for column in (FamilyRequest.initiator_id, FamilyRequest.recipient_id):
        await session.execute(update(FamilyRequest).where(column == old_id).values({column: new_id}))
    # Message IDs can change during a Telegram chat migration: do not retain stale reply mappings.
    await session.execute(update(FamilyRequest).where(
        FamilyRequest.chat_id == new_id, FamilyRequest.status == "pending",
    ).values(status="cancelled", message_id=None))
    if old_cache:
        if await session.get(UserCache, new_id):
            await session.delete(old_cache)
        else:
            old_cache.user_id = new_id
