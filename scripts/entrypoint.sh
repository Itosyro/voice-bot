#!/bin/sh
# Точка входа контейнера. Ничего не роняет старт: бот умеет работать
# деградированно (без истории/skills), и лучше живой бот с предупреждением
# в логах, чем контейнер в restart-loop.
set -u

DB_URL="${DATABASE_URL:-sqlite+aiosqlite:///data/voicebot.db}"

case "$DB_URL" in
  sqlite*)
    # Схему для SQLite создаёт сам бот (init_db) — alembic-миграции под Postgres.
    echo "[entrypoint] SQLite mode: $DB_URL (схема создаётся автоматически)"
    ;;
  *)
    echo "[entrypoint] Postgres mode: применяю миграции"
    alembic upgrade head || echo "[entrypoint] WARN: миграции не применились, продолжаю"
    ;;
esac

# Skills нужны только режиму «Промпт»; сеть/GitHub могут быть недоступны.
if [ "${SKIP_SKILLS_SYNC:-0}" != "1" ]; then
  python scripts/sync_skills.py || echo "[entrypoint] WARN: синк skills не удался, продолжаю"
fi

exec python -m src.main
