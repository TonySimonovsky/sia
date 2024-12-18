from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, asc, desc, or_, and_
from .models_db import SiaMessageModel, SiaCharacterSettingsModel, Base
from .schemas import SiaMessageSchema, SiaMessageGeneratedSchema, SiaCharacterSettingsSchema
from sia.character import SiaCharacter
import json
import textwrap

from utils.logging_utils import setup_logging, log_message, enable_logging

class SiaMemory:

    def __init__(self, db_path: str, character: SiaCharacter):
        self.db_path = db_path
        self.character = character
        self.engine = create_engine(self.db_path)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.logging_enabled = self.character.logging_enabled

        self.logger = setup_logging()
        enable_logging(self.logging_enabled)


    def add_message(self, message_id: str, message: SiaMessageGeneratedSchema, original_data: dict = None) -> SiaMessageSchema:
        session = self.Session()

        message_model = SiaMessageModel(
            id=str(message_id),
            platform=message.platform,
            character=message.character,
            author=message.author,
            content=message.content,
            conversation_id=message.conversation_id or message.id,
            response_to=message.response_to,
            flagged=message.flagged,
            message_metadata=message.message_metadata,
            original_data=original_data
        )
        
        try:
            # Serialize original_data if it's a dictionary
            if isinstance(original_data, dict):
                original_data = json.dumps(original_data)

            session.add(message_model)
            session.commit()

            # Convert the model to a schema
            message_schema = SiaMessageSchema.from_orm(message_model)
            return message_schema
        
        except Exception as e:
            log_message(self.logger, "error", self, f"Error adding message to database: {e}")
            log_message(self.logger, "error", self, f"message type: {type(message)}")
            session.rollback()
            raise e
        
        finally:
            session.close()
        

    def get_messages(self, id=None, platform: str = None, author: str = None, not_author: str = None, character: str = None, conversation_id: str = None, flagged: bool = False, sort_by: str = None, sort_order: str = "asc", is_post: bool = None, from_datetime=None, exclude_own_conversations: bool = False):
        session = self.Session()
        query = session.query(SiaMessageModel)
        if id:
            query = query.filter_by(id=id)
        if character:
            query = query.filter_by(character=character)
        if platform:
            query = query.filter_by(platform=platform)
        if author:
            query = query.filter_by(author=author)
        if not_author:
            query = query.filter(SiaMessageModel.author != not_author)
        if conversation_id:
            query = query.filter_by(conversation_id=conversation_id)
        if from_datetime:
            query = query.filter(SiaMessageModel.wen_posted >= from_datetime)

        # Exclude messages from conversations that we initiated
        if exclude_own_conversations:
            # Get conversation_ids where we were the initial poster
            our_initiated_conversations = session.query(SiaMessageModel.conversation_id).filter(
                and_(
                    SiaMessageModel.author == self.character.twitter_username,
                    SiaMessageModel.id == SiaMessageModel.conversation_id  # This identifies the initial post
                )
            ).distinct().subquery()
            
            # Then exclude messages from these conversations
            query = query.filter(
                ~SiaMessageModel.conversation_id.in_(our_initiated_conversations)
            )
            
        # if is_post is not None:
        if is_post:
            # For posts: id matches conversation_id or conversation_id is None
            query = query.filter(or_(
                SiaMessageModel.id == SiaMessageModel.conversation_id,
                SiaMessageModel.conversation_id == None
            ))

        query = query.filter_by(flagged=flagged)

        if sort_by:
            if sort_order == "asc":
                query = query.order_by(asc(sort_by))
            else:
                query = query.order_by(desc(sort_by))
        posts = query.all()
        session.close()
        return [SiaMessageSchema.from_orm(post) for post in posts]
    
    
    def get_conversation_ids(self):
        session = self.Session()
        conversation_ids = session.query(SiaMessageModel.conversation_id).filter(SiaMessageModel.id != SiaMessageModel.conversation_id).distinct().all()
        session.close()
        return [conversation_id[0] for conversation_id in conversation_ids]
    
    
    def clear_messages(self):
        session = self.Session()
        session.query(SiaMessageModel).filter_by(character=self.character.name).delete()
        session.commit()
        session.close()


    def reset_database(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)


    @classmethod
    def printable_message(self, message_id, author_username, created_at, text, wrap_width=70, indent_width=5):
        output_str = ""
        output_str += f"{author_username} [{created_at}] (message id: {message_id}):\n"
        wrapped_comment = textwrap.fill(text.strip(), width=wrap_width)
        output_str += ' ' * indent_width + wrapped_comment.replace('\n', '\n' + ' ' * indent_width) + "\n"

        return output_str

    @classmethod
    def printable_messages_list(self, messages):
        output_str = ""
        for message in messages:
            message_id = message.id

            output_str += self.printable_message(message_id=message_id, author_username=message.author, created_at=message.wen_posted, text=message.content)
            
            output_str += f"\n\n{'='*10}\n\n"

        return output_str



    def get_character_settings(self):
        session = self.Session()
        try:
            character_settings = session.query(SiaCharacterSettingsModel).filter_by(character_name_id=self.character.name_id).first()
            if not character_settings:
                character_settings = SiaCharacterSettingsModel(
                    character_name_id=self.character.name_id,
                    character_settings={}
                )
                session.add(character_settings)
                session.commit()
            
            # Convert the SQLAlchemy model to a Pydantic schema before closing the session
            character_settings_schema = SiaCharacterSettingsSchema.from_orm(character_settings)
            return character_settings_schema

        finally:
            session.close()
    
        
    def update_character_settings(self, character_settings: SiaCharacterSettingsSchema):
        session = self.Session()
        # Convert the Pydantic schema to a dictionary
        character_settings_dict = character_settings.dict(exclude_unset=True)
        session.query(SiaCharacterSettingsModel).filter_by(character_name_id=self.character.name_id).update(character_settings_dict)
        session.commit()
        session.close()
