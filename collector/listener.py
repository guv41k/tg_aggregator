import logging
import pathlib
from datetime import datetime

from telegram import Bot, Update, Message as TGMessage
from telegram.ext import Application, MessageHandler, MessageReactionHandler, filters, ContextTypes

from config import COLLECTOR_TOKEN
from db.crud import save_message, upsert_chat, upsert_user, update_message_reactions
from db.session import SessionLocal

logger = logging.getLogger(__name__)

MEDIA_ROOT = pathlib.Path("media")

MEDIA_EXTENSIONS = {
    "photo": ".jpg",
    "voice": ".ogg",
    "video": ".mp4",
    "video_note": ".mp4",
    "audio": ".mp3",
    "sticker": ".webp",
}


def _extract_media(message: TGMessage) -> tuple[str | None, str | None]:
    if message.photo:
        return "photo", message.photo[-1].file_id
    if message.document:
        return "document", message.document.file_id
    if message.video:
        return "video", message.video.file_id
    if message.voice:
        return "voice", message.voice.file_id
    if message.audio:
        return "audio", message.audio.file_id
    if message.video_note:
        return "video_note", message.video_note.file_id
    if message.sticker:
        return "sticker", message.sticker.file_id
    return None, None


async def download_media(
    bot: Bot,
    message: TGMessage,
    media_type: str,
    file_id: str,
    chat_id: int,
) -> str | None:
    try:
        if media_type == "document" and message.document and message.document.file_name:
            ext = pathlib.Path(message.document.file_name).suffix or ".bin"
        elif media_type == "audio" and message.audio and message.audio.file_name:
            ext = pathlib.Path(message.audio.file_name).suffix or ".mp3"
        else:
            ext = MEDIA_EXTENSIONS.get(media_type, ".bin")

        ts = message.date.strftime("%Y%m%d%H%M%S") if message.date else "unknown"
        filename = f"{chat_id}_{message.message_id}_{ts}{ext}"

        dest_dir = MEDIA_ROOT / media_type
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        tg_file = await bot.get_file(file_id)
        await tg_file.download_to_drive(dest_path)

        relative_path = dest_path.as_posix()
        logger.info("Скачан файл: %s", relative_path)
        return relative_path

    except Exception:
        logger.warning(
            "Не удалось скачать %s для сообщения %s (chat %s)",
            media_type,
            message.message_id,
            chat_id,
            exc_info=True,
        )
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if message is None or chat is None:
        return

    media_type, file_id = _extract_media(message)

    file_path = None
    if media_type and file_id:
        file_path = await download_media(context.bot, message, media_type, file_id, chat.id)

    user_data = None
    if user is not None:
        user_data = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }

    chat_data = {
        "id": chat.id,
        "title": chat.title or chat.full_name,
        "type": chat.type,
    }

    message_data = {
        "id": message.message_id,
        "chat_id": chat.id,
        "user_id": user.id if user else None,
        "text": message.text or message.caption,
        "media_type": media_type,
        "file_id": file_id,
        "file_path": file_path,
        "reactions": None,  # реакции приходят отдельным событием (MessageReactionUpdated)
        "timestamp": message.date or datetime.utcnow(),
    }

    with SessionLocal() as session:
        try:
            upsert_chat(session, chat_data)
            if user_data:
                upsert_user(session, user_data)
            save_message(session, message_data)
            logger.debug(
                "Сохранено сообщение %s из чата %s (%s)",
                message.message_id,
                chat.id,
                chat_data["title"],
            )
        except Exception:
            logger.exception(
                "Не удалось сохранить сообщение %s из чата %s",
                message.message_id,
                chat.id,
            )


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reaction_update = update.message_reaction
    if reaction_update is None:
        return

    chat_id = reaction_update.chat.id
    message_id = reaction_update.message_id

    # Фильтруем только emoji-реакции (бывают ещё кастомные)
    old_emojis = [r.emoji for r in (reaction_update.old_reaction or []) if hasattr(r, "emoji")]
    new_emojis = [r.emoji for r in (reaction_update.new_reaction or []) if hasattr(r, "emoji")]

    logger.debug(
        "Реакция: chat_id=%s, message_id=%s, old=%s, new=%s",
        chat_id, message_id, old_emojis, new_emojis,
    )

    with SessionLocal() as session:
        try:
            update_message_reactions(session, chat_id, message_id, old_emojis, new_emojis)
        except Exception:
            logger.exception(
                "Не удалось обновить реакции для сообщения %s в чате %s",
                message_id,
                chat_id,
            )


def build_collector_app() -> Application:
    app = Application.builder().token(COLLECTOR_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    app.add_handler(MessageReactionHandler(handle_reaction))
    logger.info("Бот-сборщик инициализирован")
    return app
