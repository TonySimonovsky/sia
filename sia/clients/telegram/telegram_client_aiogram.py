import random
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message as TgMessage, InputMediaPhoto
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramConflictError

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

    async def handle_telegram_conflict(bot: Bot, retries=3):
        for attempt in range(retries):
            try:
                return await bot.get_updates()
            except TelegramConflictError as e:
                print(f"Conflict detected (attempt {attempt + 1}/{retries})")
                if attempt == retries - 1:  # Last attempt
                    print("Clearing webhook as last resort...")
                    await bot.delete_webhook(drop_pending_updates=True)
                else:
                    # Wait with exponential backoff before retry
                    await asyncio.sleep(1 * (attempt + 1))
        
        raise Exception("Could not resolve Telegram conflict after clearing webhook")
        
    def telegram_message_to_sia_message(
        self, message: TgMessage
    ) -> SiaMessageGeneratedSchema:
        return SiaMessageGeneratedSchema(
            conversation_id=str(message.chat.id),
            content=message.text,
            platform="telegram",
            author=message.from_user.username or str(message.from_user.id),
            # character=self.sia.character.name,
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
                from aiogram.types import FSInputFile
                media_group = [InputMediaPhoto(media=FSInputFile(file)) for file in media]
                # media_group = [InputMediaPhoto(media=open(file, 'rb')) for file in media]
                sent_messages = await self.bot.send_media_group(
                    chat_id=int(message.conversation_id),
                    media=media_group,
                    reply_to_message_id=int(in_reply_to_message_id.split("-")[-1]) if in_reply_to_message_id else None
                )
                return str(sent_messages[0].message_id)
                # sent_messages = await self.bot.send_media_group(
                #     chat_id=int(message.conversation_id),
                #     media=media_group,
                #     reply_to_message_id=int(in_reply_to_message_id.split("-")[-1]) if in_reply_to_message_id else None
                # )
                # return str(sent_messages[0].message_id)
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
        log_message(self.logger, "info", self, f"Processing message id {message.message_id} in chat {message.chat.id}: {message.text}")
        
        chat_id = message.chat.id

        try:
            # Convert Telegram message to Sia message format
            sia_message = self.telegram_message_to_sia_message(message)
            message_id = f"{chat_id}-{str(message.message_id)}"
            
            # Save message to database
            stored_message = self.sia.memory.add_message(
                message_id=message_id,
                message=sia_message,
                character=self.sia.character.name
            )
            
            log_message(self.logger, "info", self, f"Stored message: {stored_message}")

            should_respond = False

            # Check for direct mentions
            if f"@{self.sia.character.platform_settings.get('telegram', {}).get('username', '<no_username>')}" in message.text:
                log_message(self.logger, "info", self, f"Responding to mention: {message.text}")
                should_respond = True
            # Check if message is a reply to bot's message
            elif message.reply_to_message and message.reply_to_message.from_user.username == self.sia.character.platform_settings.get('telegram', {}).get('username'):
                log_message(self.logger, "info", self, f"Responding to reply to bot's message: {message.text}")
                should_respond = True

            if should_respond and self.sia.character.responding.get("enabled", True):
                response = self.sia.generate_response(stored_message)
                if response:
                    message_id = await self.publish_message(
                        response,
                        in_reply_to_message_id=str(message.message_id)
                    )
                    self.sia.memory.add_message(
                        message_id=f"{chat_id}-{message_id}",
                        message=response,
                        message_type="reply",
                        character=self.sia.character.name
                    )
            else:
                log_message(self.logger, "info", self, f"No mention or reply to bot found: {message.text}")

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
        log_message(self.logger, "info", self, f"Post frequency: {post_frequency}")
        log_message(self.logger, "info", self, f"Latest post: {latest_post}")
        log_message(self.logger, "info", self, f"Next post time: {next_post_time}, datetime.now(): {datetime.now()}")
        
        if datetime.now() > next_post_time:
            log_message(self.logger, "info", self, "It's time to post!")
            post, media = self.sia.generate_post(
                platform="telegram",
                author=self.sia.character.platform_settings.get("telegram", {}).get("username", ""),
                # character=self.sia.character.name,
                conversation_id=chat_id
            )

            if post or media:
                message_id = await self.publish_message(message=post, media=media)
                if message_id:
                    self.sia.memory.add_message(
                        message_id=f"{chat_id}-{message_id}", 
                        message=post, 
                        message_type="post",
                        character=self.sia.character.name
                    )
                    
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

        async def start_polling_with_retry(retries=3):
            for attempt in range(retries):
                try:
                    log_message(
                        self.logger,
                        "info",
                        self,
                        f"Starting polling attempt {attempt + 1}/{retries}"
                    )
                    
                    # First, try to delete any existing webhook
                    await self.bot.delete_webhook(drop_pending_updates=True)
                    
                    # Wait a moment for the webhook deletion to take effect
                    await asyncio.sleep(1)
                    
                    return await self.dp.start_polling(
                        self.bot,
                        allowed_updates=["message"],
                        skip_updates=True,  # Changed to True to avoid conflicts
                        handle_signals=False
                    )
                    
                except TelegramConflictError as e:
                    log_message(
                        self.logger,
                        "warning",
                        self,
                        f"Conflict detected (attempt {attempt + 1}/{retries}): {e}"
                    )
                    
                    # Clear any pending updates and webhook before retrying
                    await self.bot.delete_webhook(drop_pending_updates=True)
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
                except Exception as e:
                    log_message(
                        self.logger,
                        "error",
                        self,
                        f"Unexpected error during polling attempt: {e}"
                    )
                    if attempt == retries - 1:
                        raise

        async def periodic_post():
            while True:
                try:
                    await self.post()
                except Exception as e:
                    log_message(
                        self.logger,
                        "error",
                        self,
                        f"Error in periodic post: {e}"
                    )
                finally:
                    await asyncio.sleep(60)  # Check every minute

        try:
            log_message(self.logger, "info", self, "Starting Telegram bot...")
            
            # Create tasks
            polling_task = asyncio.create_task(start_polling_with_retry())
            posting_task = asyncio.create_task(periodic_post())
            
            # Wait for both tasks
            await asyncio.gather(
                polling_task,
                posting_task,
                return_exceptions=True
            )
            
        except asyncio.CancelledError:
            log_message(self.logger, "info", self, "Bot shutdown requested")
        except Exception as e:
            log_message(
                self.logger,
                "error",
                self,
                f"Critical error in main loop: {e}"
            )
            return False
        finally:
            # Cleanup
            try:
                await self.bot.session.close()
                log_message(self.logger, "info", self, "Bot session closed")
            except Exception as e:
                log_message(
                    self.logger,
                    "error",
                    self,
                    f"Error during cleanup: {e}"
                )

        return True