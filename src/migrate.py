"""Переезд на новый сервер: архив (.env + база) приходит владельцу в Telegram.

Владелец снимает VPS на неделю и каждую неделю переезжает. `/migrate` в личке
с ботом (или `make migrate` на хосте) присылает tar.gz с секретами и базой плюс
готовую однострочную команду для нового сервера.
"""

import asyncio
import html
import io
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile

from src.config import settings

INSTALL_URL = "https://raw.githubusercontent.com/Itosyro/voice-bot/main/scripts/install-server.sh"

# getFile у Bot API отдаёт файлы только до 20 МБ — выше однострочник не сработает.
_TG_DOWNLOAD_LIMIT = 19_000_000


def _db_path() -> Path:
    """Путь к файлу SQLite из database_url (3 и 4 слэша — относительный/абсолютный)."""
    url = settings.database_url
    if not url.startswith("sqlite"):
        raise RuntimeError(
            f"Миграция умеет только SQLite (self-hosted), а DATABASE_URL={url!r}. "
            "Для Postgres переезда не нужно: база живёт вне сервера."
        )
    return Path(url.split("///", 1)[-1])


def snapshot_db(dst: str | Path) -> Path:
    """Консистентная копия базы в `dst` (её же зовёт `make backup`).

    backup() вместо копирования файла: бот пишет прямо сейчас, а в WAL-режиме
    сырая копия .db без -wal — это база «из прошлого» или вовсе битая.
    """
    db_path = _db_path()
    if not db_path.is_file():
        raise FileNotFoundError(f"База не найдена: {db_path}")
    src_conn = sqlite3.connect(str(db_path))
    dst_conn = sqlite3.connect(str(dst))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()
    return Path(dst)


def build_archive() -> tuple[bytes, str]:
    """Собрать tar.gz с `.env` и консистентным снимком базы. Синхронно (to_thread)."""
    env_path = Path(".env")
    if not env_path.is_file():
        raise FileNotFoundError(
            ".env не найден в рабочей папке. Внутри контейнера он должен быть "
            "примонтирован: в docker-compose.server.yml нужна строка "
            "'- ./.env:/app/.env:ro'. Обнови репозиторий (make update) и повтори."
        )

    with tempfile.TemporaryDirectory() as tmp:
        snapshot = snapshot_db(Path(tmp) / "voicebot.db")

        # skills_index полностью пересобирается на каждом старте контейнера
        # (scripts/sync_skills.py), так что везти её незачем — а это почти весь вес
        # базы, и без неё архив влезает в лимит Telegram.
        conn = sqlite3.connect(str(snapshot))
        try:
            try:
                conn.execute("DELETE FROM skills_index")
                conn.commit()
            except sqlite3.OperationalError:
                # Очень старая база без этой таблицы — не повод срывать переезд.
                conn.rollback()
            conn.execute("VACUUM")
        finally:
            conn.close()

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(env_path, arcname=".env")
            tar.add(snapshot, arcname="voicebot.db")

    name = f"voicebot-migration-{datetime.now().strftime('%Y%m%d-%H%M')}.tar.gz"
    return buf.getvalue(), name


async def send_migration(bot: Bot, chat_id: int) -> None:
    """Отправить архив и однострочник для нового сервера в указанный чат."""
    data, name = await asyncio.to_thread(build_archive)

    size = (
        f"{len(data) / 1_048_576:.1f} МБ" if len(data) >= 1_048_576 else f"{len(data) // 1024} КБ"
    )
    sent = await bot.send_document(
        chat_id,
        BufferedInputFile(data, filename=name),
        caption=f"📦 Архив переезда: .env + база ({size}).",
    )
    file_id = sent.document.file_id  # type: ignore[union-attr]

    # Токен идёт переменной окружения, а не аргументом: argv виден в `ps` любому
    # локальному пользователю, environment — только владельцу процесса.
    command = (
        f"curl -fsSL {INSTALL_URL} | "
        f"TG_TOKEN={settings.telegram_bot_token} bash -s -- --tg {file_id}"
    )
    # Отправить бот может до 50 МБ, а скачать по getFile новый сервер — только 20.
    too_big = (
        ""
        if len(data) <= _TG_DOWNLOAD_LIMIT
        else "‼️ Архив больше 20 МБ: Telegram не отдаст его по Bot API, эта команда "
        "упрётся в ошибку. Переезжай ручным способом (внизу).\n\n"
    )
    await bot.send_message(
        chat_id,
        "🚚 <b>Новый сервер</b> (чистая Ubuntu/Debian, под root) — вставь одну команду:\n\n"
        f"<code>{html.escape(command)}</code>\n\n" + too_big + "Она поставит Docker/git/make, "
        "склонирует репозиторий, вернёт .env и базу, соберёт образ и запустит бота.\n\n"
        "🔐 В файле и в команде — твой токен и ключи. Никому не пересылай.\n\n"
        "Вручную (и всегда, если архив больше 20 МБ): скачай файл, закинь на сервер "
        f"(<code>scp {html.escape(name)} root@СЕРВЕР:~/</code>), затем на сервере\n"
        f"<code>curl -fsSL {INSTALL_URL} | bash -s -- --restore ~/{html.escape(name)}</code>\n"
        "(или из папки проекта: <code>bash scripts/install-server.sh --restore ФАЙЛ</code>)",
        parse_mode="HTML",
    )


if __name__ == "__main__":
    # Хостовый фолбэк (`make migrate`), когда чат с ботом недоступен.
    async def _main() -> None:
        admins = settings.admin_user_ids_list
        if not admins:
            raise SystemExit("ADMIN_USER_IDS пуст — некому слать архив. Добавь свой id в .env.")
        bot = Bot(token=settings.telegram_bot_token)
        try:
            await send_migration(bot, admins[0])
        finally:
            await bot.session.close()

    asyncio.run(_main())
