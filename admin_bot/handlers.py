import logging
import pathlib
import zipfile
from datetime import datetime
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ConversationHandler, ContextTypes, MessageHandler, filters,
)

from admin_bot.filters import AdminFilter
from config import ADMIN_IDS, BOT_TOKEN
from db.crud import get_all_chats, get_messages_by_period
from db.session import SessionLocal
from utils.formatters import format_messages

logger = logging.getLogger(__name__)

admin_filter = AdminFilter()

ZIP_SIZE_LIMIT = 50 * 1024 * 1024  # 50 МБ — лимит Telegram Bot API

# Callback data
CB_CHATS = "chats"
CB_EXPORT = "export"
CB_CANCEL = "cancel"
CB_BACK = "back"
CB_CHAT_PREFIX = "chat:"

MAIN_MENU_TEXT = "Привет, администратор! Выберите действие:"

# Состояния диалога выгрузки
SELECT_CHAT, ENTER_DATE_FROM, ENTER_DATE_TO = range(3)


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Список чатов", callback_data=CB_CHATS),
        InlineKeyboardButton("📤 Выгрузка", callback_data=CB_EXPORT),
    ]])


def _chats_menu() -> InlineKeyboardMarkup:
    """Меню под списком чатов — с кнопкой выхода."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Список чатов", callback_data=CB_CHATS),
            InlineKeyboardButton("📤 Выгрузка", callback_data=CB_EXPORT),
        ],
        [InlineKeyboardButton("← Назад", callback_data=CB_BACK)],
    ])


def _cancel_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data=CB_CANCEL)]])


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id in ADMIN_IDS


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=_main_menu())


# ── Список чатов (кнопка «📋 Список чатов») ──────────────────────────────────

async def cb_show_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not _is_admin(update):
        await query.answer("Нет доступа.", show_alert=True)
        return

    with SessionLocal() as session:
        try:
            chats = get_all_chats(session)
        except Exception:
            logger.exception("Ошибка при получении списка чатов")
            await query.edit_message_text("Ошибка при обращении к базе данных.", reply_markup=_main_menu())
            return

    if not chats:
        await query.edit_message_text("Пока ни одного чата не отслеживается.", reply_markup=_chats_menu())
        return

    lines = ["<b>Отслеживаемые чаты:</b>"]
    for chat in chats:
        lines.append(f"• <b>{chat.title or '—'}</b> | id: <code>{chat.id}</code> | тип: {chat.type}")

    await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=_chats_menu())


# ── Диалог выгрузки ───────────────────────────────────────────────────────────

async def cb_start_export(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 1 — показываем список чатов кнопками."""
    query = update.callback_query
    await query.answer()

    if not _is_admin(update):
        await query.answer("Нет доступа.", show_alert=True)
        return ConversationHandler.END

    with SessionLocal() as session:
        try:
            chats = get_all_chats(session)
        except Exception:
            logger.exception("Ошибка при получении списка чатов")
            await query.edit_message_text("Ошибка при обращении к базе данных.", reply_markup=_main_menu())
            return ConversationHandler.END

    if not chats:
        await query.edit_message_text("Нет чатов для выгрузки.", reply_markup=_main_menu())
        return ConversationHandler.END

    buttons = [
        [InlineKeyboardButton(chat.title or str(chat.id), callback_data=f"{CB_CHAT_PREFIX}{chat.id}")]
        for chat in chats
    ]
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data=CB_CANCEL)])

    await query.edit_message_text("Выберите чат:", reply_markup=InlineKeyboardMarkup(buttons))
    return SELECT_CHAT


async def cb_select_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 2 — сохраняем chat_id, просим дату начала."""
    query = update.callback_query
    await query.answer()

    chat_id = int(query.data.removeprefix(CB_CHAT_PREFIX))
    context.user_data["export_chat_id"] = chat_id

    await query.edit_message_text(
        f"Чат: <code>{chat_id}</code>\n\nВведите дату начала периода <b>(YYYY-MM-DD)</b>:",
        parse_mode="HTML",
        reply_markup=_cancel_button(),
    )
    return ENTER_DATE_FROM


async def msg_date_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 3 — валидируем дату начала, просим дату конца."""
    text = update.message.text.strip()
    try:
        date_from = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "Неверный формат. Введите дату как <b>YYYY-MM-DD</b>:",
            parse_mode="HTML",
            reply_markup=_cancel_button(),
        )
        return ENTER_DATE_FROM

    context.user_data["export_date_from"] = date_from
    await update.message.reply_text(
        f"Начало: <b>{text}</b>\n\nВведите дату окончания <b>(YYYY-MM-DD)</b>:",
        parse_mode="HTML",
        reply_markup=_cancel_button(),
    )
    return ENTER_DATE_TO


