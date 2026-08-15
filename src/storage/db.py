from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

log = structlog.get_logger()

IS_SQLITE = settings.database_url.startswith("sqlite")


def _engine_kwargs() -> dict:
    """Параметры движка под конкретную БД.

    SQLite (self-hosted: файл рядом с ботом, никаких внешних сервисов) не имеет
    ни пула соединений в привычном смысле, ни asyncpg-параметров — передавать
    их туда нельзя.
    """
    if IS_SQLITE:
        return {"connect_args": {"timeout": 30}}
    return {
        # Пул под managed Postgres free tier (Supabase/Neon) с лимитом коннектов.
        "pool_size": 5,
        "max_overflow": 5,
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "connect_args": {
            # statement_cache_size=0 — совместимость с PgBouncer-пулерами.
            "statement_cache_size": 0,
            # timeout/command_timeout: приостановленный Supabase (TCP открыт,
            # ответа нет) без них подвешивал хендлеры навечно.
            "timeout": 10,
            "command_timeout": 30,
        },
    }


engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    **_engine_kwargs(),
)


if IS_SQLITE:

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        """WAL + разумный таймаут: без них параллельные запросы к файлу
        упираются в «database is locked»."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionMaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _create_missing_indexes(conn) -> None:
    """Досоздать индексы, которых нет в существующей базе (checkfirst=True)."""
    from src.storage.models import Base

    for table in Base.metadata.tables.values():
        for index in table.indexes:
            index.create(bind=conn, checkfirst=True)


async def init_db() -> None:
    """Создать схему, если её ещё нет.

    Для SQLite это единственный способ поднять таблицы (alembic-миграции
    написаны под Postgres). Для Postgres схемой занимается alembic — здесь
    только проверяем связь, чтобы старт падал с понятной ошибкой, а не в
    первом же хендлере.
    """
    from src.storage.models import Base

    if IS_SQLITE:
        # Папку под файл базы создаём сами: при первом запуске её нет, и
        # SQLite падает с «unable to open database file».
        path = settings.database_url.split("///", 1)[-1]
        parent = Path(path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # create_all НЕ добавляет индексы в уже существующие таблицы — а база
            # теперь переезжает с сервера на сервер целиком, так что «создастся
            # при первом запуске» тут не работает. Досоздаём явно (idempotent).
            await conn.run_sync(_create_missing_indexes)
        log.info("sqlite_schema_ready", url=settings.database_url)
        return

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    log.info("postgres_reachable")
