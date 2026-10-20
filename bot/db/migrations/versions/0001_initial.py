"""Import legacy SQLite and establish the transactional game schema."""
import math

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def fk(column, target):
    return sa.ForeignKeyConstraint(
        ["chat_id", column], [f"{target}.chat_id", f"{target}.{'user_id' if target == 'user' else 'id'}"],
        deferrable=True, initially="DEFERRED",
    )


def upgrade():
    connection = op.get_bind()
    existing = set(sa.inspect(connection).get_table_names())
    legacy = {}
    expected = {
        "user": ("chat_id", "user_id", "length", "next_dick"),
        "user_cache": ("user_id", "user_name"),
        "banned_user": ("user_id", "is_banned"),
    }
    unexpected = existing - set(expected) - {"alembic_version"}
    if unexpected:
        raise RuntimeError(f"Неизвестные таблицы без версии миграции: {', '.join(sorted(unexpected))}")
    for name, columns in expected.items():
        if name not in existing:
            continue
        table = sa.Table(name, sa.MetaData(), autoload_with=connection)
        if set(table.c.keys()) != set(columns):
            raise RuntimeError(f"Неожиданная структура таблицы {name}; миграция остановлена.")
        keys = [table.c.chat_id, table.c.user_id] if name == "user" else [table.c.user_id]
        duplicate = connection.execute(
            sa.select(*keys).group_by(*keys).having(sa.func.count() > 1).limit(1)
        ).first()
        if duplicate:
            raise RuntimeError(f"Дубликат ключа в {name}: {tuple(duplicate)}. Данные не изменены.")
        for row in connection.execute(sa.select(table)).mappings():
            integer_fields = ["chat_id", "user_id", "length"] if name == "user" else ["user_id"]
            if name == "banned_user":
                integer_fields.append("is_banned")
            if any(not isinstance(row[field], int) for field in integer_fields):
                raise RuntimeError(f"Некорректные целочисленные поля в {name}, user_id={row['user_id']}.")
            if name == "user":
                timestamp = row["next_dick"]
                if timestamp is not None and (
                    not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp)
                ):
                    raise RuntimeError(f"Некорректный next_dick, user_id={row['user_id']}.")
        legacy[name] = table

    for name in legacy:
        op.rename_table(name, f"legacy_{name}")

    op.create_table(
        "user",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("length", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("next_dick", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pregnancy_available_at", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_user_chat_length", "user", ["chat_id", "length"])
    op.create_table(
        "user_cache", sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_name", sa.String(), nullable=True),
    )
    op.create_table(
        "banned_user", sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("is_banned", sa.Integer(), nullable=False, server_default="1"),
    )
    for name in legacy:
        source = sa.Table(f"legacy_{name}", sa.MetaData(), autoload_with=connection)
        target = sa.Table(name, sa.MetaData(), autoload_with=connection)
        columns = list(expected[name])
        expressions = [
            sa.func.coalesce(source.c[column], 0) if column == "next_dick" else source.c[column]
            for column in columns
        ]
        connection.execute(target.insert().from_select(columns, sa.select(*expressions)))
        op.drop_table(f"legacy_{name}")

    op.create_table(
        "marriage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("first_id", sa.BigInteger(), nullable=False),
        sa.Column("second_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("ended_at", sa.Float(), nullable=True),
        sa.Column("next_sex", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("chat_id", "id"),
        sa.CheckConstraint("first_id < second_id", name="ordered_spouses"),
        fk("first_id", "user"), fk("second_id", "user"),
    )
    op.create_index("ix_marriage_chat_id", "marriage", ["chat_id"])
    op.create_table(
        "marriage_member",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("marriage_id", sa.Integer(), nullable=False),
        fk("user_id", "user"), fk("marriage_id", "marriage"),
    )
    op.create_table(
        "family_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("initiator_id", sa.BigInteger(), nullable=False),
        sa.Column("recipient_id", sa.BigInteger(), nullable=False),
        sa.Column("marriage_id", sa.Integer(), nullable=True),
        sa.Column("child_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.UniqueConstraint("chat_id", "message_id"),
        sa.CheckConstraint("kind IN ('marry', 'divorce', 'sex', 'orphanage')", name="request_kind"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'cancelled', 'expired')",
            name="request_status",
        ),
        fk("marriage_id", "marriage"),
    )
    op.create_index("ix_family_request_chat_id", "family_request", ["chat_id"])
    op.create_table(
        "pregnancy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("marriage_id", sa.Integer(), nullable=False),
        sa.Column("carrier_id", sa.BigInteger(), nullable=False),
        sa.Column("conceived_at", sa.Float(), nullable=False),
        sa.Column("due_at", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.UniqueConstraint("chat_id", "id"),
        sa.CheckConstraint("status IN ('active', 'born', 'cancelled')", name="pregnancy_status"),
        fk("carrier_id", "user"), fk("marriage_id", "marriage"),
    )
    op.create_index("ix_pregnancy_due_at", "pregnancy", ["due_at"])
    op.create_index(
        "uq_active_pregnancy", "pregnancy", ["chat_id", "carrier_id"],
        unique=True, sqlite_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "child",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("pregnancy_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("marriage_id", sa.Integer(), nullable=True),
        sa.Column("first_parent_id", sa.BigInteger(), nullable=False),
        sa.Column("second_parent_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(64), nullable=True),
        sa.Column("born_at", sa.Float(), nullable=False),
        sa.Column("length", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("next_dick", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notified_at", sa.Float(), nullable=True),
        sa.Column("notify_after", sa.Float(), nullable=False, server_default="0"),
        fk("marriage_id", "marriage"), fk("first_parent_id", "user"),
        fk("second_parent_id", "user"), fk("pregnancy_id", "pregnancy"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_child_family", "child", ["chat_id", "marriage_id"])


def downgrade():
    raise RuntimeError("Откат выполняется восстановлением резервной копии при остановленном боте.")
