import os
import re

from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")
owners_id = (7475155639, 727261363)


def get_fake_base(
    chat_id: int, 
    user_id: int,
    length: int = 0,
    next_dick: int = 0,
    married_id: int | None = None
):
    return {
        "chat_id": chat_id,
        "user_id": user_id,
        "length": length,
        "next_dick": next_dick,
        "married_with": married_id,
        "fake": True,
        "anal_radius": 0
    }

def escape_markdown(string: str):
    MARKDOWN_QUOTE_PATTERN = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")
    return re.sub(pattern=MARKDOWN_QUOTE_PATTERN, repl="\\\1", string=string)
