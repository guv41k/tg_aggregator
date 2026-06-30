import logging
import pathlib
import zipfile
from datetime import datetime
from io import BytesIO

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from admin_bot.filters import AdminFilter
from config import BOT_TOKEN
from db.crud import get_all_chats, get_messages_by_period
from db.session import SessionLocal
from utils.formatters import format_messages

logger = logging.getLogger(__name__)

admin_filter = AdminFilter()

ZIP_SIZE_LIMIT = 50 * 1024 * 1024  # 50 МБ — лимит Telegram Bot API


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветствие администратора."""
    await update.message.reply_text(
        "Привет, администратор!\n\n"
        "Доступные команды:\n"
        "/chats — список отслеживаемых чатов\n"
        "/export <chat_id> <YYYY-MM-DD> <YYYY-MM-DD> — выгрузка переписки за период"
    )


async def cmd_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вывести список всех чатов, сохранённых в БД."""
    with SessionLocal() as session:
        try:
            chats = get_all_chats(session)
        except Exception:
            logger.exception("Ошибка при получении списка чатов")
            await update.message.reply_text("Ошибка при обращении к базе данных.")
            return

    if not chats:
        await update.message.reply_text("Пока ни одного чата не отслеживается.")
        return

    lines = ["<b>Отслеживаемые чаты:</b>"]
    for chat in chats:
        lines.append(f"• <b>{chat.title or '—'}</b> | id: <code>{chat.id}</code> | тип: {chat.type}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выгрузить переписку чата за период в виде ZIP-архива.

    Использование: /export <chat_id> <YYYY-MM-DD> <YYYY-MM-DD>
    """
    args = context.args
    if not args or len(args) < 3:
        await update.message.reply_text(
            "Использование: /export <chat_id> <YYYY-MM-DD> <YYYY-MM-DD>\n"
            "Пример: /export -1001234567890 2024-01-01 2024-01-31"
        )
        return

    try:
        chat_id = int(args[0])
        date_from = datetime.strptime(args[1], "%Y-%m-%d")
        date_to = datetime.strptime(args[2], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        await update.message.reply_text(
            "Неверный формат аргументов.\n"
            "chat_id — целое число, даты — YYYY-MM-DD."
        )
        return

    try:
        with SessionLocal() as session:
            messages = get_messages_by_period(session, chat_id, date_from, date_to)
            if not messages:
                await update.message.reply_text(
                    f"За период {args[1]} — {args[2]} сообщений в чате {chat_id} не найдено."
                )
                return
            # format_messages обращается к message.user — вызываем пока сессия открыта.
            # filename_only=True: в тексте будет только имя файла, сам файл будет в media/ архива.
            text = format_messages(messages, chat_id, date_from, date_to, filename_only=True)
            file_paths = [msg.file_path for msg in messages]
            msg_count = len(messages)
    except Exception:
        logger.exception("Ошибка при выгрузке сообщений chat_id=%s", chat_id)
        await update.message.reply_text("Не удалось сформировать выгрузку. Подробности в логах сервера.")
        return

    # Собираем ZIP в памяти
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.txt", text.encode("utf-8"))
        for fp in file_paths:
            if not fp:
                continue
            local_path = pathlib.Path(fp)
            if local_path.exists():
                zf.write(local_path, arcname=f"media/{local_path.name}")
            else:
                logger.warning("Медиафайл не найден на диске: %s", fp)

    zip_size = zip_buffer.tell()
    if zip_size > ZIP_SIZE_LIMIT:
        await update.message.reply_text(
            f"Архив слишком большой ({zip_size // 1024 // 1024} МБ > 50 МБ). "
            "Сократите период выгрузки и попробуйте снова."
        )
        return

    zip_buffer.seek(0)
    zip_name = f"export_{chat_id}_{args[1]}_{args[2]}.zip"

    try:
        await update.message.reply_document(
            document=zip_buffer,
            filename=zip_name,
            caption=f"Выгрузка: {msg_count} сообщ. | {args[1]} — {args[2]}",
        )
    except Exception:
        logger.exception("Ошибка при отправке архива выгрузки chat_id=%s", chat_id)
        await update.message.reply_text("Не удалось отправить архив. Подробности в логах сервера.")
        return

    logger.info(
        "Администратор %s запросил выгрузку chat_id=%s (%s — %s), %d сообщений",
        update.effective_user.id,
        chat_id,
        args[1],
        args[2],
        msg_count,
    )


def build_admin_app() -> Application:
    """Собрать и вернуть приложение бота-администратора."""
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start, filters=admin_filter))
    app.add_handler(CommandHandler("chats", cmd_chats, filters=admin_filter))
    app.add_handler(CommandHandler("export", cmd_export, filters=admin_filter))

    logger.info("Бот администратора инициализирован")
    return app
