from telegram import Update
from telegram.ext import filters

from config import ADMIN_IDS


class AdminFilter(filters.UpdateFilter):
    """Пропускает обновления только от пользователей из списка ADMIN_IDS."""

    name = "admin_filter"

    def filter(self, update: Update) -> bool:
        user = update.effective_user
        if user is None:
            return False
        return user.id in ADMIN_IDS
