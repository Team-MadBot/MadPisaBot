import datetime
import enum
from typing import List
from typing import Optional

from sqlalchemy import delete
from sqlalchemy import ForeignKey
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import selectinload
from sqlalchemy.types import String


class DbBase(AsyncAttrs, DeclarativeBase):
    pass

class ThingForm(enum.Enum):
    MASCULINE = "masculine"
    FEMININE = "feminine"
    MIDDLE = "middle"

class ChatUser(DbBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.chat_id"), index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    thing_value: Mapped[int] = mapped_column(default=0)
    cooldown_timestamp: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    chat: Mapped['Chat'] = relationship(back_populates="users")

class Chat(DbBase):
    __tablename__ = "chats"

    chat_id: Mapped[int] = mapped_column(primary_key=True)
    thing_name: Mapped[str] = mapped_column(String(100), default="ум")  # Пользователь, ваш {thing_name} увеличился на 52 {thing_metric}
    thing_form: Mapped[ThingForm] = mapped_column(default=ThingForm.MASCULINE)
    thing_metric: Mapped[str] = mapped_column(String(100), default="IQ")
    random_min_value: Mapped[int] = mapped_column(default=-5)  # FIXME: random_min_value MUST be less then random_max_value
    random_max_value: Mapped[int] = mapped_column(default=10)
    users: Mapped[List[ChatUser]] = relationship(back_populates="chat")

class User(DbBase):
    __tablename__ = "botusers"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    is_feedback_banned: Mapped[bool] = mapped_column(default=False)
    user_name: Mapped[str] = mapped_column(default="Неизвестный")


engine = create_async_engine("sqlite+aiosqlite:///database.db")
async_session = async_sessionmaker(engine, expire_on_commit=False)


class DatabaseManager:
    @staticmethod
    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(DbBase.metadata.create_all)
    
    @staticmethod
    async def get_session() -> async_sessionmaker[AsyncSession]:
        return async_session


class ChatRepository:
    @staticmethod
    async def create_chat(
        chat_id: int,
        thing_name: Optional[str] = None,
        thing_metric: Optional[str] = None,
        thing_form: Optional[ThingForm] = None,
        random_min_value: Optional[int] = None,
        random_max_value: Optional[int] = None
    ) -> Chat:
        async with async_session() as session:
            chat = Chat(
                chat_id=chat_id,
                thing_name=thing_name,
                thing_metric=thing_metric,
                thing_form=thing_form,
                random_min_value=random_min_value,
                random_max_value=random_max_value
            )
            session.add(chat)
            await session.commit()
            await session.refresh(chat)
            return chat
    
    @staticmethod
    async def get_chat_by_id(chat_id: int) -> Optional[Chat]:
        async with async_session() as session:
            stmt = select(Chat).where(Chat.chat_id == chat_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    async def get_chat_with_users(chat_id: int) -> Optional[Chat]:
        async with async_session() as session:
            stmt = select(Chat).options(selectinload(Chat.users)).where(Chat.chat_id == chat_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    @staticmethod
    async def update_chat_settings(current_chat_id: int, **kwargs) -> bool:
        async with async_session() as session:
            stmt = update(Chat).where(Chat.chat_id == current_chat_id).values(**kwargs)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def delete_chat(chat_id: int) -> bool:
        async with async_session() as session:
            stmt = delete(Chat).where(Chat.chat_id == chat_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def get_all_chats() -> List[Chat]:
        async with async_session() as session:
            stmt = select(Chat)
            return list((await session.execute(stmt)).scalars().all())
    
    @staticmethod
    async def get_or_create_chat(chat_id: int, **kwargs) -> Chat:
        chat = await ChatRepository.get_chat_by_id(chat_id)
        if chat is None:
            chat = await ChatRepository.create_chat(chat_id=chat_id, **kwargs)
        return chat


class ChatUserRepository:
    @staticmethod
    async def create_user(
        chat_id: int, 
        user_id: int, 
        thing_value: Optional[int] = None
    ) -> ChatUser:
        async with async_session() as session:
            user = ChatUser(
                chat_id=chat_id,
                user_id=user_id,
                thing_value=thing_value
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    @staticmethod
    async def get_user(chat_id: int, user_id: int) -> Optional[ChatUser]:
        async with async_session() as session:
            stmt = select(ChatUser).where(
                ChatUser.chat_id == chat_id,
                ChatUser.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    async def get_any_user(user_id: int) -> Optional[ChatUser]:
        async with async_session() as session:
            stmt = select(ChatUser).where(
                ChatUser.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_with_chat(chat_id: int, user_id: int) -> Optional[ChatUser]:
        async with async_session() as session:
            stmt = select(ChatUser).options(selectinload(ChatUser.chat)).where(
                ChatUser.chat_id == chat_id,
                ChatUser.user_id == user_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    @staticmethod
    async def update_user_value(chat_id: int, user_id: int, thing_value: int) -> bool:
        async with async_session() as session:
            stmt = update(ChatUser).where(
                ChatUser.chat_id == chat_id,
                ChatUser.user_id == user_id
            ).values(thing_value=thing_value)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def increment_user_value(chat_id: int, user_id: int, increment: int) -> bool:
        async with async_session() as session:
            stmt = update(ChatUser).where(
                ChatUser.chat_id == chat_id,
                ChatUser.user_id == user_id
            ).values(thing_value=ChatUser.thing_value + increment)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def migrate_user_id(old_user_id: int, new_user_id: int) -> bool:
        async with async_session() as session:
            stmt = update(ChatUser).where(ChatUser.user_id == old_user_id).values(user_id=new_user_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def update_cooldown(chat_id: int, user_id: int, timestamp: datetime.datetime) -> bool:
        async with async_session() as session:
            stmt = update(ChatUser).where(
                ChatUser.chat_id == chat_id,
                ChatUser.user_id == user_id
            ).values(cooldown_timestamp=timestamp)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    @staticmethod
    async def set_new_cooldown(chat_id: int, user_id: int) -> bool:
        return await ChatUserRepository.update_cooldown(
            chat_id=chat_id,
            user_id=user_id,
            timestamp=datetime.datetime.now() + datetime.timedelta(hours=12)
        )
    
    @staticmethod
    async def reset_cooldown(user_id: int) -> bool:
        async with async_session() as session:
            stmt = update(ChatUser).where(
                ChatUser.user_id == user_id
            ).values(cooldown_timestamp=datetime.datetime.now())
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def delete_user(chat_id: int, user_id: int) -> bool:
        async with async_session() as session:
            stmt = delete(ChatUser).where(
                ChatUser.chat_id == chat_id,
                ChatUser.user_id == user_id
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def get_users_by_chat(chat_id: int) -> List[ChatUser]:
        async with async_session() as session:
            stmt = select(ChatUser).where(ChatUser.chat_id == chat_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    @staticmethod
    async def get_top_users(chat_id: int, limit: int = 20) -> List[ChatUser]:
        async with async_session() as session:
            stmt = select(ChatUser).where(
                ChatUser.chat_id == chat_id
            ).order_by(ChatUser.thing_value.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    @staticmethod
    async def get_or_create_user(chat_id: int, user_id: int) -> ChatUser:
        user = await ChatUserRepository.get_user(chat_id, user_id)
        if user is None:
            user = await ChatUserRepository.create_user(chat_id, user_id)
        return user


class UserRepository:
    @staticmethod
    async def create_user(
        user_id: int,
        user_name: Optional[str] = None,
        is_feedback_banned: Optional[bool] = None
    ) -> User:
        async with async_session() as session:
            user = User(
                user_id=user_id,
                user_name=user_name,
                is_feedback_banned=is_feedback_banned
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[User]:
        async with async_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    
    @staticmethod
    async def update_user(user_id: int, **kwargs) -> bool:
        async with async_session() as session:
            stmt = update(User).where(User.user_id == user_id).values(**kwargs)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def migrate_user_id(old_user_id: int, new_user_id: int) -> bool:
        async with async_session() as session:
            stmt = update(User).where(User.user_id == old_user_id).values(user_id=new_user_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def delete_user(user_id: int) -> bool:
        async with async_session() as session:
            stmt = delete(User).where(User.user_id == user_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
    
    @staticmethod
    async def get_all_users() -> List[User]:
        async with async_session() as session:
            stmt = select(User)
            return list((await session.execute(stmt)).scalars().all())
    
    @staticmethod
    async def get_and_update_user(user_id: int, **kwargs) -> User:
        user = await UserRepository.get_user_by_id(user_id=user_id)
        if user is None:
            user = await UserRepository.create_user(user_id=user_id, **kwargs)
        else:
            await UserRepository.update_user(user_id=user_id, **kwargs)

        return user
