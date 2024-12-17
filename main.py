import time
import asyncio
import os
import random
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from sia.sia import Sia
from sia.character import SiaCharacter
from sia.memory.memory import SiaMemory
from sia.clients.telegram.telegram_client import SiaTelegram
from sia.clients.twitter.twitter_official_api_client import SiaTwitterOfficial
from sia.modules.knowledge.GoogleNews.google_news import GoogleNewsModule

from tweepy import Forbidden

from utils.logging_utils import setup_logging, log_message, enable_logging

logger = setup_logging()
logging_enabled = True
enable_logging(logging_enabled)



async def main():
    character_name_id = os.getenv("CHARACTER_NAME_ID")
    
    client_creds = {}
    if os.getenv("TW_API_KEY"):
        client_creds["twitter_creds"] = {
            "api_key": os.getenv("TW_API_KEY"),
            "api_secret_key": os.getenv("TW_API_KEY_SECRET"),
            "access_token": os.getenv("TW_ACCESS_TOKEN"),
            "access_token_secret": os.getenv("TW_ACCESS_TOKEN_SECRET"),
            "bearer_token": os.getenv("TW_BEARER_TOKEN")
        }
    if os.getenv("TG_BOT_TOKEN"):
        client_creds["telegram_creds"] = {
            "tg_bot_token": os.getenv("TG_BOT_TOKEN"),
        }
    
    sia = Sia(
        character_json_filepath=f"characters/{character_name_id}.json",
        **client_creds,
        memory_db_path=os.getenv("DB_PATH"),
        # knowledge_module_classes=[GoogleNewsModule],
        logging_enabled=logging_enabled
    )
    
    await sia.run()
    

if __name__ == '__main__':
    asyncio.run(main())
