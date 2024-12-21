import random
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message as TgMessage, InputMediaPhoto
from aiogram.client.default import DefaultBotProperties

from pydantic import BaseModel

import asyncio

from sia.character import SiaCharacter
from sia.memory.memory import SiaMemory
from sia.memory.schemas import SiaMessageGeneratedSchema, SiaMessageSchema
from sia.clients.client_interface import SiaClientInterface
from utils.logging_utils import enable_logging, log_message, setup_logging


class SiaTelegram(SiaClientInterface):
    
    def __init__(
        self,
        sia,
        bot_token: str,
        chat_id: str,
        character: SiaCharacter = None,
        memory: SiaMemory = None,
        logging_enabled=True,
        testing=False,
    ):
        print("Initializing Telegram bot...")  # Debug print
        self.bot = Bot(
            token=bot_token, 
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        print(f"Bot created with token: {bot_token[:8]}...")  # Debug print
        
        self.dp = Dispatcher()
        self.chat_id = str(chat_id)
        print(f"Watching chat ID: {self.chat_id}")  # Debug print
        
        super().__init__(
            sia=sia,
            logging_enabled=logging_enabled,
            client=self.bot
        )

        self.testing = testing
        self.logger = setup_logging()
        if self.testing:
            self.logger_testing = setup_logging(
                logger_name="testing", log_filename="testing.log"
            )
        enable_logging(logging_enabled)

        self.sia = sia
        
        # Register message handler
        print("Setting up handlers...")  # Debug print
        self.setup_handlers()
        print("Handlers set up")  # Debug print

    def setup_handlers(self):
        """Set up message handlers"""
        print("Setting up message handlers...")  # Debug print

        @self.dp.message(F.chat.type.in_({"group", "supergroup"}))
        async def message_handler(message: TgMessage):
            print(f"Handler triggered! Message: {message.text}")  # Debug print
            await self._handle_group_message(message)
            
        print("Message handlers set up")  # Debug print

        
    def telegram_message_to_sia_message(
        self, message: TgMessage
    ) -> SiaMessageGeneratedSchema:
        return SiaMessageGeneratedSchema(
            conversation_id=str(message.chat.id),
            content=message.text,
            platform="telegram",
            author=message.from_user.username or str(message.from_user.id),
            character=self.sia.character.name,
            response_to=str(message.reply_to_message.message_id) if message.reply_to_message else None,
            wen_posted=message.date,
            flagged=0,
            metadata=None,
        )

    async def publish_message(
        self,
        message: SiaMessageGeneratedSchema,
        media: List[str] = None,
        in_reply_to_message_id: str = None,
    ) -> str:
        
        try:
            # Send text message or media
            if media:
                media_group = [InputMediaPhoto(media=open(file, 'rb')) for file in media]
                sent_messages = await self.bot.send_media_group(
                    chat_id=int(message.conversation_id),
                    media=media_group,
                    reply_to_message_id=int(in_reply_to_message_id.split("-")[-1]) if in_reply_to_message_id else None
                )
                return str(sent_messages[0].message_id)
            else:
                sent_message = await self.bot.send_message(
                    chat_id=int(message.conversation_id),
                    text=message.content,
                    reply_to_message_id=int(in_reply_to_message_id.split("-")[-1]) if in_reply_to_message_id else None
                )
                return str(sent_message.message_id)

        except Exception as e:
            log_message(
                self.logger, "error", self, f"Failed to send message: {e}"
            )
            return None

    async def _handle_group_message(self, message: TgMessage):
        """Handle incoming messages"""
        log_message(self.logger, "info", self, f"Processing message: {message.text}")

        try:
            # Convert Telegram message to Sia message format
            sia_message = self.telegram_message_to_sia_message(message)
            message_id = self.sia.character.platform_settings.get("telegram", {}).get("post", {}).get("chat_id", "") + "-" + str(message.message_id)
            
            # Save message to database
            stored_message = self.sia.memory.add_message(
                message_id=message_id,
                message=sia_message
            )
            
            log_message(self.logger, "info", self, f"Stored message: {stored_message}")

            # Respond to mentions
            if f"@{self.sia.character.platform_settings.get('telegram', {}).get('username', '<no_username>')}" in message.text:
                log_message(self.logger, "info", self, f"Responding to mention: {message.text}")

                # Generate and send response if appropriate
                if self.sia.character.responding.get("enabled", True):
                    response = self.sia.generate_response(stored_message)
                    if response:
                        await self.publish_message(
                            response,
                            in_reply_to_message_id=str(message.message_id)
                        )

            else:
                log_message(self.logger, "info", self, f"No mention found: {message.text}")

        except Exception as e:
            log_message(self.logger, "error", self, f"Error handling message: {e}")

    async def post(self):
        """Implementation of periodic posting"""
        if not self.sia.character.platform_settings.get("telegram", {}).get("post", {}).get("enabled", False):
            return
        
        chat_id = self.sia.character.platform_settings.get("telegram", {}).get("post", {}).get("chat_id", "")


        # check if it is
        #   time to post

        post_frequency = (
            self.sia.character.platform_settings.get("telegram", {})
            .get("post", {})
            .get("frequency", 1)
        )
        latest_post = self.sia.memory.get_messages(
            platform="telegram",
            character=self.sia.character.name,
            author=self.sia.character.platform_settings.get("telegram", {}).get("username", ""),
            is_post=True,
            conversation_id=chat_id,
            sort_by="wen_posted",
            sort_order="desc"
        )

        latest_post = latest_post[0] if latest_post else None
        next_post_time = latest_post.wen_posted + timedelta(hours=post_frequency) if latest_post else datetime.now()-timedelta(seconds=10)
        log_message(self.logger, "info", self, f"Next post time: {next_post_time}, datetime.now(): {datetime.now()}")
        
        if datetime.now() > next_post_time:
            log_message(self.logger, "info", self, "It's time to post!")
            post, media = self.sia.generate_post(
                platform="telegram",
                author=self.sia.character.platform_settings.get("telegram", {}).get("username", ""),
                character=self.sia.character.name,
                conversation_id=chat_id
            )

            if post or media:
                message_id = await self.publish_message(post) # , media
                if message_id:
                    self.sia.memory.add_message(message_id=f"{chat_id}-{message_id}", message=post, message_type="post")
                    
                    # # Update next post time
                    # self.sia.character.platform_settings["telegram"] = {
                    #     "next_post_time": time.time() + 
                    #         self.sia.character.platform_settings.get("telegram", {}).get("post_frequency", 2) * 3600
                    # }
                    # self.sia.memory.update_character_settings(character_settings)


    async def run(self):
        """Main loop to run the Telegram bot"""
        if not self.sia.character.platform_settings.get("telegram", {}).get("enabled", True):
            return

        try:
            log_message(self.logger, "info", self, "Starting Telegram bot...")
            print("Starting polling...")  # Debug print
            
            # Create background task for posting
            async def periodic_post():
                while True:
                    await self.post()
                    await asyncio.sleep(60)  # Check every minute
            
            # Start both the polling and posting tasks
            await asyncio.gather(
                self.dp.start_polling(
                    self.bot,
                    allowed_updates=["message"],
                    skip_updates=False
                ),
                periodic_post()
            )
            
        except Exception as e:
            log_message(self.logger, "error", self, f"Error in main loop: {e}")
            return False

        return True