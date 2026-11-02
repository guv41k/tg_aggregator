import unittest
from types import SimpleNamespace
from unittest.mock import patch

from admin_bot.filters import AdminFilter


class AdminFilterTests(unittest.TestCase):
    def test_only_configured_admin_is_allowed(self) -> None:
        admin_filter = AdminFilter()

        with patch("admin_bot.filters.ADMIN_IDS", [42]):
            self.assertTrue(admin_filter.filter(SimpleNamespace(effective_user=SimpleNamespace(id=42))))
            self.assertFalse(admin_filter.filter(SimpleNamespace(effective_user=SimpleNamespace(id=7))))
            self.assertFalse(admin_filter.filter(SimpleNamespace(effective_user=None)))
