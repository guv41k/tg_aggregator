import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

logger = logging.getLogger(__name__)

Base = declarative_base()

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    try:
        from db import models  # noqa: F401 — регистрирует модели в Base.metadata
        Base.metadata.create_all(bind=engine)
        logger.info("Таблицы БД успешно созданы / уже существуют")
    except Exception:
        logger.exception("Ошибка при инициализации БД")
        raise
