import random
import textwrap
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from langchain.prompts import ChatPromptTemplate
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

import tweepy
from tweepy import Forbidden
from tweepy import Response as TwpResponse
from tweepy import Tweet
from tweepy import User as TwpUser

from sia.character import SiaCharacter
from sia.memory.memory import SiaMemory
from sia.memory.schemas import SiaMessageGeneratedSchema, SiaMessageSchema
from utils.logging_utils import enable_logging, log_message, setup_logging

from sia.clients.client_interface import SiaClientInterface


class SiaTwitterOfficial(SiaClientInterface):

    def __init__(
        self,
        sia,
        api_key,
        api_secret_key,
        access_token,
        access_token_secret,
        bearer_token,
        character: SiaCharacter = None,
        memory: SiaMemory = None,
        logging_enabled=True,
        testing=False,
    ):
        
        self.client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret_key,
            access_token=access_token,
            access_token_secret=access_token_secret,
            bearer_token=bearer_token,
            wait_on_rate_limit=True,
        )
        
        super().__init__(
            sia=sia,
            logging_enabled=logging_enabled,
            client=self.client
        )

        # self.client_dict_output = tweepy.Client(
        #     consumer_key=api_key, consumer_secret=api_secret_key,
        #     access_token=access_token, access_token_secret=access_token_secret,
        #     bearer_token=bearer_token,
        #     wait_on_rate_limit=True,
        #     return_type=dict
        # )

        self.testing = testing

        self.logger = setup_logging()
        if self.testing:
            self.logger_testing = setup_logging(
                logger_name="testing", log_filename="testing.log"
            )
        enable_logging(logging_enabled)

        self.api_key = api_key
        self.api_secret_key = api_secret_key
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.memory = memory
        self.character = character
        self.sia = sia

    def publish_message(
        self,
        message: SiaMessageGeneratedSchema,
        media: dict = [],
        in_reply_to_message_id: str = None
    ) -> str:

        media_ids = None
        if media:
            media_ids = []
            for m in media:
                media_ids.append(self.upload_media(m))

        try:
            print(f"message: {message}")
            print(f"media_ids: {media_ids}")
            print(f"in_reply_to_tweet_id: {in_reply_to_message_id}")

            response = self.client.create_tweet(
                text=message.content,
                **({"media_ids": media_ids} if media_ids else {}),
                # in_reply_to_tweet_id=in_reply_to_tweet_id
                **(
                    {"in_reply_to_tweet_id": in_reply_to_message_id}
                    if in_reply_to_message_id
                    else {}
                ),
            )
            print(f"Tweet sent successfully!: {response}")
            return response.data["id"]
        except Exception as e:
            print(f"Failed to send tweet: {e}")
            print(f"Response headers: {e.response.headers}")

    def upload_media(self, media_filepath):
        auth = tweepy.OAuth1UserHandler(self.api_key, self.api_secret_key)
        auth.set_access_token(
            self.access_token,
            self.access_token_secret,
        )
        client_v1 = tweepy.API(auth)

        media = client_v1.media_upload(filename=media_filepath)

        return media.media_id

    # def get_my_tweet_ids(self):
    #     log_message(self.logger, "info", self, f"Getting my tweet ids for {self.character.twitter_username}")
    #     my_tweets = self.memory.get_messages(platform="twitter", author=self.character.twitter_username)
    #     return [tweet.id for tweet in my_tweets]

    def tweet_to_message(
        self, tweet: Tweet, author: TwpUser
    ) -> SiaMessageGeneratedSchema:
        return SiaMessageGeneratedSchema(
            conversation_id=str(tweet.conversation_id),
            content=tweet.text,
            platform="twitter",
            author=author.username,
            # character=self.character.name,
            response_to=None,
            wen_posted=tweet.created_at,
            flagged=0,
            metadata=None,
        )

    def get_last_retrieved_reply_id(self):
        log_message(
            self.logger,
            "info",
            self,
            f"Getting last retrieved reply id for {
                self.character.twitter_username} (character: {
                self.character.name})",
        )
        replies = self.memory.get_messages(
            platform="twitter",
            not_author=self.character.twitter_username,
            character=self.character.name,
        )
        if replies:
            max_reply = max(replies, key=lambda reply: reply.id)
            return None if max_reply.id == "None" else max_reply.id

    def get_conversation(self, conversation_id: str) -> list[SiaMessageSchema]:
        messages = self.memory.get_messages(
            conversation_id=conversation_id,
            sort_by="wen_posted",
            sort_order="asc",
            flagged=False,
        )
        return messages

    def get_user_by_id_from_twp_response(
        self, twp_response: TwpResponse, user_id: int
    ) -> TwpUser:
        return next(
            (user for user in twp_response.includes["users"] if user.id == user_id),
            None,
        )

    @classmethod
    def search_tweets(
        self,
        query: str,
        start_time: datetime = None,
        end_time: datetime = None,
        tweet_fields: list[str] = [
            "conversation_id",
            "created_at",
            "in_reply_to_user_id",
            "public_metrics",
        ],
        max_results: int = 10,
        expansions: list[str] = [
            "author_id",
            "referenced_tweets.id",
            "referenced_tweets.id.author_id",
        ],
        since_id: str = None,
        client: tweepy.Client = None,
    ) -> TwpResponse:
        if not client:
            client = self.client

        search_inputs = {
            "query": query,
            "tweet_fields": tweet_fields,
            "max_results": max_results,
            "expansions": expansions,
            "start_time": start_time,
            "end_time": end_time,
        }
        if since_id:
            search_inputs["since_id"] = since_id

        tweets = client.search_recent_tweets(**search_inputs)

        return tweets

    def save_tweet_to_db(self, tweet: Tweet, author: TwpUser, message_type: str = "reply") -> SiaMessageSchema:

        # check if the tweet is already in the database
        get_message_in_db = self.memory.get_messages(
            id=str(tweet.id), flagged=2  # getting both flagged and unflagged messages
        )

        try:

            # if the tweet is already in the database
            #   we still need to add it to the return list
            if get_message_in_db:
                log_message(
                    self.logger,
                    "info",
                    self,
                    f"Message with id {
                        tweet.id} already exists in the database, returning it without adding to the database",
                )
                # if exclude_responded_to:
                #     message_responses_in_db = self.memory.get_messages(conversation_id=str(tweet.id), flagged=2)
                #     if message_responses_in_db:
                #         log_message(self.logger, "info", self, f"Message with id {tweet.id} has already been responded to")
                #         continue
                return get_message_in_db[0]

            # if the tweet is not in the database
            else:
                # convert tweet object
                #   to message object
                message_to_add = self.tweet_to_message(tweet=tweet, author=author)
                if self.testing:
                    message_to_add.flagged = 1
                    message_to_add.message_metadata = {"flagged": "test_data"}
                message_in_db = self.memory.add_message(
                    message_id=str(tweet.id),
                    message=message_to_add,
                    message_type=message_type
                )
                return message_in_db

        except Exception as e:
            log_message(
                self.logger, "error", self, f"Error saving tweet to database: {e}"
            )

    def save_tweets_to_db(
        self, tweets: TwpResponse, exclude_own=True, exclude_responded_to=False
    ) -> list[SiaMessageSchema]:
        messages = []
        # for tweet in tweets.data:
        #     self.memory.add_message(message_id=tweet.id, message=self.tweet_to_message(tweet, author))
        # return messages

        if not tweets.data:
            log_message(self.logger, "info", self, f"No tweets to add")
            return []

        for tweet in tweets.data:
            author = self.get_user_by_id_from_twp_response(tweets, tweet.author_id)
            log_message(
                self.logger,
                "info",
                self,
                f"[save_tweets_to_db] Processing tweet: {
                    tweet.id}, author {author}",
            )

            # exclude tweets from the character themselves
            #   as they've been added when creting and posting them
            if exclude_own:
                log_message(self.logger, "info", self, f"author of the tweet: {author}")
                if author == self.character.twitter_username:
                    continue

            # reasoning about if we need to flag the tweet
            try:
                from openai import OpenAI

                client = OpenAI()
                moderation_response = client.moderations.create(
                    model="omni-moderation-latest",
                    input=tweet.text,
                )
                flagged = moderation_response.results[0].flagged
                if flagged:
                    log_message(
                        self.logger,
                        "info",
                        self,
                        f"The tweet (id {
                            tweet.id}) ({
                            tweet.text.replace(
                                '\n', ' ')}) was flagged: {
                            moderation_response.results}",
                    )
            except Exception as e:
                log_message(self.logger, "error", self, f"Error moderating tweet: {e}")
                flagged = False

            tweet_message = self.save_tweet_to_db(tweet=tweet, author=author)

            # if we need to exclude from the return list
            #    the tweets that have already
            #    been responded to by the character,
            if exclude_responded_to:
                message_responses_in_db = self.memory.get_messages(
                    conversation_id=str(tweet.id),
                    author=self.character.twitter_username,
                    flagged=2,
                )
                if message_responses_in_db:
                    log_message(
                        self.logger,
                        "info",
                        self,
                        f"Message with id {
                            tweet.id} has already been responded to",
                    )
                    continue
                else:
                    if tweet_message:
                        messages.append(tweet_message)
            else:
                if tweet_message:
                    messages.append(tweet_message)

            # get_message_in_db = self.memory.get_messages(
            #     id=str(tweet.id),
            #     flagged=2 # getting both flagged and unflagged messages
            # )
            # try:
            #     # if the tweet is already in the database
            #     #   we still need to add it to the return list
            #     if get_message_in_db:
            #         log_message(self.logger, "info", self, f"Message with id {tweet.id} already exists in the database")
            #         if exclude_responded_to:
            #             message_responses_in_db = self.memory.get_messages(conversation_id=str(tweet.id), flagged=2)
            #             if message_responses_in_db:
            #                 log_message(self.logger, "info", self, f"Message with id {tweet.id} has already been responded to")
            #                 continue
            #         messages.append(get_message_in_db[0])
            #     else:
            #         # convert tweet object
            #         #   to message object
            #         message_to_add = self.tweet_to_message(tweet, author)
            #         if self.testing:
            #             message_to_add.flagged = 1
            #             message_to_add.message_metadata = { "flagged": "test_data" }
            #         message_in_db = self.memory.add_message(message_id=str(tweet.id), message=message_to_add)
            #         messages.append(message_in_db)

            # except Exception as e:
            #     print(f"Error adding message: {e}")
            # try:
            #     message_in_db = self.memory.get_messages(id=str(tweet.id), flagged=2)
            #     if exclude_responded_to:
            #         message_responses_in_db = self.memory.get_messages(conversation_id=str(tweet.id), flagged=2)
            #     else:
            #         message_responses_in_db = []
            #     # only add to return if we haven't responded to this tweet yet
            #     if message_in_db and not message_responses_in_db:
            #         log_message(self.logger, "info", self, f"Message with id {tweet.id} already exists in the database")
            #         messages.append(message_in_db[0])
            #     else:
            #         log_message(self.logger, "info", self, f"Message with id {tweet.id} not found in the database")
            #         continue
            # except Exception as e:
            #     log_message(self.logger, "error", self, f"Error retrieving message: {e}")

            # also add all referenced tweets
            if tweet.referenced_tweets:
                for ref_tweet in tweet.referenced_tweets:
                    # Get referenced tweet details
                    ref_tweet_id = ref_tweet.id

                    if "tweets" in tweets.includes:
                        for included_tweet in tweets.includes["tweets"]:
                            if included_tweet.id == ref_tweet_id:
                                try:
                                    author = self.get_user_by_id_from_twp_response(
                                        tweets, included_tweet.author_id
                                    )
                                    tweet_message = self.save_tweet_to_db(
                                        tweet=included_tweet, author=author
                                    )
                                    messages.append(tweet_message)

                                except Exception as e:
                                    log_message(
                                        self.logger,
                                        "error",
                                        self,
                                        f"Error adding referenced tweet: {e}",
                                    )

        return messages

    # # 2024.12.21: deprecated, now using search_tweets+save_tweets_to_db instead
    # def get_new_replies_to_my_tweets(self) -> list[SiaMessageSchema]:
    # since_id = self.get_last_retrieved_reply_id()
    # log_message(self.logger, "info", self, f"since_id: {since_id}")

    # messages = []

    # try:
    #     search_inputs = {
    #         "query": f"to:{self.character.twitter_username} OR @{self.character.twitter_username}",
    #         "client": self.client
    #     }
    #     if since_id:
    #         search_inputs["since_id"] = since_id

    #     new_replies_to_my_tweets = self.search_tweets(**search_inputs)
    # except Exception as e:
    #     log_message(self.logger, "error", self, f"Error getting replies: {e}")
    #     return []

    # if not new_replies_to_my_tweets.data:
    #     return []

    # for reply in new_replies_to_my_tweets.data:

    #     log_message(self.logger, "info", self, f"processing new mention: {reply}")

    #     # exclude replies from the character itself
    #     author = next((user.username for user in new_replies_to_my_tweets.includes['users'] if user.id == reply.author_id), None)
    #     log_message(self.logger, "info", self, f"author of the received reply: {author}")
    #     if author == self.character.twitter_username:
    #         continue

    #     try:
    #         from openai import OpenAI
    #         client = OpenAI()
    #         moderation_response = client.moderations.create(
    #             model="omni-moderation-latest",
    #             input=reply.text,
    #         )
    #         flagged = moderation_response.results[0].flagged
    #         if flagged:
    #             log_message(self.logger, "info", self, f"flagged reply: {reply.text}")
    #     except Exception as e:
    #         log_message(self.logger, "error", self, f"Error moderating reply: {e}")
    #         flagged = False

    #     try:
    #         message = self.memory.add_message(
    #             message_id=str(reply.id),
    #             message=SiaMessageGeneratedSchema(
    #                 conversation_id=str(reply.data['conversation_id']),
    #                 content=reply.text,
    #                 platform="twitter",
    #                 author=next(user.username for user in new_replies_to_my_tweets.includes['users'] if user.id == reply.author_id),
    #                 character=self.character.name,
    #                 response_to=str(next((ref.id for ref in reply.referenced_tweets if ref.type == "replied_to"), None)) if reply.referenced_tweets else None,
    #                 wen_posted=reply.created_at,
    #                 flagged=int(flagged),
    #                 metadata=moderation_response
    #             ),
    #             original_data=reply.data
    #         )
    #         messages.append(message)
    #     except Exception as e:
    #         log_message(self.logger, "error", self, f"Error adding message: {e}")

    # return messages

    # # 2024.12.17: deprecated, now using search_tweets+save_tweets_to_db instead
    # def search_and_collect_tweets(self, query: str, start_time: datetime = None, end_time: datetime = None) -> list[SiaMessageSchema]:
    #     tweets = self.client.search_recent_tweets(
    #         query=query,
    #         tweet_fields=[
    #             "conversation_id",
    #             "created_at",
    #             "in_reply_to_user_id",
    #             "public_metrics"
    #         ],
    #         max_results=30,
    #         expansions=["author_id","referenced_tweets.id"],
    #         start_time=start_time,
    #         end_time=end_time
    #     )

    #     messages = []

    #     if not tweets.data:
    #         log_message(self.logger, "info", self, f"No tweets found for query: {query}")
    #         return []

    #     for tweet in tweets.data:

    #         log_message(self.logger, "info", self, f"Processing tweet: {tweet.id}")

    #         try:
    #             author = self.get_user_by_id_from_twp_response(tweets, tweet.author_id)
    #             message_in_db = self.memory.add_message(message_id=tweet.id, message=self.tweet_to_message(tweet, author))
    #             messages.append(message_in_db)
    #         except Exception as e:
    #             log_message(self.logger, "error", self, f"Error adding message: {e}")
    #             continue

    #         # also add all referenced tweets
    #         if tweet.referenced_tweets:
    #             for ref_tweet in tweet.referenced_tweets:
    #                 # Get referenced tweet details
    #                 ref_tweet_id = ref_tweet.id

    #                 if 'tweets' in tweets.includes:
    #                     for included_tweet in tweets.includes['tweets']:
    #                         if included_tweet.id == ref_tweet_id:
    #                             try:
    #                                 author = self.get_user_by_id_from_twp_response(tweets, included_tweet.author_id)
    #                                 message_in_db = self.memory.add_message(message_id=included_tweet.id, message=self.tweet_to_message(included_tweet, author))
    #                                 messages.append(message_in_db)
    #                             except Exception as e:
    #                                 log_message(self.logger, "error", self, f"Error adding message: {e}")

    #     return messages

    @classmethod
    def printable_tweet(
        self,
        tweet_id,
        author_username,
        created_at,
        text,
        public_metrics,
        wrap_width=70,
        indent_width=5,
    ):
        output_str = ""
        output_str += f"{author_username} [{created_at}] (tweet id: {tweet_id}):\n"
        wrapped_comment = textwrap.fill(text.strip(), width=wrap_width)
        output_str += (
            " " * indent_width
            + wrapped_comment.replace("\n", "\n" + " " * indent_width)
            + "\n"
        )
        output_str += (
            " " * indent_width
            + f"(likes: {
            public_metrics.get(
                'like_count', 0)}, retweets: {
            public_metrics.get(
                'retweet_count', 0)}, replies: {
                    public_metrics.get(
                        'reply_count', 0)}, quotes: {
                            public_metrics.get(
                                'quote_count', 0)})"
        )

        return output_str

    @classmethod
    def printable_tweets_list(self, tweets):
        output_str = ""
        for tweet in tweets.data:
            author = next(
                (
                    user
                    for user in tweets.includes["users"]
                    if user.id == tweet.author_id
                ),
                None,
            )
            author_username = author.username if author else "Unknown"
            tweet_id = tweet.id

            if "referenced_tweets" in tweet:
                for ref_tweet in tweet.referenced_tweets:
                    ref_tweet_id = ref_tweet.id
                    ref_tweet_data = next(
                        (t for t in tweets.includes["tweets"] if t.id == ref_tweet_id),
                        None,
                    )
                    if ref_tweet_data:
                        ref_author = next(
                            (
                                user
                                for user in tweets.includes["users"]
                                if user.id == ref_tweet_data.author_id
                            ),
                            None,
                        )
                        ref_author_name = ref_author.name if ref_author else "Unknown"
                        output_str += self.printable_tweet(
                            tweet_id=ref_tweet_id,
                            author_username=ref_author_name,
                            created_at=ref_tweet_data.created_at,
                            text=ref_tweet_data.text,
                            public_metrics=ref_tweet_data.public_metrics,
                        )

            output_str += self.printable_tweet(
                tweet_id=tweet_id,
                author_username=author_username,
                created_at=tweet.created_at,
                text=tweet.text,
                public_metrics=tweet.public_metrics,
            )

            output_str += f"\n\n{'=' * 10}\n\n"

        return output_str

    # def tweets_obj_add(self, tweets1, tweets2):
    #     return TwpResponse(
    #         data=tweets1.data + tweets2.data,
    #         includes= { **tweets1.includes, **tweets2.includes },
    #         errors=tweets1.errors + tweets2.errors,
    #         meta= { **tweets1.meta, **tweets2.meta }
    #     )

    # def find_tweet_by_id_in_twp_response(self, tweets, tweet_id):
    # return next((tweet for tweet in tweets.data if tweet.id == tweet_id),
    # None)

    def decide_which_tweet_to_reply_to(
        self, tweets: list[SiaMessageSchema]
    ) -> SiaMessageSchema:
        tweets_str_for_prompt = tweets[0].printable_list(tweets)

        class Decision(BaseModel):
            tweet_id: str
            tweet_username: str
            tweet_text: str
            decision_reasoning: str

        prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
                {you_are}

                Your objective is to select the most relevant tweet to respond to from the list of tweets provided below.

                Tweets:
                {tweets}
            """,
                ),
                (
                    "user",
                    """
                Generate your response to the tweet. Your response length must be fewer than 30 words.
            """,
                ),
            ]
        )

        ai_input = {
            "you_are": self.character.prompts.get("you_are"),
            "tweets": tweets_str_for_prompt,
        }

        try:
            llm = ChatAnthropic(model="claude-3-5-sonnet-20240620", temperature=0.0)
            llm_structured = llm.with_structured_output(Decision)

            ai_chain = prompt_template | llm_structured

            decision = ai_chain.invoke(ai_input)

        except Exception:

            try:
                llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
                llm_structured = llm.with_structured_output(Decision)

                ai_chain = prompt_template | llm_structured

                decision = ai_chain.invoke(ai_input)

            except Exception as e:
                log_message(
                    self.logger, "error", self, f"Error generating response: {e}"
                )
                return None

        if self.testing:
            log_message(
                self.logger_testing, "info", self, f"***Decision***:\n{decision}\n\n"
            )

        tweet = tweets[0].select_by_id_from_list(tweets, decision.tweet_id)

        return tweet

    # def exclude_tweet_messages_already_engaged(self, tweets: list[SiaMessageSchema]) -> list[SiaMessageSchema]:
    #     tweets_to_include = []
    #     for tweet in tweets:
    #         if tweet.id not in self.memory.get_conversation_ids():
    #             tweets_to_include.append(tweet)
    #     return tweets_to_include

    def post(self):

        character_settings = self.memory.get_character_settings()

        next_post_time = character_settings.character_settings.get("twitter", {}).get(
            "next_post_time", 0
        )
        next_post_datetime = (
            datetime.fromtimestamp(next_post_time).strftime("%Y-%m-%d %H:%M:%S")
            if next_post_time
            else "N/A"
        )
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Current time: {now_time}")
        next_post_time_seconds = next_post_time - time.time()
        next_post_hours = next_post_time_seconds // 3600
        next_post_minutes = (next_post_time_seconds % 3600) // 60
        print(
            f"Next post time: {next_post_datetime} (posting in {next_post_hours}h {next_post_minutes}m)"
        )

        if (
            self.character.platform_settings.get("twitter", {})
            .get("post", {})
            .get("enabled", False)
            and time.time() > next_post_time
        ):

            post, media = self.sia.generate_post(
                platform="twitter",
                author=self.character.twitter_username,
                # character=self.character.name,
            )

            if post or media:
                print(f"Generated post: {len(post.content)} characters")
                tweet_id = self.publish_message(message=post, media=media)
                if tweet_id and tweet_id is not Forbidden:
                    self.memory.add_message(message_id=tweet_id, message=post, message_type="post")

                    character_settings.character_settings = {
                        "twitter": {
                            "next_post_time": time.time()
                            + self.character.platform_settings.get("twitter", {}).get(
                                "post_frequency", 2
                            )
                            * 3600
                        }
                    }
                    self.memory.update_character_settings(character_settings)
            else:
                log_message(self.logger, "info", self, "No post or media generated.")

            time.sleep(30)

    def reply(self):

        if self.character.responding.get("enabled", True):
            log_message(self.logger, "info", self, "Checking for new replies...")

            # check for tweets
            #   where I'm tagged

            since_id = self.get_last_retrieved_reply_id()
            replies_search_inputs = {
                "query": f"to:{self.character.twitter_username} OR @{self.character.twitter_username}",
                "client": self.client,
            }
            if since_id:
                replies_search_inputs["since_id"] = since_id
            replies = self.search_tweets(**replies_search_inputs)
            replies_messages = self.save_tweets_to_db(tweets=replies, exclude_own=True)

            responses_sent = self.memory.get_messages(
                platform="twitter",
                character=self.character.name,
                author=self.character.twitter_username,
                sort_by="wen_posted",
                sort_order="desc",
            )
            responses_sent_this_hour = len(
                [
                    r
                    for r in responses_sent
                    if r.wen_posted > datetime.now() - timedelta(hours=1)
                ]
            )
            max_responses_an_hour = self.character.responding.get(
                "responses_an_hour", 3
            )
            log_message(
                self.logger,
                "info",
                self,
                f"Number of responses sent this hour: {responses_sent_this_hour}, max allowed: {max_responses_an_hour}",
            )

            if replies_messages:

                # randomize the order of replies
                replies_messages.sort(key=lambda x: random.random())

                for r in replies_messages:

                    log_message(self.logger, "info", self, f"Processing reply: {r}")

                    # skipping flagged
                    if r.flagged:
                        log_message(
                            self.logger, "info", self, f"Skipping flagged reply: {r}"
                        )
                        continue

                    # stopping when max responses per hour is reached
                    if responses_sent_this_hour >= max_responses_an_hour:
                        log_message(
                            self.logger,
                            "info",
                            self,
                            f"Max number of responses sent this hour reached. Skipping remaining replies.",
                        )
                        break

                    # temporary:
                    #   skipping conversations where
                    #   we've already sent 3+ replies
                    current_conversation = self.get_conversation(r.conversation_id)
                    own_messages_count = sum(
                        1
                        for msg in current_conversation
                        if msg.author == self.character.twitter_username
                    )
                    if own_messages_count >= 3:
                        log_message(
                            self.logger,
                            "info",
                            self,
                            f"Skipping conversation {
                                r.conversation_id} as it already has {own_messages_count} replies from us.",
                        )
                        continue

                    generated_response = self.sia.generate_response(r)
                    if not generated_response:
                        log_message(
                            self.logger, "error", self, f"No response generated"
                        )
                        continue

                    tweet_id = self.publish_message(
                        message=generated_response,
                        in_reply_to_message_id=r.id
                    )
                    self.memory.add_message(
                        message_id=tweet_id,
                        message=generated_response,
                        message_type="reply"
                    )

                    if isinstance(tweet_id, Forbidden):
                        log_message(
                            self.logger,
                            "error",
                            self,
                            f"Failed to send reply: {tweet_id}. Sleeping for 10 minutes.",
                        )
                        time.sleep(600)

                    time.sleep(random.randint(70, 90))

            else:
                log_message(self.logger, "info", self, "No new replies yet.")

    def engage(self, testing_rounds=3, search_period_hours=24):

        # do not do anything
        #   if engagement is not enabled
        #   and we are not in a testing mode
        if (
            not self.character.platform_settings.get("twitter", {})
            .get("engage", {})
            .get("enabled", False)
        ) and (not self.testing):
            return

        search_frequency = (
            self.character.platform_settings.get("twitter", {})
            .get("engage", {})
            .get("search_frequency", 1)
        )

        # check when we last engaged
        #   and if it's time to engage again

        messages_to_engage_in_db = self.memory.get_messages(
            platform="twitter",
            character=self.character.name,
            exclude_own_conversations=True,
            sort_by="wen_posted",
            sort_order="desc",
        )
        if messages_to_engage_in_db:
            latest_message = messages_to_engage_in_db[0]
            next_time_to_engage = latest_message.wen_posted + timedelta(
                hours=search_frequency
            )
            is_time_to_engage = datetime.now() > next_time_to_engage
            if not is_time_to_engage and not self.testing:
                log_message(
                    self.logger,
                    "info",
                    self,
                    f"Not the time to engage yet. Last time engaged: {
                        latest_message.wen_posted}, next time to engage: {next_time_to_engage}",
                )
                return
        else:
            is_time_to_engage = True

        # if we are not in testing mode, we will only do one round,
        #   rounds are needed only in testing mode
        if not self.testing:
            testing_rounds = 1
        for i in range(testing_rounds):

            # # Calculate time window for this round
            # end_time = datetime.now(timezone.utc) - timedelta(hours=search_frequency*i) - timedelta(seconds=23)
            # start_time = end_time - timedelta(hours=search_period_hours)

            start_time = (
                datetime.now(timezone.utc)
                - timedelta(hours=search_frequency * i + search_period_hours)
            ).isoformat()
            end_time = (
                datetime.now(timezone.utc)
                - timedelta(hours=search_frequency * i)
                - timedelta(seconds=23)
            )

            # search for tweets to engage with
            tweets_to_engage = []
            for search_query in (
                self.character.platform_settings.get("twitter", {})
                .get("engage", {})
                .get("search_queries", [])
            ):
                tweets = self.search_tweets(
                    query=search_query,
                    start_time=start_time,
                    end_time=end_time,
                    client=self.client,
                )
                tweets_messages = self.save_tweets_to_db(
                    tweets=tweets, exclude_responded_to=True
                )
                log_message(
                    self.logger,
                    "info",
                    self,
                    f"Found {
                        len(tweets_messages)} tweets to engage with",
                )
                # tweets_messages = self.exclude_tweet_messages_already_engaged(tweets_messages)
                # log_message(self.logger, "info", self, f"{len(tweets_messages)} tweets to engage with after excluding already engaged")
                tweets_to_engage.extend(tweets_messages)
            if not tweets_to_engage:
                log_message(
                    self.logger, "info", self, f"No tweets found to engage with"
                )
                continue
            if self.testing:
                log_message(
                    self.logger_testing,
                    "info",
                    self,
                    f"***Tweets to engage with***:\n{
                        tweets_to_engage[0].printable_list(tweets_to_engage)}\n\n",
                )

            # select a tweet to engage with
            tweet_to_respond = self.decide_which_tweet_to_reply_to(tweets_to_engage)
            if self.testing:
                log_message(
                    self.logger_testing,
                    "info",
                    self,
                    f"***Tweet to respond to***:\n{tweet_to_respond.printable()}\n\n",
                )

            # respond
            previous_messages = self.memory.printable_messages_list(
                self.memory.get_messages(
                    platform="twitter",
                    author=self.character.twitter_username,
                    sort_by="wen_posted",
                    sort_order="asc",
                    flagged=2,
                )[-20:]
            )
            if self.testing:
                log_message(
                    self.logger_testing,
                    "info",
                    self,
                    f"***Previous messages***:\n{previous_messages}\n\n",
                )

            ai_response = self.sia.generate_response(
                tweet_to_respond,
                use_filtering_rules=False,
                platform="twitter",
                previous_messages=previous_messages,
            )
            if self.testing:
                log_message(
                    self.logger_testing,
                    "info",
                    self,
                    f"***Response***:\n{ai_response}\n\n",
                )

            if not ai_response:
                log_message(
                    self.logger,
                    "error",
                    self,
                    f"No response generated for tweet: {tweet_to_respond}",
                )
                continue

            metadata = {}
            if not self.testing:
                tweet_id = self.publish_message(
                    message=ai_response,
                    media=None,
                    in_reply_to_message_id=tweet_to_respond.id
                )

                log_message(
                    self.logger, "info", self, f"Published response with id: {tweet_id}"
                )

                if self.testing:
                    log_message(
                        self.logger_testing,
                        "info",
                        self,
                        f"***Published response***:\nTweet id: {tweet_id}\n\n",
                    )

                metadata = {"flagged": "test_data"} if self.testing else {}
            else:
                tweet_id = str(uuid4())

            # save message to db
            message = self.memory.add_message(
                message_id=str(tweet_id),
                message=SiaMessageGeneratedSchema(
                    conversation_id=tweet_to_respond.id,
                    content=ai_response.content,
                    platform="twitter",
                    # character=self.character.name,
                    author=self.character.twitter_username,
                    response_to=tweet_to_respond.id,
                    wen_posted=datetime.now(timezone.utc),
                    flagged=int(self.testing),
                    metadata=metadata,
                    message_type="reply"
                ),
            )

    async def run(self):

        if not self.character.platform_settings.get("twitter", {}).get("enabled", True):
            return

        while 1:

            # character_settings = self.memory.get_character_settings()

            # next_post_time = character_settings.character_settings.get('twitter', {}).get('next_post_time', 0)
            # next_post_datetime = datetime.fromtimestamp(next_post_time).strftime('%Y-%m-%d %H:%M:%S') if next_post_time else "N/A"
            # now_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # print(f"Current time: {now_time}")
            # next_post_time_seconds = next_post_time - time.time()
            # next_post_hours = next_post_time_seconds // 3600
            # next_post_minutes = (next_post_time_seconds % 3600) // 60
            # print(f"Next post time: {next_post_datetime} (posting in {next_post_hours}h {next_post_minutes}m)")

            # from pydantic import BaseModel, Field
            # class Decision(BaseModel):
            #     text_idea: str | None = Field(description="The idea for the text of the tweet")
            #     text_usage_reasoning: str | None = Field(description="The reasoning for using the text idea")
            #     image_idea: str | None = Field(description="The idea for the image of the tweet")
            #     image_usage_reasoning: str | None = Field(description="The reasoning for using the image idea")
            #     meme_idea: str | None = Field(description="The idea for the meme of the tweet")
            #     meme_usage_reasoning: str | None = Field(description="The reasoning for using the meme idea")

            # decision_prompt = ChatPromptTemplate.from_messages([
            #     ("system", """
            #         # ABOUT YOU
            #         {you_are}

            #         # CONTEXT
            #         Now is {date_time}

            #         # YOUR TASK
            #         Your task is to come up with an idea of a tweet.

            #         # RESOURCES AND ABILITIES AVAILABLE TO YOU

            #         1. Media generation
            #         - dall-e image
            #         - meme

            #         # DECISIONS TO MAKE

            #         - if we use text in the tweet, decide an idea for the text (just a concept, example: about the implications of AI on workforce)
            #         - if you want to use any of the media available to you

            #         # RESPONSE FORMAT

            #         Respond in a valid json format with the following fields:
            #         - text_idea: None if no text is needed
            #         - text_usage_reasoning
            #         - image_idea: None if no picture is needed
            #         - image_usage_reasoning
            #         - meme_idea: None if no picture is needed
            #         - meme_usage_reasoning
            #     """),
            #     ("user", "make a decision"),
            # ])

            #         # 2. Knowledge sources:
            #         # - recent news
            #         # - information about crypto token $SIA

            #         # If any of the knowledge sources are used, your idea for the tweet must be based around the chosen source of knowledge. You must avoid inventing specific topic from the chosen source (as you don't know which specific knowledge is available within each category).

            #         # decisions to make:
            #         # - if you want to use any knowledge available to you

            #         # - knowledge_to_use: none if not needed to use

            # from langchain_openai import ChatOpenAI
            # decision_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            # decision_llm_structured = decision_llm.with_structured_output(Decision)
            # now_datetime = datetime.now().strftime('%Y-%m-%d %H:%M')
            # decision_chain = decision_prompt | decision_llm_structured
            # ai_decision = decision_chain.invoke(
            #     {
            #         "you_are": self.character.prompts.get("you_are", ""),
            #         "date_time": now_datetime
            #     }
            # )
            # print(f"\n\nAI decision: {ai_decision}\n\n")

            # posting
            #   new tweet
            self.post()

            # if self.character.platform_settings.get("twitter",
            # {}).get("post", {}).get("enabled", False) and time.time() >
            # next_post_time:

            #     post, media = self.sia.generate_post(
            #         platform="twitter",
            #         author=self.character.twitter_username,
            #         character=self.character.name
            #     )

            #     if post or media:
            #         print(f"Generated post: {len(post.content)} characters")
            #         tweet_id = self.publish_message(post, media)
            #         if tweet_id and tweet_id is not Forbidden:
            #             self.memory.add_message(message_id=tweet_id, message=post)

            #             character_settings.character_settings = {
            #                 "twitter": {
            #                     "next_post_time": time.time() + self.character.platform_settings.get("twitter", {}).get("post_frequency", 2) * 3600
            #                 }
            #             }
            #             self.memory.update_character_settings(character_settings)
            #     else:
            #         log_message(self.logger, "info", self, "No post or media generated.")

            #     time.sleep(30)

            # replying
            #   to mentions
            self.reply()

            # if self.character.responding.get("enabled", True):
            #     print("Checking for new replies...")

            #     replies = self.get_new_replies_to_my_tweets()
            #     if replies:

            #         # randomize the order of replies
            #         replies.sort(key=lambda x: random.random())

            #         for r in replies:

            #             max_responses_an_hour = character_settings.character_settings.get("responding", {}).get("responses_an_hour", 3)
            #             log_message(self.logger, "info", self, f"Replies sent during this hour: {replies_sent}, max allowed: {max_responses_an_hour}")
            #             if replies_sent >= max_responses_an_hour:
            #                 break

            #             # temporary: do not responsd in coversations where you've already sent 3 replies
            #             current_conversation = self.get_conversation(r.conversation_id)
            #             own_messages_count = sum(1 for msg in current_conversation if msg.author == self.character.twitter_username)
            #             if own_messages_count >= 3:
            #                 log_message(self.logger, "info", self, f"Skipping conversation {r.conversation_id} as it already has {own_messages_count} replies from us.")
            #                 continue

            #             print(f"Reply: {r}")
            #             if r.flagged:
            #                 print(f"Skipping flagged reply: {r}")
            #                 continue
            #             generated_response = self.sia.generate_response(r)
            #             if not generated_response:
            #                 print(f"No response generated for reply: {r}")
            #                 continue
            #             print(f"Generated response: {len(generated_response.content)} characters")
            #             tweet_id = self.sia.twitter.publish_message(post=generated_response, in_reply_to_tweet_id=r.id)
            #             self.memory.add_message(message_id=tweet_id, message=generated_response)
            #             replies_sent += 1
            #             if isinstance(tweet_id, Forbidden):
            #                 print(f"\n\nFailed to send reply: {tweet_id}. Sleeping for 10 minutes.\n\n")
            #                 time.sleep(600)
            #             time.sleep(random.randint(70, 90))
            #     else:
            #         print("No new replies yet.")
            #     print("\n\n")

            # searching for and replying
            #   to tweets from other users
            self.engage()

            # search_to_engage_frequency = character_settings.character_settings.get("engage", {}).get("search_frequency", 1)

            # if self.character.platform_settings.get("twitter",
            # {}).get("engage", {}).get("enabled", False):

            #     messages_to_engage = self.memory.get_messages(
            #         platform="twitter",
            #         character=self.character.name,
            #         exclude_own_conversations=True,
            #         sort_by="wen_posted",
            #         sort_order="desc"
            #     )
            #     latest_message = messages_to_engage[0]
            #     next_time_to_engage = latest_message.wen_posted + timedelta(hours=self.character.platform_settings.get("twitter", {}).get("engage", {}).get("post_frequency", 1))
            #     time_to_engage = datetime.now() > next_time_to_engage

            #     print(f"latest message datetime: {latest_message.wen_posted}")
            #     print(f"next time to engage: {next_time_to_engage}")
            #     print(f"is it time to engage?: {time_to_engage}")

            #     log_message(self.logger, "info", self, f"Searching for tweets to reply to")

            # for search in self.character.platform_settings.get("twitter",
            # {}).get("engage", {}).get("searches", []):

            #         tweets = self.search_and_collect_tweets(search)
            #         log_message(self.logger, "info", self, f"Found {len(tweets)} tweets to reply to")

            #         # tweets = self.client.search_recent_tweets(
            #         #     query=search,
            #         #     tweet_fields=[
            #         #         "conversation_id",
            #         #         "created_at",
            #         #         "in_reply_to_user_id",
            #         #         "public_metrics"
            #         #     ],
            #         #     max_results=30,
            #         #     expansions=["author_id","referenced_tweets.id"]
            #         # )

            time.sleep(random.randint(70, 90))
