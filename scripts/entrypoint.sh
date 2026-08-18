#!/bin/sh
# Точка входа контейнера. Ничего не роняет старт: бот умеет работать
# деградированно (без истории/skills), и лучше живой бот с предупреждением
# в логах, чем контейнер в restart-loop.
set -u

DB_URL="${DATABASE_URL:-sqlite+aiosqlite:///data/voicebot.db}"

case "$DB_URL" in
  sqlite*)
    # На чистом SQLite сначала создаём таблицы. Иначе sync_skills пытается
    # заполнить skills_index до первого init_db в основном приложении.
    echo "[entrypoint] SQLite mode: $DB_URL (инициализирую схему)"
    python - <<'PY' || echo "[entrypoint] WARN: SQLite-схема не инициализировалась, продолжаю"
import asyncio

from src.storage.db import init_db

asyncio.run(init_db())
PY
    ;;
  *)
    echo "[entrypoint] Postgres mode: применяю миграции"
    alembic upgrade head || echo "[entrypoint] WARN: миграции не применились, продолжаю"
    ;;
esac

# Skills нужны только режиму «Промпт»; сеть/GitHub могут быть недоступны.
# Для SQLite схема уже создана выше, поэтому первый sync не упадёт на
# отсутствующей таблице skills_index.
if [ "${SKIP_SKILLS_SYNC:-0}" != "1" ]; then
  python scripts/sync_skills.py || echo "[entrypoint] WARN: синк skills не удался, продолжаю"
fi

exec python -m src.main