import unittest
from datetime import datetime

from db.models import Message, User
from utils.formatters import format_messages


class FormatMessagesTests(unittest.TestCase):
    def test_text_sender_and_reactions_appear_in_export(self) -> None:
        message = Message(
            chat_id=10,
            id=7,
            user=User(id=42, first_name="Анна", username="anna"),
            text="Привет",
            reactions=[{"emoji": "👍", "count": 2}],
            timestamp=datetime(2026, 1, 1, 12, 30),
        )

        result = format_messages(
            [message], 10, datetime(2026, 1, 1), datetime(2026, 1, 2)
        )

        self.assertIn("Сообщений: 1", result)
        self.assertIn("Анна (@anna):\nПривет", result)
        self.assertIn("Реакции: 👍 (2)", result)

    def test_media_export_can_use_filename_only(self) -> None:
        message = Message(
            chat_id=10,
            id=8,
            media_type="photo",
            file_path="media/photo/image.jpg",
            timestamp=datetime(2026, 1, 1, 12, 30),
        )

        result = format_messages(
            [message], 10, datetime(2026, 1, 1), datetime(2026, 1, 2),
            filename_only=True,
        )

        self.assertIn("[photo: image.jpg]", result)
        self.assertNotIn("media/photo/", result)
