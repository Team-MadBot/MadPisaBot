from sqlalchemy import (
    BigInteger, CheckConstraint, Float, ForeignKeyConstraint, Index, Integer,
    String, UniqueConstraint, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def player_fk(column: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["chat_id", column], ["user.chat_id", "user.user_id"],
        deferrable=True, initially="DEFERRED",
    )


def marriage_fk(column: str = "marriage_id") -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["chat_id", column], ["marriage.chat_id", "marriage.id"],
        deferrable=True, initially="DEFERRED",
    )


class Player(Base):
    __tablename__ = "user"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    length: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    # Epoch seconds are UTC. Float preserves fractional legacy timestamps.
    next_dick: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    pregnancy_available_at: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    __table_args__ = (Index("ix_user_chat_length", "chat_id", "length"),)


class UserCache(Base):
    __tablename__ = "user_cache"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_name: Mapped[str | None] = mapped_column(String)


class BannedUser(Base):
    __tablename__ = "banned_user"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    is_banned: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class Marriage(Base):
    __tablename__ = "marriage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    first_id: Mapped[int] = mapped_column(BigInteger)
    second_id: Mapped[int] = mapped_column(BigInteger)
    started_at: Mapped[float] = mapped_column(Float)
    ended_at: Mapped[float | None] = mapped_column(Float)
    next_sex: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    __table_args__ = (
        UniqueConstraint("chat_id", "id"),
        CheckConstraint("first_id < second_id", name="ordered_spouses"),
        player_fk("first_id"), player_fk("second_id"),
    )

    def partner(self, user_id: int) -> int:
        if user_id not in (self.first_id, self.second_id):
            raise ValueError("Игрок не является участником брака.")
        return self.second_id if user_id == self.first_id else self.first_id


class MarriageMember(Base):
    """Only current memberships; history remains in Marriage."""
    __tablename__ = "marriage_member"
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    marriage_id: Mapped[int] = mapped_column(Integer)
    __table_args__ = (player_fk("user_id"), marriage_fk())


class FamilyRequest(Base):
    __tablename__ = "family_request"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    initiator_id: Mapped[int] = mapped_column(BigInteger)
    recipient_id: Mapped[int] = mapped_column(BigInteger)
    marriage_id: Mapped[int | None] = mapped_column(Integer)
    # No FK: voluntary surrender deletes the child, but keeps request history.
    child_id: Mapped[int | None] = mapped_column(Integer)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    __table_args__ = (
        UniqueConstraint("chat_id", "message_id"),
        CheckConstraint("kind IN ('marry', 'divorce', 'sex', 'orphanage')", name="request_kind"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled', 'expired')",
            name="request_status",
        ),
        marriage_fk(),
    )


class Pregnancy(Base):
    __tablename__ = "pregnancy"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    marriage_id: Mapped[int] = mapped_column(Integer)
    carrier_id: Mapped[int] = mapped_column(BigInteger)
    conceived_at: Mapped[float] = mapped_column(Float)
    due_at: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    __table_args__ = (
        UniqueConstraint("chat_id", "id"),
        CheckConstraint("status IN ('active', 'born', 'cancelled')", name="pregnancy_status"),
        Index(
            "uq_active_pregnancy", "chat_id", "carrier_id", unique=True,
            sqlite_where=text("status = 'active'"),
        ),
        player_fk("carrier_id"), marriage_fk(),
    )


class Child(Base):
    __tablename__ = "child"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    pregnancy_id: Mapped[int] = mapped_column(Integer, unique=True)
    marriage_id: Mapped[int | None] = mapped_column(Integer)
    first_parent_id: Mapped[int] = mapped_column(BigInteger)
    second_parent_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str | None] = mapped_column(String(64))
    born_at: Mapped[float] = mapped_column(Float)
    length: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    next_dick: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    notified_at: Mapped[float | None] = mapped_column(Float)
    notify_after: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    __table_args__ = (
        marriage_fk(), player_fk("first_parent_id"), player_fk("second_parent_id"),
        ForeignKeyConstraint(
            ["chat_id", "pregnancy_id"], ["pregnancy.chat_id", "pregnancy.id"],
            deferrable=True, initially="DEFERRED",
        ),
        Index("ix_child_family", "chat_id", "marriage_id"),
        # Never reuse an ID referenced by an old surrender request.
        {"sqlite_autoincrement": True},
    )

    @property
    def display_name(self) -> str:
        return self.name or f"Ребёнок №{self.id}"
