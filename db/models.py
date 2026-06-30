from datetime import datetime
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import relationship

from db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)  # Telegram user_id
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)

    messages = relationship("Message", back_populates="user")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(BigInteger, primary_key=True)  # Telegram chat_id
    title = Column(String(255), nullable=True)
    type = Column(String(50), nullable=True)  # private, group, supergroup, channel

    messages = relationship("Message", back_populates="chat")


class Message(Base):
    __tablename__ = "messages"

    id = Column(BigInteger, primary_key=True)  # Telegram message_id (внутри чата не уникален глобально)
    chat_id = Column(BigInteger, ForeignKey("chats.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    text = Column(Text, nullable=True)
    media_type = Column(String(50), nullable=True)   # photo, document, video, …
    file_id = Column(String(512), nullable=True)
    file_path = Column(String(1024), nullable=True)  # локальный путь к скачанному файлу
    reactions = Column(JSON, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    chat = relationship("Chat", back_populates="messages")
    user = relationship("User", back_populates="messages")
