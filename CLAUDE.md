# Voice Polisher Bot — CLAUDE.md

## Что это

Telegram-бот для обработки голосовых сообщений и текста через Groq AI.
5 режимов: Polish, Prompt Engineer, Humanizer, Translator, Summary.
Принимает голос/аудио/видео-кружки/видео — напрямую, **пересланные** или **реплаем**
на чужое/своё сообщение. Голосовые до 1 часа (длинные режутся на чанки).
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
- **Источник медиа** — `handle_voice` берёт медиа из самого сообщения (прямое/форвард), а если их нет — из `reply_to_message` (реплай на голос/кружок/видео). Фильтр роутера: `_HAS_MEDIA | _REPLY_HAS_MEDIA`. Видео/кружки → ffmpeg вытаскивает аудио-дорожку.
- **Доставка ответа** — прогресс-сообщение («✨ Полирую…») затем редактируется в финальный результат через `send_result` из `src/handlers/_reply.py`. Результат оборачивается в `<blockquote><code>…</code></blockquote>` (экранируется `escape_html`) — цитата + тап-чтобы-скопировать, `parse_mode="HTML"`. Стриминг-превью (`sendMessageDraft`) убран: эфемерный драфт надо финализировать через `SendMessage`, а мы редактируем другое сообщение — оставались «осиротевшие» пустые пузыри. `on_delta` в сервисах сохранён (default `None`).
- **Парс-моды** — у бота default `parse_mode=None`. Сырой вывод LLM содержит `<`, `&` — поэтому перед вставкой в HTML он **экранируется** (`escape_html`) и кладётся в `<code>`. Готовые текстовые константы с HTML-тегами отправляются с явным `parse_mode="HTML"`.
- **Whisper** — `whisper-large-v3` (НЕ turbo). Выбран осознанно: **качество распознавания важнее скорости** (turbo хуже на сложной речи/акцентах/матах). Не менять на turbo без явной просьбы владельца.
- **Кнопка «Повтор»** (`action:regenerate`) — реально прогоняет цикл заново на последнем запросе: для голоса `force_retranscribe=True` (сброс кэша → свежая транскрипция Whisper), затем свежая генерация LLM. Последний запрос хранится в памяти процесса (`src/handlers/_last.py`, `LastRequest` по `telegram_user_id`); общая логика голоса/текста вынесена в `_process_media`/`_process_text`, их же зовут `regenerate_voice`/`regenerate_text`. После рестарта стор пуст — «Повтор» просит прислать заново.
- **Снаппи-кнопки** — callback-хендлеры зовут `callback.answer()` сразу (до DB/edit), чтобы спиннер на кнопке гас мгновенно.
- **Groq API** — retry до 3 попыток с паузой 2с/4с; при 429 (rate-limit) и в LLM (`complete`), и в STT (`transcribe`) идёт ротация по всем ключам из `get_all_groq_keys()`.
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
- `/users` — список пользователей (кто, username, кол-во запросов, последняя активность, статус)
- `/user <id>` — карточка пользователя + inline-кнопки бан/разбан
- `/ban <id>` / `/unban <id>` — блокировка/разблокировка по telegram_id
- `/sync_skills` — перезалить skills из GitHub репозиториев
- `/history` — последние 10 запросов

Бан хранится в колонке `users.is_blocked`; `AuthMiddleware` проверяет её (своя короткая сессия), админов забанить нельзя.

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
- [x] Фикс парсинга f/awesome-chatgpt-prompts (csv.field_size_limit)
- [x] Админ-дашборд в Telegram: /users, /user, /ban, /unban + бан через AuthMiddleware
- [x] Режим Summary (саммари) + стиль Polish «Сырой»
- [x] Голосовые до 1 часа (чанкинг через ffmpeg), видео-кружки/видео
- [x] Транскрипция пересланных и реплай-голосовых (не только прямых записей)
- [x] Копируемый результат: цитата + тап-чтобы-скопировать (`<blockquote><code>`)
- [x] Фикс конфликта webhook/polling (delete_webhook перед polling), опциональный webhook-режим, TTL-очистка БД
- [x] Ротация Groq-ключей в LLM при 429 (как в STT)
- [x] Рабочая кнопка «Повтор»: полный свежий прогон с force_retranscribe (сброс кэша)
- [ ] Redis для rate-limit при масштабировании >1 реплики
