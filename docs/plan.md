# Voice Polisher Bot — Plan

## Описание проекта

Telegram-бот для расшифровки голосовых сообщений и обработки текста через 5 режимов:

| # | Режим | Что делает | Вход | Подстили |
|---|-------|-----------|------|----------|
| 1 | **Polish** | Транскрипция + полировка текста | голос / текст | raw, default, creative, formal, embellish |
| 2 | **Prompt Engineer** | Мысль -> профессиональный промпт | голос / текст | general, designer, coder, coder_strict |
| 3 | **Humanizer** | Удаление AI-маркеров | только текст | lite, strong |
| 4 | **Translator** | Перевод с сохранением тона | голос / текст | выбор языка (14) |
| 5 | **Summary** | Конденсация текста в ключевые точки | голос / текст | — |

## Стек

- **Python 3.11** + **aiogram 3** (async Telegram framework)
- **Groq SDK** — Whisper STT + LLM (4 отдельных API-ключа по режимам)
- **PostgreSQL** + asyncpg + SQLAlchemy 2.0 async + Alembic
- **rank-bm25** — BM25 поиск по skills (RAG-lite)
- **Docker Compose** — бот + Postgres
- **Render** — текущий хостинг
- **structlog** — структурированные логи
- **pydantic-settings** — конфигурация через .env

## Архитектура

```
User -> Telegram -> aiogram handlers -> Mode Router -> [POLISH|PROMPT|HUMANIZER|TRANSLATOR]
                                            |                    |
                                       PostgreSQL          Skills RAG (BM25)
                                    (users, history)      (8 repos, ~200 skills)
                                            |                    |
                                       Groq API (4 ключа, по одному на режим)
                                       - Whisper STT (если вход — голос)
                                       - LLM (llama-3.3-70b / gpt-oss-120b)
```

## Структура кода

```
src/
  bot.py              — сборка бота (dispatcher, middlewares, routers)
  main.py             — точка входа
  config.py           — pydantic-settings конфиг
  utils.py            — общие утилиты (escape_html, send_result)
  logging_config.py   — structlog настройка

  handlers/
    start.py           — /start, /help
    modes.py           — /modes
    voice.py           — голосовые сообщения (прямые, пересланные, reply-to)
    text.py            — текстовые сообщения (прямые, пересланные, caption)
    callbacks.py       — inline-кнопки (режимы, стили, действия)
    settings.py        — /settings, /lang, /history
    admin.py           — /sync_skills, /stats

  services/
    transcribe.py      — Groq Whisper STT
    llm.py             — обёртка Groq LLM (complete + is_rate_limit_error)
    polish.py          — сервис Polish
    prompt_eng.py      — сервис Prompt Engineer + Skills RAG
    humanizer.py       — сервис Humanizer
    translator.py      — сервис Translator
    summary.py         — сервис Summary
    skills_db.py       — SkillsDB (BM25 индекс + search)

  storage/
    db.py              — async engine + session maker
    models.py          — SQLAlchemy 2.0 модели (User, RequestHistory, TranscriptionCache, SkillIndex)
    users.py           — CRUD для users
    history.py         — CRUD для request_history

  prompts/
    polish.py          — системные промпты Polish (4 подстиля)
    prompt_eng.py      — системные промпты Prompt Engineer (4 подстиля)
    humanizer.py       — системные промпты Humanizer (2 подстиля)
    translator.py      — системный промпт Translator

  ui/
    design.py          — константы дизайна (MODE_NAME, MODE_ICON, STYLE_NAME, STYLE_ICON, LANG_FLAG, ICON_*)
    keyboards.py       — все inline-клавиатуры (Unicode-символы на всех кнопках)
    messages.py        — шаблоны текстовых сообщений

  middlewares/
    auth.py            — проверка ALLOWED_USER_IDS
    rate_limit.py      — in-memory rate limit
    db_session.py      — инжекция AsyncSession
```

