import logging
from datetime import datetime

from sqlalchemy.orm import Session

from db.models import Chat, Message, User

logger = logging.getLogger(__name__)


def upsert_user(session: Session, user_data: dict) -> User:
    """Создать или обновить запись пользователя."""
    try:
        user = session.get(User, user_data["id"])
        if user is None:
            user = User(id=user_data["id"])
            session.add(user)
        user.username = user_data.get("username")
        user.first_name = user_data.get("first_name")
        user.last_name = user_data.get("last_name")
        session.commit()
        return user
    except Exception:
        session.rollback()
        logger.exception("Ошибка при upsert пользователя id=%s", user_data.get("id"))
        raise


def upsert_chat(session: Session, chat_data: dict) -> Chat:
    """Создать или обновить запись чата."""
    try:
        chat = session.get(Chat, chat_data["id"])
        if chat is None:
            chat = Chat(id=chat_data["id"])
            session.add(chat)
        chat.title = chat_data.get("title")
        chat.type = chat_data.get("type")
        session.commit()
        return chat
    except Exception:
        session.rollback()
        logger.exception("Ошибка при upsert чата id=%s", chat_data.get("id"))
        raise


def save_message(session: Session, message_data: dict) -> Message:
    """Сохранить сообщение. Если уже существует — пропустить."""
    try:
        msg = session.get(Message, message_data["id"])
        if msg is not None:
            return msg
        msg = Message(
            id=message_data["id"],
            chat_id=message_data["chat_id"],
            user_id=message_data.get("user_id"),
            text=message_data.get("text"),
            media_type=message_data.get("media_type"),
            file_id=message_data.get("file_id"),
            reactions=message_data.get("reactions"),
            timestamp=message_data.get("timestamp", datetime.utcnow()),
        )
        session.add(msg)
        session.commit()
        return msg
    except Exception:
        session.rollback()
        logger.exception("Ошибка при сохранении сообщения id=%s", message_data.get("id"))
        raise


def get_messages_by_period(
    session: Session,
    chat_id: int,
    date_from: datetime,
    date_to: datetime,
) -> list[Message]:
    """Вернуть список сообщений чата за указанный период."""
    try:
        return (
            session.query(Message)
            .filter(
                Message.chat_id == chat_id,
                Message.timestamp >= date_from,
                Message.timestamp <= date_to,
            )
            .order_by(Message.timestamp)
            .all()
        )
    except Exception:
        logger.exception("Ошибка при выборке сообщений chat_id=%s", chat_id)
        raise


def get_all_chats(session: Session) -> list[Chat]:
    """Вернуть все зарегистрированные чаты."""
    try:
        return session.query(Chat).order_by(Chat.title).all()
    except Exception:
        logger.exception("Ошибка при получении списка чатов")
        raise
