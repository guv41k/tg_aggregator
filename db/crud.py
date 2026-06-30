import logging
from datetime import datetime

from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

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
            file_path=message_data.get("file_path"),
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
            .options(selectinload(Message.user))
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


def update_message_reactions(
    session: Session,
    chat_id: int,
    message_id: int,
    old_emojis: list[str],
    new_emojis: list[str],
) -> None:
    """Обновить реакции сообщения с учётом delta: убрать old_emojis, добавить new_emojis.

    Реакции хранятся как [{"emoji": "🔥", "count": N}].
    """
    try:
        msg = (
            session.query(Message)
            .filter(Message.id == message_id, Message.chat_id == chat_id)
            .first()
        )
        if msg is None:
            logger.debug(
                "Реакция пришла на несохранённое сообщение %s в чате %s",
                message_id,
                chat_id,
            )
            return

        counts: dict[str, int] = {
            r["emoji"]: r["count"]
            for r in (msg.reactions or [])
            if isinstance(r, dict)
        }

        for emoji in old_emojis:
            counts[emoji] = max(0, counts.get(emoji, 0) - 1)
        for emoji in new_emojis:
            counts[emoji] = counts.get(emoji, 0) + 1

        msg.reactions = [
            {"emoji": e, "count": c} for e, c in counts.items() if c > 0
        ]
        flag_modified(msg, "reactions")
        session.commit()
    except Exception:
        session.rollback()
        logger.exception(
            "Ошибка при обновлении реакций сообщения %s в чате %s",
            message_id,
            chat_id,
        )
        raise


def get_all_chats(session: Session) -> list[Chat]:
    """Вернуть все зарегистрированные чаты."""
    try:
        return session.query(Chat).order_by(Chat.title).all()
    except Exception:
        logger.exception("Ошибка при получении списка чатов")
        raise