async def msg_date_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Шаг 4 — валидируем дату конца, формируем и отправляем ZIP."""
    text = update.message.text.strip()
    try:
        date_to = datetime.strptime(text, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        await update.message.reply_text(
            "Неверный формат. Введите дату как <b>YYYY-MM-DD</b>:",
            parse_mode="HTML",
            reply_markup=_cancel_button(),
        )
        return ENTER_DATE_TO

    chat_id: int = context.user_data["export_chat_id"]
    date_from: datetime = context.user_data["export_date_from"]
    date_from_str = date_from.strftime("%Y-%m-%d")

    await update.message.reply_text("⏳ Формирую архив...")

    try:
        with SessionLocal() as session:
            messages = get_messages_by_period(session, chat_id, date_from, date_to)
            if not messages:
                await update.message.reply_text(
                    f"За период {date_from_str} — {text} сообщений не найдено.",
                    reply_markup=_main_menu(),
                )
                return ConversationHandler.END
            export_text = format_messages(messages, chat_id, date_from, date_to, filename_only=True)
            file_paths = [msg.file_path for msg in messages]
            msg_count = len(messages)
    except Exception:
        logger.exception("Ошибка при выгрузке сообщений chat_id=%s", chat_id)
        await update.message.reply_text(
            "Не удалось сформировать выгрузку. Подробности в логах сервера.",
            reply_markup=_main_menu(),
        )
        return ConversationHandler.END

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.txt", export_text.encode("utf-8"))
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
            "Сократите период и попробуйте снова.",
            reply_markup=_main_menu(),
        )
        return ConversationHandler.END

    zip_buffer.seek(0)
    try:
        await update.message.reply_document(
            document=zip_buffer,
            filename=f"export_{chat_id}_{date_from_str}_{text}.zip",
            caption=f"Выгрузка: {msg_count} сообщ. | {date_from_str} — {text}",
        )
    except Exception:
        logger.exception("Ошибка при отправке архива chat_id=%s", chat_id)
        await update.message.reply_text("Не удалось отправить архив. Подробности в логах сервера.")
        return ConversationHandler.END

    logger.info(
        "Администратор %s выгрузил chat_id=%s (%s — %s), %d сообщений",
        update.effective_user.id, chat_id, date_from_str, text, msg_count,
    )

    await update.message.reply_text("Готово! Выберите следующее действие:", reply_markup=_main_menu())
    return ConversationHandler.END


async def cb_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка «← Назад» — возвращает на главный экран."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(MAIN_MENU_TEXT, reply_markup=_main_menu())


async def cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Кнопка «❌ Отмена» внутри диалога — завершает и возвращает на главный экран."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(MAIN_MENU_TEXT, reply_markup=_main_menu())
    return ConversationHandler.END


# ── Сборка приложения ─────────────────────────────────────────────────────────

def build_admin_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start, filters=admin_filter))
    app.add_handler(CallbackQueryHandler(cb_show_chats, pattern=f"^{CB_CHATS}$"))
    app.add_handler(CallbackQueryHandler(cb_back, pattern=f"^{CB_BACK}$"))

    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(cb_start_export, pattern=f"^{CB_EXPORT}$")],
        states={
            SELECT_CHAT: [CallbackQueryHandler(cb_select_chat, pattern=f"^{CB_CHAT_PREFIX}")],
            ENTER_DATE_FROM: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_date_from)],
            ENTER_DATE_TO: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_date_to)],
        },
        fallbacks=[
            CallbackQueryHandler(cb_cancel, pattern=f"^{CB_CANCEL}$"),
            CommandHandler("start", cmd_start, filters=admin_filter),
        ],
    ))

    logger.info("Бот администратора инициализирован")
    return app
