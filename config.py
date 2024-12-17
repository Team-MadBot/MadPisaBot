import os

from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")
owners_id = (727261363, )

def get_fake_chat_info(
    chat_id: int,
    thing_name: str = "ум",
    thing_metric: str = "IQ",
    min_value: int = -5,
    max_value: int = 10
) -> dict:
    return {
        "chat_id": chat_id,
        "thing_name": thing_name,
        "thing_metric": thing_metric,
        "min_value": min_value,
        "max_value": max_value,
        "fake": True
    }
