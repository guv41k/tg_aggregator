from datetime import datetime

from db.models import Message


def format_messages(
    messages: list[Message],
    chat_id: int,
    date_from: datetime,
    date_to: datetime,
) -> str:
    """Форматировать список сообщений в текстовый файл для выгрузки."""
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

        body = msg.text or f"[{msg.media_type or 'медиа'}]"

        line = f"[{ts}] {sender}:\n{body}"

        if msg.reactions:
            line += f"\n  Реакции: {' '.join(msg.reactions)}"

        lines.append(line)

    return header + "\n\n".join(lines)
