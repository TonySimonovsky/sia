from utils.logging_utils import enable_logging, setup_logging
from sia.sia import Sia
from sia.testing.web_interface import WebTester
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

logger = setup_logging()
logging_enabled = True
enable_logging(logging_enabled)

async def main():
    character_name_id = os.getenv("CHARACTER_NAME_ID")
    testing_mode = os.getenv("TESTING_MODE", "false").lower() == "true"

    client_creds = {}
    if os.getenv("TW_API_KEY"):
        client_creds["twitter_creds"] = {
            "api_key": os.getenv("TW_API_KEY"),
            "api_secret_key": os.getenv("TW_API_KEY_SECRET"),
            "access_token": os.getenv("TW_ACCESS_TOKEN"),
            "access_token_secret": os.getenv("TW_ACCESS_TOKEN_SECRET"),
            "bearer_token": os.getenv("TW_BEARER_TOKEN"),
        }
    if os.getenv("TG_BOT_TOKEN"):
        client_creds["telegram_creds"] = {
            "bot_token": os.getenv("TG_BOT_TOKEN"),
        }

    sia = Sia(
        character_json_filepath=f"characters/{character_name_id}.json",
        **client_creds,
        memory_db_path=os.getenv("DB_PATH"),
        logging_enabled=logging_enabled,
    )

    if testing_mode:
        # Run in testing mode with web interface
        tester = WebTester(sia)
        tester.run()
    else:
        # Run normal mode
        sia.run()

if __name__ == "__main__":
    asyncio.run(main())
