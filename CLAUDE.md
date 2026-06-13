# Voice Polisher Bot — CLAUDE.md

## Что это

Telegram-бот для обработки голосовых сообщений и текста через Groq AI.
4 режима: Polish, Prompt Engineer, Humanizer, Translator.
Закрыт через `ALLOWED_USER_IDS` — личный сервис для ~10–50 пользователей.

## Архитектура

```
src/
  main.py          — точка входа, health-сервер (/health), polling
  bot.py           — создание Bot + Dispatcher, регистрация роутеров/middleware
  config.py        — Pydantic Settings (читает .env)
  handlers/        — Telegram-хендлеры (voice, text, admin, callbacks, …)
  services/        — бизнес-логика (llm, transcribe, polish, prompt_eng, …)
  storage/         — SQLAlchemy модели, db.py (движок), users/history
  prompts/         — системные промпты для каждого режима
  ui/              — keyboards.py, messages.py
  middlewares/     — auth (ALLOWED_USER_IDS), rate_limit, db_session
```

**Стек:** aiogram 3, SQLAlchemy 2 async, asyncpg, Groq SDK (LLM + Whisper STT), aiohttp (health), BM25 (skills search), Alembic (миграции).

## Ключевые решения

- **Транскрипция кэшируется** по `file_id` в таблице `transcription_cache`. Кнопка "🎙️ Перетранскрибировать" сбрасывает кэш для последнего файла и просит отправить снова.
- **Длинные ответы** (>3900 символов) разбиваются на несколько сообщений по границам абзацев — не обрезаются. Если получилось бы больше 10 сообщений, ответ целиком отправляется файлом `.txt`.
- **Стриминг превью** — во всех 4 режимах во время генерации в чат идёт `sendMessageDraft` (эфемерный предпросмотр) через `make_draft_callback`/`send_result` из `src/handlers/_reply.py`.
- **Groq API** — retry до 3 попыток с паузой 2с/4с при любой ошибке (обрывы, 500, временные сбои, пустой ответ reasoning-модели).
- **gpt-oss-120b (coder_strict)** — reasoning-модель, требует `reasoning_effort`/`reasoning_format="hidden"` и `max_completion_tokens`, иначе возвращает пустой content.
- **rate_limit** — in-memory скользящее окно, idle-юзеры удаляются из dict.
- **БД** — pool_size=5, statement_cache_size=0 (совместимость с Supabase/Neon PgBouncer).

## Деплой

- **Хостинг бота:** Render (free tier). Бот работает через long-polling.
- **Keep-alive:** внешний пингер (cron-job.org / UptimeRobot) дёргает `/health` каждые 10 мин — Render не усыпляет.
- **БД:** Supabase (free, постоянная). CONNECTION STRING формата `postgresql+asyncpg://postgres.xxxx:PWD@pooler.supabase.com:5432/postgres` (Session pooler, порт 5432).
- **При старте автоматически:** `alembic upgrade head` + `python scripts/sync_skills.py`.

## Переменные окружения (обязательные)

```
TELEGRAM_BOT_TOKEN=
GROQ_API_KEY_FALLBACK=   # или отдельные ключи на каждый режим
DATABASE_URL=            # postgresql+asyncpg://...
ADMIN_USER_IDS=          # твой telegram user_id, через запятую
ALLOWED_USER_IDS=        # пусто = открыт всем, список = только они
```

## Команды разработки

```bash
docker compose up --build          # локально с postgres
alembic upgrade head               # применить миграции
python scripts/sync_skills.py      # залить skills в БД
python -m src.main                 # запустить бота
```

## Команды бота (для тебя как админа)

- `/stats` — статистика: юзеры, запросы, активные за 7 дней, режимы
- `/sync_skills` — перезалить skills из GitHub репозиториев
- `/history` — последние 10 запросов

## Текущий статус / roadmap

- [x] Промпт-инъекция закрыта (PR #6)
- [x] Supabase-ready DB pool (PR #7)
- [x] Non-root Docker, атомарный upsert пользователя, защита от огромных файлов (PR #7)
- [x] Retry для Groq API
- [x] Разбивка длинных ответов на части вместо обрезки
- [x] Кнопка "Перетранскрибировать" для пересчёта кэша
- [x] Активные юзеры за 7 дней в /stats
- [x] Стриминг превью (sendMessageDraft) во всех режимах, файл .txt для очень длинных ответов
- [x] Фикс Prompt Engineer / coder_strict (gpt-oss-120b reasoning params) и усиленный retry Groq
- [x] Дизайнерские скиллы Taste-Skill (Leonxlnx/taste-skill) и Impeccable (pbakaus/impeccable)
- [ ] Webhook вместо polling (нужен публичный HTTPS URL — Render даёт его бесплатно)
- [ ] Redis для rate-limit при масштабировании >1 реплики
