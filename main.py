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
# from sia.clients.telegram.telegram_client import SiaTelegram
from sia.clients.twitter.twitter_official_api_client import SiaTwitterOfficial
from sia.modules.knowledge.GoogleNews.google_news import GoogleNewsModule

from tweepy import Forbidden

from utils.logging_utils import setup_logging, log_message, enable_logging

logger = setup_logging()
logging_enabled = True
enable_logging(logging_enabled)



async def main():
    character_name_id = os.getenv("CHARACTER_NAME_ID")

    sia = Sia(
        character_json_filepath=f"characters/{character_name_id}.json",
        twitter_creds = {
            "api_key": os.getenv("TW_API_KEY"),
            "api_secret_key": os.getenv("TW_API_KEY_SECRET"),
            "access_token": os.getenv("TW_ACCESS_TOKEN"),
            "access_token_secret": os.getenv("TW_ACCESS_TOKEN_SECRET"),
            "bearer_token": os.getenv("TW_BEARER_TOKEN")
        },
        memory_db_path=os.getenv("DB_PATH"),
        knowledge_module_classes=[GoogleNewsModule],
        logging_enabled=logging_enabled
    )
    
    # modules_settings = sia.get_modules_settings()
    # print(f"Modules settings: {modules_settings}")
    # print()
    # plugin = sia.get_plugin()
    # print(f"Plugin: {plugin}")
    # try:
    #     res = plugin.get_instructions_and_knowledge()
    #     print(f"Result: {res}")
    # except Exception as e:
    #     print(f"Error executing plugin: {e}")


    character_name = sia.character.name
    
    # my_tweet_ids = sia.twitter.get_my_tweet_ids()
    # print(f"My tweet ids: {my_tweet_ids}")
    
    
    # sia_previous_posts = sia.memory.get_messages()
    # print("Posts from memory:\n")
    # for post in sia_previous_posts[-10:]:
    #     print(post)
    #     print("\n")
    # print(f"{'*'*100}\n\n")


    # times_of_day = sia.character.times_of_day()
    
    start_time = time.time()
    
    replies_sent = 0
    
    # run for 55 minutes
    while time.time() - start_time < 3300:

        character_settings = sia.memory.get_character_settings()
        
        next_post_time = character_settings.character_settings.get('twitter', {}).get('next_post_time', 0)
        next_post_datetime = datetime.fromtimestamp(next_post_time).strftime('%Y-%m-%d %H:%M:%S') if next_post_time else "N/A"
        now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"Current time: {now_time}")
        next_post_time_seconds = next_post_time - time.time()
        next_post_hours = next_post_time_seconds // 3600
        next_post_minutes = (next_post_time_seconds % 3600) // 60
        print(f"Next post time: {next_post_datetime} (posting in {next_post_hours}h {next_post_minutes}m)")
        
        # posting
        #   new tweet
        if time.time() > next_post_time:
            post, media = sia.generate_post(
                platform="twitter",
                author=character_name,
                character=character_name
            )
            
            if post or media:
                print(f"Generated post: {len(post.content)} characters")
                tweet_id = sia.twitter.publish_post(post, media)
                if tweet_id and tweet_id is not Forbidden:
                    sia.memory.add_message(post, tweet_id)

                    character_settings.character_settings = {
                        "twitter": {
                            "next_post_time": time.time() + sia.character.platform_settings.get("twitter", {}).get("post_frequency", 2) * 3600
                        }
                    }
                    sia.memory.update_character_settings(character_settings)
            else:
                log_message(logger, "info", sia, "No post or media generated.")

            time.sleep(30)


        # replying
        #   to new replies
        
        if sia.character.responding.get("enabled", True):
            print("Checking for new replies...")
            replies = sia.twitter.get_new_replies_to_my_tweets()
            if replies:
                
                # randomize the order of replies
                replies.sort(key=lambda x: random.random())
                
                for r in replies:
                    
                    max_responses_an_hour = character_settings.character_settings.get("responding", {}).get("responses_an_hour", 3)
                    log_message(logger, "info", sia, f"Replies sent during this hour: {replies_sent}, max allowed: {max_responses_an_hour}")
                    if replies_sent >= max_responses_an_hour:
                        break

                    print(f"Reply: {r}")
                    if r.flagged:
                        print(f"Skipping flagged reply: {r}")
                        continue
                    generated_response = sia.generate_response(r)
                    if not generated_response:
                        print(f"No response generated for reply: {r}")
                        continue
                    print(f"Generated response: {len(generated_response.content)} characters")
                    tweet_id = sia.twitter.publish_post(post=generated_response, in_reply_to_tweet_id=r.id)
                    replies_sent += 1
                    if isinstance(tweet_id, Forbidden):
                        print(f"\n\nFailed to send reply: {tweet_id}. Sleeping for 10 minutes.\n\n")
                        time.sleep(600)
                    time.sleep(random.randint(20, 40))
            else:
                print("No new replies yet.")
            print("\n\n")

        time.sleep(random.randint(20, 40))



# Start the asyncio event loop
if __name__ == '__main__':
    asyncio.run(main())
