import pathlib
from datetime import datetime

from db.models import Message


def format_messages(
    messages: list[Message],
    chat_id: int,
    date_from: datetime,
    date_to: datetime,
    filename_only: bool = False,
) -> str:
    """Форматировать список сообщений в текст для выгрузки.

    filename_only=True — в теле сообщения выводить только имя файла без пути
    (используется при сборке ZIP, где файлы лежат рядом).
    """
    header = (
        f"Выгрузка переписки\n"
        f"Чат: {chat_id}\n"
        f"Период: {date_from.strftime('%Y-%m-%d')} — {date_to.strftime('%Y-%m-%d')}\n"
        f"Сообщений: {len(messages)}\n"
        f"{'=' * 60}\n\n"
    )

    lines = []
    for msg in messages:
        ts = msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")

        if msg.user and (msg.user.first_name or msg.user.username):
            name_parts = [msg.user.first_name, msg.user.last_name]
            full_name = " ".join(p for p in name_parts if p)
            sender = f"{full_name} (@{msg.user.username})" if msg.user.username else full_name
        else:
            sender = f"user_id:{msg.user_id}" if msg.user_id else "Неизвестно"

        if msg.text:
            body = msg.text
        elif msg.media_type:
            if msg.file_path:
                display = pathlib.Path(msg.file_path).name if filename_only else msg.file_path
                body = f"[{msg.media_type}: {display}]"
            else:
                body = f"[{msg.media_type} (файл недоступен)]"
        else:
            body = "[медиа]"

        line = f"[{ts}] {sender}:\n{body}"

        if msg.reactions:
            parts = [
                f"{r['emoji']} ({r['count']})"
                for r in msg.reactions
                if isinstance(r, dict) and r.get("count", 0) > 0
            ]
            if parts:
                line += f"\n  Реакции: {' '.join(parts)}"

        lines.append(line)

    return header + "\n\n".join(lines)
