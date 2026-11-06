import os
import unittest
from datetime import datetime
from uuid import uuid4

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError("Set TEST_DATABASE_URL to a PostgreSQL test database URL")

# db.session creates its engine at import time; point it at the test database too.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from db.crud import (  # noqa: E402
    get_messages_by_period,
    save_message,
    update_message_reactions,
    upsert_chat,
)
from db.models import Message  # noqa: E402
from db.session import Base  # noqa: E402


class PostgresCrudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(TEST_DATABASE_URL)
        if cls.engine.dialect.name != "postgresql":
            cls.engine.dispose()
            raise RuntimeError("TEST_DATABASE_URL must use PostgreSQL")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.connection = self.engine.connect()
        self.addCleanup(self.connection.close)
        transaction = self.connection.begin()
        self.addCleanup(transaction.rollback)

        # A fresh schema per test keeps the database untouched after rollback.
        schema = f"test_{uuid4().hex}"
        self.connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        self.connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
        Base.metadata.create_all(self.connection)

    def session(self) -> Session:
        # CRUD functions call commit(); savepoints keep the outer test transaction open.
        return Session(bind=self.connection, join_transaction_mode="create_savepoint")

    def test_messages_have_composite_primary_key(self) -> None:
        primary_key = inspect(self.connection).get_pk_constraint("messages")
        self.assertEqual(set(primary_key["constrained_columns"]), {"chat_id", "id"})

    def test_same_message_id_in_two_chats_and_duplicate_in_one_chat(self) -> None:
        with self.session() as session:
            upsert_chat(session, {"id": 10})
            upsert_chat(session, {"id": 20})
            save_message(session, {"chat_id": 10, "id": 7, "text": "Первое"})
            save_message(session, {"chat_id": 20, "id": 7, "text": "Второе"})
            save_message(session, {"chat_id": 10, "id": 7, "text": "Повтор"})

        with self.session() as session:
            self.assertEqual(session.get(Message, (10, 7)).text, "Первое")
            self.assertEqual(session.get(Message, (20, 7)).text, "Второе")
            self.assertEqual(session.scalar(select(func.count()).select_from(Message)), 2)

    def test_reactions_are_saved_for_the_requested_chat(self) -> None:
        with self.session() as session:
            upsert_chat(session, {"id": 10})
            upsert_chat(session, {"id": 20})
            save_message(session, {"chat_id": 10, "id": 7})
            save_message(session, {"chat_id": 20, "id": 7})
            update_message_reactions(session, 20, 7, [], ["👍"])
            update_message_reactions(session, 20, 7, ["👍"], ["🔥"])

        with self.session() as session:
            self.assertIsNone(session.get(Message, (10, 7)).reactions)
            self.assertEqual(
                session.get(Message, (20, 7)).reactions,
                [{"emoji": "🔥", "count": 1}],
            )

    def test_period_query_returns_only_the_requested_chat(self) -> None:
        with self.session() as session:
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

        with self.session() as session:
            messages = get_messages_by_period(
                session, 10, datetime(2026, 1, 1), datetime(2026, 1, 1, 23, 59, 59)
            )
            self.assertEqual([(message.chat_id, message.id) for message in messages], [(10, 1)])