## Skills RAG — 8 репозиториев

| # | Репозиторий | Что внутри | Используется в |
|---|-------------|------------|----------------|
| 1 | anthropics/skills | 17 официальных Claude Skills | Prompt Engineer |
| 2 | nextlevelbuilder/ui-ux-pro-max-skill | CSV-базы: продукты, стили, палитры, типографика | Designer + Coder |
| 3 | blader/humanizer | Skill для удаления AI-маркеров | Humanizer |
| 4 | f/prompts.chat | 161k stars, коллекция промптов | Prompt Engineer |
| 5 | dair-ai/Prompt-Engineering-Guide | Гайды по промпт-инженерии | Prompt Engineer |
| 6 | danielrosehill/STT-Basic-Cleanup-System-Prompt | Промпты для cleanup STT | Polish |
| 7 | alirezarezvani/claude-skills | 232 production skills | Prompt Engineer, Coder |
| 8 | davila7/claude-code-templates | Шаблоны и skills | Prompt Engineer |

## Сессия 1 — Первоначальная разработка (Devin)

Создание всего проекта с нуля по ТЗ v3:
- Полная реализация всех 4 режимов
- PostgreSQL схема + миграции
- Skills sync из 8 репозиториев
- Docker + docker-compose
- 52 теста (pytest)
- Деплой на Render

## Сессия 2 — UI/UX доработки (Юсуф)

Коммиты на ветке `devin/1778083729-voice-polisher-bot`:
- Дизайн-система: MODE_NAME, STYLE_NAME, LANG_FLAG
- Русский UI (ПОЛИРОВКА, ПРОМПТ, ОЧЕЛОВЕЧИТЬ, ПЕРЕВОД)
- Цветные кнопки (`style=` параметр) -> убраны (не в aiogram API на тот момент; возвращены в Сессии 7 через Bot API 9.4)
- Reply-to-voice (частично)
- Retry + fallback для Groq API

## Сессия 3 — Code Review + Bugfixes

Ветка: `devin/1778145843-review-fixes`
PR: https://github.com/Itosyro/voice-bot/pull/3

### Что изменено

1. **`src/handlers/voice.py`** — порядок хендлеров, ffmpeg таймаут, экспорт в файл, сохранение ошибок
2. **`src/handlers/callbacks.py`** — фильтр set_default, HTML-экранирование
3. **`src/handlers/text.py`** — проверка пустого результата, экспорт в файл, сохранение ошибок
4. **`src/handlers/settings.py`** — валидация /lang, top-level imports
5. **`src/bot.py`** — Auth/RateLimit middleware на callback_query
6. **`src/utils.py`** — escape_html + send_result (экспорт в файл при >4096 символов)
7. **`src/services/llm.py`** — is_rate_limit_error без ложных срабатываний
8. **`src/services/transcribe.py`** — IntegrityError обработка race condition
9. **`src/services/summary.py`** — отдельный API ключ через get_groq_key("summary")
10. **`src/config.py`** — "summary" в key_map
11. **`src/middlewares/auth.py`** — CallbackQuery ответ с show_alert
12. **`src/middlewares/rate_limit.py`** — CallbackQuery ответ с show_alert
13. **`src/states.py`** — удалён (dead code)
14. **`src/services/audio.py`** — удалён (dead code)

## Сессия 7 — Unicode-символы + цветные кнопки (Bot API 9.4)

Ветка: `devin/1778153304-unicode-buttons`
PR: https://github.com/Itosyro/voice-bot/pull/4

### Что изменено

1. **`src/ui/design.py`**:
   - STYLE_ICON — Unicode-маркеры для подстилей (▪ ▫ ◦ ▸ ◈)
   - ICON_DOWNLOAD = "⇩"
   - BTN_STYLE_* константы цветов кнопок (primary, success, danger)
