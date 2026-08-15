"""Переезд на новый сервер: архив (.env + база) и однострочник в Telegram."""

import io
import sqlite3
import tarfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine, insert

from src.config import settings
from src.migrate import build_archive, send_migration
from src.storage.models import Base, SkillIndex, User

ENV_BODY = b"TELEGRAM_BOT_TOKEN=123:ABC\nGROQ_API_KEY_FALLBACK=gsk_test\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Рабочая папка «как в контейнере»: .env рядом, база с юзером и skills."""
    db_file = tmp_path / "voicebot.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(User).values(telegram_user_id=777, username="owner"))
        conn.execute(
            insert(SkillIndex).values(
                source_repo="repo",
                skill_name="s",
                description="d",
                body="b" * 5000,
                file_path="f",
            )
        )
    engine.dispose()

    (tmp_path / ".env").write_bytes(ENV_BODY)
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_file}")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _extract(data: bytes) -> tarfile.TarFile:
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


def test_build_archive_contains_env_and_db(project):
    data, name = build_archive()

    assert name.startswith("voicebot-migration-") and name.endswith(".tar.gz")
    with _extract(data) as tar:
        assert sorted(tar.getnames()) == [".env", "voicebot.db"]
        assert tar.extractfile(".env").read() == ENV_BODY  # байт-в-байт
        tar.extract("voicebot.db", project / "out")

    conn = sqlite3.connect(project / "out" / "voicebot.db")
    try:
        assert conn.execute("SELECT username FROM users").fetchone() == ("owner",)
        # skills_index пересобирается на старте контейнера — в архиве её быть не должно.
        assert conn.execute("SELECT count(*) FROM skills_index").fetchone() == (0,)
    finally:
        conn.close()


def test_build_archive_without_env_explains_the_mount(project):
    (project / ".env").unlink()
    with pytest.raises(FileNotFoundError, match=r"/app/\.env"):
        build_archive()


def test_build_archive_refuses_postgres(project, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://u:p@host/db")
    with pytest.raises(RuntimeError, match="SQLite"):
        build_archive()


async def test_send_migration_sends_file_and_command(project, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "123:SECRET")
    bot = MagicMock()
    bot.send_document = AsyncMock(return_value=MagicMock(document=MagicMock(file_id="FID42")))
    bot.send_message = AsyncMock()

    await send_migration(bot, 777)

    bot.send_document.assert_awaited_once()
    bot.send_message.assert_awaited_once()
    text = bot.send_message.await_args.args[1]
    assert "<code>curl -fsSL" in text
    # Токен уезжает переменной окружения, а не в argv (иначе виден в ps).
    assert "TG_TOKEN=123:SECRET bash -s -- --tg FID42</code>" in text
    assert bot.send_message.await_args.kwargs["parse_mode"] == "HTML"


async def test_send_migration_warns_when_archive_too_big(project, monkeypatch):
    """Бот шлёт до 50 МБ, а новый сервер качает через getFile только 20 — предупреждаем."""
    import src.migrate as migrate_mod

    monkeypatch.setattr(migrate_mod, "_TG_DOWNLOAD_LIMIT", 0)
    bot = MagicMock()
    bot.send_document = AsyncMock(return_value=MagicMock(document=MagicMock(file_id="FID42")))
    bot.send_message = AsyncMock()

    await send_migration(bot, 777)

    text = bot.send_message.await_args.args[1]
    assert "больше 20 МБ" in text
    assert "--restore" in text


async def test_migrate_command_guards():
    """Архив с секретами: только админ и только в личке."""
    from src.handlers.admin import cmd_migrate

    stranger = MagicMock(answer=AsyncMock())
    stranger.from_user.id = 999
    monkey_admin = settings.admin_user_ids_list  # пусто в тестах → любой не админ
    assert monkey_admin == []
    await cmd_migrate(stranger)
    assert "администратор" in stranger.answer.await_args.args[0]

    group = MagicMock(answer=AsyncMock())
    group.from_user.id = 111
    group.chat.type = "group"
    settings.admin_user_ids = "111"
    try:
        await cmd_migrate(group)
    finally:
        settings.admin_user_ids = ""
    assert group.answer.await_args.args[0] == "Только в личке с ботом."
