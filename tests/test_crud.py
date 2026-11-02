import unittest
from datetime import datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from db.crud import (
    get_messages_by_period,
    save_message,
    update_message_reactions,
    upsert_chat,
)
from db.models import Message
from db.session import Base


class MessageCrudTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)

    def test_same_message_id_can_be_saved_in_two_chats(self) -> None:
        with Session(self.engine) as session:
            upsert_chat(session, {"id": 10})
            upsert_chat(session, {"id": 20})

            save_message(session, {"chat_id": 10, "id": 7, "text": "Первое"})
            save_message(session, {"chat_id": 20, "id": 7, "text": "Второе"})

            self.assertEqual(session.get(Message, (10, 7)).text, "Первое")
            self.assertEqual(session.get(Message, (20, 7)).text, "Второе")
            self.assertEqual(session.scalar(select(func.count()).select_from(Message)), 2)

    def test_repeated_message_is_not_inserted_again(self) -> None:
        with Session(self.engine) as session:
            upsert_chat(session, {"id": 10})

            save_message(session, {"chat_id": 10, "id": 7, "text": "Первое"})
            save_message(session, {"chat_id": 10, "id": 7, "text": "Повтор"})

            self.assertEqual(session.get(Message, (10, 7)).text, "Первое")
            self.assertEqual(session.scalar(select(func.count()).select_from(Message)), 1)

    def test_reactions_change_only_the_requested_chat(self) -> None:
        with Session(self.engine) as session:
            upsert_chat(session, {"id": 10})
            upsert_chat(session, {"id": 20})
            save_message(session, {"chat_id": 10, "id": 7})
            save_message(session, {"chat_id": 20, "id": 7})

            update_message_reactions(session, 20, 7, [], ["👍"])
            update_message_reactions(session, 20, 7, ["👍"], ["🔥"])

            self.assertIsNone(session.get(Message, (10, 7)).reactions)
            self.assertEqual(
                session.get(Message, (20, 7)).reactions,
                [{"emoji": "🔥", "count": 1}],
            )

    def test_period_query_returns_only_messages_from_requested_chat(self) -> None:
        with Session(self.engine) as session:
            upsert_chat(session, {"id": 10})
            upsert_chat(session, {"id": 20})
            save_message(session, {
                "chat_id": 10, "id": 1, "timestamp": datetime(2026, 1, 1, 9),
            })
            save_message(session, {
                "chat_id": 10, "id": 2, "timestamp": datetime(2026, 1, 2, 9),
            })
            save_message(session, {
                "chat_id": 20, "id": 1, "timestamp": datetime(2026, 1, 1, 10),
            })

            messages = get_messages_by_period(
                session, 10, datetime(2026, 1, 1), datetime(2026, 1, 1, 23, 59, 59)
            )

            self.assertEqual([(message.chat_id, message.id) for message in messages], [(10, 1)])
