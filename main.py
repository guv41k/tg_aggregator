import asyncio
import logging

from admin_bot import build_admin_app
from collector import build_collector_app
from db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Инициализация базы данных")
    init_db()

    collector_app = build_collector_app()
    admin_app = build_admin_app()

    async with collector_app, admin_app:
        await collector_app.start()
        await admin_app.start()

        await collector_app.updater.start_polling(drop_pending_updates=True)
        await admin_app.updater.start_polling(drop_pending_updates=True)

        logger.info("Оба бота запущены. Нажми Ctrl+C для остановки.")
        await asyncio.Event().wait()

        await collector_app.updater.stop()
        await admin_app.updater.stop()

        await collector_app.stop()
        await admin_app.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
