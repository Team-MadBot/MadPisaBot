import sqlite3

db_old = sqlite3.connect("database.db")
db_new = sqlite3.connect("database_migrated.db")
db_old.row_factory = sqlite3.Row
db_new.row_factory = sqlite3.Row
cur_old = db_old.cursor()
cur_new = db_new.cursor()

cur_new.execute(
    """CREATE TABLE IF NOT EXISTS user (
        chat_id INTEGER,
        user_id INTEGER,
        length INTEGER DEFAULT(0),
        next_dick INTEGER DEFAULT(0),
        married_with INTEGER,
        anal_radius INTEGER DEFAULT(0)
    )
    """
)
cur_new.execute(
    """CREATE TABLE IF NOT EXISTS user_cache (
        user_id INTEGER UNIQUE NOT NULL,
        user_name TEXT
    )
    """
)
cur_new.execute(
    """CREATE TABLE IF NOT EXISTS chat_cache (
        chat_id INTEGER UNIQUE NOT NULL,
        chat_title TEXT
    )"""
)

for i in cur_old.execute("SELECT * FROM user").fetchall():
    cur_new.execute(
        "INSERT INTO user (chat_id, user_id, length, next_dick) VALUES (?, ?, ?, ?)",
        (i["chat_id"], i["user_id"], i["length"], i["next_dick"])
    )

for i in cur_old.execute("SELECT * FROM user_cache").fetchall():
    cur_new.execute(
        "INSERT INTO user_cache (user_id, user_name) VALUES (?, ?)",
        (i["user_id"], i["user_name"])
    )

db_new.commit()
