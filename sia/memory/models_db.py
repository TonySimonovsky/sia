from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class SiaMessageModel(Base):
    __tablename__ = "message"

    id = Column(String, primary_key=True)
    conversation_id = Column(String)
    character = Column(String)
    platform = Column(String, nullable=False)
    author = Column(String, nullable=False)
    content = Column(String, nullable=False)
    response_to = Column(String)
    message_type = Column(String, nullable=True)
    wen_posted = Column(DateTime, default=lambda: datetime.now())
    original_data = Column(JSON)
    flagged = Column(Boolean, nullable=True, default=False)
    message_metadata = Column(JSON)


class SiaCharacterSettingsModel(Base):
    __tablename__ = "character_settings"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    character_name_id = Column(String)
    character_settings = Column(JSON)
