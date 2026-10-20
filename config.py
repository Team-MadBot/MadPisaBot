import os

from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")
owners_id = (727261363, )
database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///database.db")