2. **`src/ui/keyboards.py`**:
   - Unicode-символы на всех кнопках (режимы, действия, настройки, стили)
   - `style=` параметр на всех InlineKeyboardButton (Bot API 9.4)
   - Emoji-флаги стран для языков сохранены
   - Добавлен helper `_mode_info_btn()`

### Цветовая схема кнопок

| Тип кнопки | Стиль | Цвет |
|------------|--------|------|
| Режимы (5 шт) | danger | Красный |
| Действия (Повтор, Меню…) | danger | Красный |
| Подрежимы (стили) | primary | Синий |
| Назад/Сброс | danger | Красный |
| Настройки, История | — | Дефолтный (белый) |
| Языки | — | Дефолтный (белый) |

## Сессия 8 — Webhook + Health-check (не засыпает на Render)

### Проблема

Render Free Tier усыпляет сервис через ~15 минут без входящего трафика. Бот работает в режиме **long polling** — он сам ходит к Telegram за обновлениями. Когда Render усыпляет процесс, polling прекращается и бот перестаёт отвечать. При этом Render dashboard показывает "deployed" (зелёный) — потому что последний деплой был успешным, но сам процесс уже спит.

### Решение

Два изменения, которые решают проблему комплексно:

#### 1. Webhook вместо Long Polling

**Что:** Переключить бота с `dp.start_polling()` на Webhook-режим.

**Как работает:**
- Бот регистрирует у Telegram URL вида `https://voice-polisher-bot.onrender.com/webhook/<BOT_TOKEN>`
- Telegram отправляет обновления (сообщения, нажатия кнопок) как HTTP POST запросы на этот URL
- Render получает входящий HTTP запрос → сервис просыпается → обрабатывает update
- Это значит, что каждое сообщение пользователя само будит бота (если он заснул)

**Какие файлы меняются:**

| Файл | Что меняется |
|------|-------------|
| `src/config.py` | Добавить поле `webhook_url: str \| None = None` и `webhook_secret: str \| None = None` |
| `src/main.py` | Переписать `main()`: если `webhook_url` задан — запускать aiohttp-сервер с webhook handler; если нет — использовать long polling (для локальной разработки) |
| `render.yaml` | Добавить env var `WEBHOOK_URL` |

**Детали реализации в `src/main.py`:**
```
Если webhook_url задан:
  1. Создать aiohttp app
  2. Добавить маршруты: GET /health → "ok", POST /webhook/<token> → aiogram webhook handler
  3. bot.set_webhook(webhook_url + "/webhook/" + token, secret_token=webhook_secret)
  4. Запустить aiohttp сервер на 0.0.0.0:PORT
  5. При shutdown — bot.delete_webhook()

Если webhook_url НЕ задан (локалка):
  Как сейчас — dp.start_polling(bot)
```

#### 2. Health-check keep-alive (самопинг)

**Что:** Добавить фоновый таск, который пингует сам себя каждые 10 минут.

**Как работает:**
- При старте бота запускается `asyncio.Task`, который каждые 600 секунд (10 мин) делает HTTP GET на `{webhook_url}/health`
- Это не даёт Render усыпить сервис, потому что каждые 10 минут приходит трафик
- Если `webhook_url` не задан (локалка) — self-ping не запускается

**Какие файлы меняются:**

| Файл | Что меняется |
|------|-------------|
| `src/main.py` | Добавить `async def _self_ping()` — цикл с `aiohttp.ClientSession().get(url)` каждые 600 сек |

### Итого: что поменяется

```
src/config.py   — +2 поля (webhook_url, webhook_secret)
src/main.py     — переписать main() с поддержкой webhook + self-ping
render.yaml     — +1 env var (WEBHOOK_URL)
```

### Обратная совместимость

- Если `WEBHOOK_URL` не задан — бот работает как раньше (long polling). Для локальной разработки ничего не меняется.
- Health-check endpoint `/health` уже есть — он сохраняется.
