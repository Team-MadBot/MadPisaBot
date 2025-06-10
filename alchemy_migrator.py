import asyncio
import datetime
import sqlite3

from db import ChatRepository, ChatUserRepository, UserCacheRepository

async def main():
    db = sqlite3.connect("database_old.db", autocommit=True)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    cur.execute("SELECT DISTINCT chat_id FROM user")
    chats_id = cur.fetchall()

    print("Migrating chats...")
    for chat_id in chats_id:
        await ChatRepository.create_chat(
            chat_id=chat_id["chat_id"],
            thing_name="писюн",
            thing_metric="см"
        )
    
    print("Migrating users....")
    cur.execute("SELECT * FROM user")
    users = cur.fetchall()
    for user in users:
        new_user = await ChatUserRepository.create_user(
            chat_id=user["chat_id"],
            user_id=user["user_id"],
            thing_value=user["length"]
        )
        user_next_dick = user["next_dick"] or 0
        if int(datetime.datetime(year=2222, month=12, day=31).timestamp()) < user_next_dick:
            user_next_dick = datetime.datetime(year=2222, month=12, day=31).timestamp()
        await ChatUserRepository.update_cooldown(
            chat_id=new_user.chat_id,
            user_id=new_user.user_id,
            timestamp=datetime.datetime.fromtimestamp(user_next_dick or 0)
        )
    
    print("Migrating user caches...")
    cur.execute("SELECT * FROM user_cache")
    user_caches = cur.fetchall()
    for user_cache in user_caches:
        await UserCacheRepository.create_user_cache(
            user_id=user_cache["user_id"],
            user_name=user_cache["user_name"]
        )
    
    cur.close()
    db.close()
    print("done!")


asyncio.run(main())