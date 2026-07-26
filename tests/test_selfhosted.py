"""Self-hosted режим: бот должен работать на файловой базе без внешних сервисов."""

from src.config import Settings


def test_sqlite_is_default_database(monkeypatch):
    """DATABASE_URL не обязателен: без него — локальный файл SQLite."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.database_url.startswith("sqlite+aiosqlite")


def test_models_are_portable_to_sqlite():
    """BigInteger-PK в SQLite не автоинкрементится, ARRAY там вообще нет —
    оба типа обязаны иметь sqlite-вариант, иначе вставки падают."""
    from sqlalchemy.dialects import postgresql, sqlite

    from src.storage.models import SkillIndex, User

    user_pk = User.__table__.c.id.type
    assert user_pk.compile(dialect=sqlite.dialect()) == "INTEGER"
    assert user_pk.compile(dialect=postgresql.dialect()) == "BIGINT"

    tags = SkillIndex.__table__.c.tags.type
    assert "JSON" in tags.compile(dialect=sqlite.dialect()).upper()
    assert "TEXT[]" in tags.compile(dialect=postgresql.dialect()).upper()


def test_engine_kwargs_differ_per_dialect(monkeypatch):
    """asyncpg-параметры (statement_cache_size и т.п.) нельзя слать в SQLite."""
    import src.storage.db as db_mod

    monkeypatch.setattr(db_mod, "IS_SQLITE", True)
    sqlite_kwargs = db_mod._engine_kwargs()
    assert "pool_size" not in sqlite_kwargs
    assert "statement_cache_size" not in sqlite_kwargs["connect_args"]

    monkeypatch.setattr(db_mod, "IS_SQLITE", False)
    pg_kwargs = db_mod._engine_kwargs()
    assert pg_kwargs["pool_size"] == 5
    assert pg_kwargs["connect_args"]["statement_cache_size"] == 0
