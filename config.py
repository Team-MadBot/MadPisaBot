import os

from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("BOT_TOKEN") or ""
owners_id = (727261363, )
