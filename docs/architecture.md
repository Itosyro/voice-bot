# Voice Polisher Bot — Architecture & Design Document

Это исчерпывающий design-doc продукта: что мы строим, для кого, как
устроено, какие компромиссы приняты и куда движемся. Документ задуман как
самодостаточный — новый разработчик должен иметь возможность развернуть
проект и быть продуктивным, прочитав только этот файл.

---

## 1. Цель продукта

**Что:** Telegram-бот, который превращает голосовые/аудио/видео-кружочки и
текстовые сообщения в чистый, полезный, готовый к публикации текст.

**Почему:** Голосовые удобно записывать, но неудобно потреблять. Текст,
надиктованный голосом, — самый быстрый способ зафиксировать мысль, но без
постобработки он плохо читается (слова-паразиты, обрывы фраз, грамматика).
Бот закрывает этот разрыв.

**Для кого:**

| Сегмент | Сценарий |
|---------|----------|
| Контент-мейкеры | Расшифровка длинных голосовых заметок в посты/статьи |
| Переводчики | Быстрый перевод voice-сообщений с сохранением тона |
| Промпт-инженеры | Сырая идея голосом → структурированный промпт |
| Аналитики | Расшифровка интервью/совещаний → саммари |
| Просто пользователи | Получить читаемый текст голосового от собеседника |

**Метрика успеха:** доля сообщений, на которые пользователь нажимает «Повтор»
или меняет режим (показатель неудовлетворённости результатом — должен
снижаться); время от отправки голоса до получения первой части ответа
(должно быть < 15 секунд для voices ≤ 5 мин).

---

## 2. Scope

### В скоупе

- 5 режимов обработки: Polish, Prompt Engineer, Humanizer, Translator, Summary.
- Голос (`voice`), аудио (`audio`), видео-кружочки (`video_note`) — для всех режимов кроме Humanizer.
- Текст напрямую и текст из caption-полей (forwarded, reply-to).
- Длинные голосовые до 1 часа с chunked-streaming.
- Inline-меню для выбора режимов/стилей/языков.
- История последних 10 запросов на пользователя.
- Авторизация по белому списку Telegram-ID и rate-limit на пользователя.

### Не в скоупе (сейчас)

- Inline-mode (`@bot polish ...`) — отложено.
- TTS (озвучивание ответа) — отложено.
- Streaming генерации LLM (editMessageText по токенам) — отложено.
- Voice calibration в Humanizer (обучение на корпусе пользователя) — отложено.
- Custom system prompts через `/prompts/new` — отложено.
- Экспорт истории в Notion/Obsidian/.md — отложено.

### Принятые ограничения

- Работа только в Telegram (другие мессенджеры не планируются).
- Без хранения сырых аудиофайлов — только транскрипты в кэше по
  `file_id`.
- Без мультиязычного UI — интерфейс на русском.
- Без real-time обработки — асинхронная очередь не нужна, request/response
  модель достаточна.

---

## 3. Технологический стек

### Runtime

- **Python 3.11+** (asyncio, type hints, structural pattern matching где
  уместно).
- **aiogram 3.27+** — асинхронный Telegram framework.
- **aiohttp 3.9+** — HTTP-сервер для webhook + self-ping client.
- **structlog** — структурированные JSON-логи.

### Внешние сервисы

- **Groq Cloud API** — единственный внешний LLM/STT провайдер.
  - **Whisper Large v3** — STT (полная модель, не turbo; выше точность,
    устойчивость к акцентам, мату, редкой лексике).
  - **Llama 3.3 70B Versatile** — основная LLM для всех режимов.
  - **Llama 3.1 8B Instant** — быстрая модель для лёгких операций.
  - **GPT-OSS 120B** — строгая модель для Coder Strict в Prompt Engineer.
- **Groq поддерживает 4-5 параллельных аккаунтов** — отдельный API-ключ
  на каждый режим + fallback ключ для round-robin при rate-limit.

### Хранилище

- **PostgreSQL 16** + asyncpg-драйвер.
- **SQLAlchemy 2.0 async** ORM с типизированными `Mapped[...]` колонками.
- **Alembic** для миграций.

### Инфраструктура

- **Docker Compose** — локальная разработка (бот + Postgres).
- **Render Free Tier** — production-хостинг (Web Service + Postgres).
- **Webhook mode** — Telegram пушит апдейты POST'ом, ничего не «спит».
- **Self-ping каждые 10 мин** — keep-alive для Render Free Tier.

### Прочее

- **rank-bm25** — BM25-индекс для skills RAG (in-memory).
- **pydantic-settings** — конфигурация через .env с валидацией.
- **ruff** — линтер + форматтер (line-length 100, конфиг в pyproject.toml).
- **pytest** — юнит-тесты (часть пре-existing failures документирована).

### Почему не GPT-4 / Claude / другие LLM

- **Groq** даёт серьёзную экономию: бесплатный тир покрывает всю нагрузку
  бота. На GPT-4 один такой бот стоил бы ~50-100$/мес даже на скромном
  трафике.
- **Скорость**: Groq отдаёт 200-500 t/s — Llama 70B на нём отвечает
  быстрее, чем большинство облачных LLM.
- **Whisper Large v3** — открытая модель, никакого вендор-лока, цена та же
  что и turbo.

---

## 4. Архитектура (компоненты)

```
                                    Telegram Cloud
                                           │
                                           │ POST /webhook/<token>
                                           ▼
                         ┌─────────────────────────────────────┐
                         │            aiohttp app              │
                         │   GET /         → health (200 ok)    │
                         │   GET /health   → health (200 ok)    │
                         │   POST /webhook → SimpleRequestHandler│
                         └────────────────┬────────────────────┘
                                           │
                                           ▼
                         ┌─────────────────────────────────────┐
                         │          aiogram Dispatcher         │
                         │    Middlewares (order matters):     │
                         │      1. Auth (белый список)         │
                         │      2. RateLimit (in-memory, 20/min)│
                         │      3. DbSession (AsyncSession)    │
                         └────────────────┬────────────────────┘
                                           │
                                           ▼
                         ┌─────────────────────────────────────┐
                         │              Routers                │
                         │   start ─ modes ─ settings ─ admin  │
                         │   callbacks ─ voice ─ text          │
                         └────────────────┬────────────────────┘
                                           │
                          ┌────────────────┼─────────────────┐
                          ▼                ▼                 ▼
                   ┌────────────┐   ┌────────────┐    ┌──────────┐
                   │ Mode router│   │ Voice flow │    │ Settings │
                   │ (callbacks)│   │ short/long │    │  /lang   │
                   └─────┬──────┘   └──────┬─────┘    └─────┬────┘
                         │                 │                 │
                         ▼                 ▼                 ▼
                   ┌──────────────────────────────────────────┐
                   │            Services layer                │
                   │  transcribe ─ llm ─ polish ─ prompt_eng  │
                   │  humanizer  ─ translator ─ summary       │
                   │  skills_db  (BM25 index, in-memory)      │
                   └────────────┬─────────────────────────────┘
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
           ┌─────────┐    ┌──────────┐    ┌─────────────┐
           │ Groq STT│    │ Groq LLM │    │ PostgreSQL  │
           │ Whisper │    │ Llama 70B│    │ users,      │
           │ Large v3│    │ Llama 8B │    │ history,    │
           │         │    │ GPT-OSS  │    │ cache,skills│
           └─────────┘    └──────────┘    └─────────────┘
```

### Потоки

#### Текстовый запрос

```
User text → AuthMiddleware → RateLimitMiddleware → DbSession
  → text router → mode router → service (polish/prompt/humanizer/...)
  → Groq LLM → send_result (split на 4096 + reply_markup)
  → save RequestHistory
```

#### Короткий голос (≤ 10 мин)

```
User voice → ... middlewares ...
  → voice router → handle_voice
  → download bytes → ffmpeg if video_note
  → transcribe (Groq Whisper, cache lookup by file_id)
  → service LLM → send_result → save history
```

#### Длинный голос (> 10 мин)

```
User voice → ... middlewares ...
  → voice router → handle_voice → _process_long_voice
  → check cache by file_id
     ├─ HIT  → _long_voice_cached_fast_path
     │         (single LLM call on full text → send_result)
     └─ MISS → download → split_audio_to_chunks (ffmpeg -f segment)
              → for each chunk K/N:
                  - progress edit "🎙 Часть K/N — распознаю…"
                  - transcribe chunk (1 retry on 429, 25s pause)
                  - if polish/translator:
                      progress edit "🛠 Часть K/N — обрабатываю…"
                      _run_mode_llm(chunk_text, mode, ...)
                      send_chunk(part header + result, reply_markup if last)
                  - if summary/prompt: collect transcripts
                  - throttle 1.5s between Groq calls
              → if summary/prompt: _run_mode_llm(full_text) → send_result
              → cache full transcript by file_id
              → final edit "✓ Готово — обработано N частей" + mode_keyboard
```

---

## 5. Структура кода

```
voice-bot/
├── src/
│   ├── main.py                — точка входа: webhook ↔ polling, self-ping
│   ├── bot.py                 — create_bot + create_dispatcher (роутеры,
│   │                            middlewares, error handler)
│   ├── config.py              — Settings (pydantic-settings) + key rotation
│   ├── utils.py               — escape_html, send_result (split на 4096 +
│   │                            file fallback), send_chunk (streaming)
│   ├── logging_config.py      — structlog setup (JSON или text)
│   │
│   ├── handlers/              — слой Telegram I/O
│   │   ├── start.py           — /start, /help
│   │   ├── modes.py           — /modes
│   │   ├── voice.py           — voice/audio/video_note (короткий + длинный
│   │   │                         pipeline, replay/cache fast-path)
│   │   ├── text.py            — обычный/forward/caption текст
│   │   ├── callbacks.py       — inline-кнопки (выбор режима/стиля/повтор)
│   │   ├── settings.py        — /settings, /lang, /history
│   │   └── admin.py           — /sync_skills, /stats
│   │
│   ├── services/              — бизнес-логика, без I/O Telegram
│   │   ├── transcribe.py      — Groq Whisper + split_audio_to_chunks
│   │   ├── llm.py             — обёртка Groq complete + retry + key
│   │   │                         rotation + fallback модель
│   │   ├── polish.py
│   │   ├── prompt_eng.py      — + Skills RAG (BM25 lookup)
│   │   ├── humanizer.py
│   │   ├── translator.py
│   │   ├── summary.py
│   │   └── skills_db.py       — in-memory BM25 индекс по skills
│   │
│   ├── prompts/               — системные промпты по режимам/подстилям
│   │   ├── polish.py
│   │   ├── prompt_eng.py
│   │   ├── humanizer.py
│   │   └── translator.py
│   │
│   ├── ui/                    — UI-константы (НЕ HTML, чистая разметка)
│   │   ├── design.py          — MODE_NAME, MODE_ICON, STYLE_NAME, STYLE_ICON,
│   │   │                         LANG_FLAG, BTN_STYLE_*
│   │   ├── keyboards.py       — все InlineKeyboardMarkup
│   │   └── messages.py        — текстовые шаблоны (form-able через .format)
│   │
│   ├── middlewares/
│   │   ├── auth.py            — ALLOWED_USER_IDS (response 403 для
│   │   │                         CallbackQuery — show_alert)
│   │   ├── rate_limit.py      — in-memory window 20/min/user
│   │   └── db_session.py      — инжектит AsyncSession + commit/rollback
│   │
│   └── storage/
│       ├── db.py              — async engine + session maker
│       ├── models.py          — User, RequestHistory, TranscriptionCache,
│       │                         SkillIndex
│       ├── users.py
│       └── history.py
│
├── alembic/                   — миграции БД
├── scripts/
│   └── sync_skills.py         — клонирует/обновляет 8 репо, индексирует
│                                 skill-файлы, пишет в `skills_index`
├── tests/                     — pytest юнит-тесты
├── docs/
│   ├── architecture.md        — этот файл
│   ├── plan.md                — план работ по сессиям
│   └── progress.md            — летопись изменений
├── docker-compose.yml
├── Dockerfile                 — Python 3.11 + ffmpeg + opus
├── render.yaml                — Render blueprint (Web Service + Postgres)
├── pyproject.toml             — зависимости + ruff config
└── .env.example               — все настройки с комментариями
```

---

## 6. Слои и инварианты

| Слой | Знает про | Не знает про |
|------|-----------|--------------|
| `handlers/` | aiogram, services, ui, storage | как Groq устроен |
| `services/` | Groq SDK, prompts, storage | aiogram, ui |
| `ui/` | константы, шаблоны | services, storage, Groq |
| `prompts/` | только строки и системные промпты | всё остальное |
| `storage/` | SQLAlchemy, asyncpg | aiogram, Groq |
| `middlewares/` | aiogram, storage | services, Groq |

### Жёсткие инварианты

1. **ALLOWED_USER_IDS** проверяется в middleware на `message` И на
   `callback_query`. Любой обход через кнопки невозможен.
2. **HTML-экранирование**: всё, что юзер видит в `parse_mode="HTML"`,
   проходит через `escape_html`. Превью истории, транскрипты, ошибки.
3. **Сообщение Telegram ≤ 4096 символов**: `send_result` режет длинный
   ответ на части (макс 3 = 12288 симв.) или отправляет файлом.
4. **Кэш STT**: `TranscriptionCache` — primary key `file_id`. Дубли через
   `try/except IntegrityError + rollback`.
5. **Rate-limit Groq**: на 429 — round-robin по всем доступным ключам, не
   ретраим тем же ключом.
6. **Хранение секретов**: ни одного API-ключа в коде. Только через env.
   `render.yaml` envVars — `sync: false`, задаются вручную в дашборде.

---

## 7. Режимы — детально

### 7.1 Polish

**Задача:** транскрипт → грамотный связный текст, сохраняя интонацию.

**Подстили:**

- `default` — нейтральная полировка, минимум вмешательства.
- `creative` — допускает стилистические улучшения, синонимы.
- `formal` — деловой регистр, без сокращений.
- `embellish` — расширяет, добавляет связки.

**LLM:** `llama-3.3-70b-versatile`.

**Ключ Groq:** `groq_api_key_polish` (с fallback на `groq_api_key_fallback`).

### 7.2 Prompt Engineer

**Задача:** сырая идея → структурированный промпт для LLM.

**Подстили:**

- `general` — универсальный промпт.
- `designer` — UI/UX-фокус, использует `nextlevelbuilder/ui-ux-pro-max-skill`.
- `coder` — код-фокус, использует `alirezarezvani/claude-skills`.
- `coder_strict` — особо строгие требования, использует `gpt-oss-120b`.

**LLM:** `llama-3.3-70b-versatile` (default), `gpt-oss-120b` (strict).

**RAG:** перед вызовом LLM делает BM25-поиск по `skills_index` по тексту
запроса, top-K релевантных skills включаются в системный промпт.

**Ключ Groq:** `groq_api_key_prompt`.

### 7.3 Humanizer

**Задача:** убрать AI-маркеры из текста (em-dash, типичные обороты,
идеально-параллельную структуру).

**Подстили:**

- `lite` — мягкая правка, сохраняет смысл и тон.
- `strong` — переписывает агрессивно, делает «человечнее».

**Принимает только текст** (не голос — для голоса нет AI-маркеров).

**LLM:** `llama-3.3-70b-versatile`.

**Ключ Groq:** `groq_api_key_humanizer`.

### 7.4 Translator

**Задача:** перевод с сохранением тона и регистра.

**Языки:** EN, RU, ES, FR, DE, ZH, JA, KO, AR, TR, PT, IT, PL, UK (14).

**Выбор языка:** сохраняется в `User.target_lang` (default `en`).

**LLM:** `llama-3.3-70b-versatile`.

**Ключ Groq:** `groq_api_key_translator`.

### 7.5 Summary

**Задача:** длинный текст/голос → ключевые тезисы.

**LLM:** `llama-3.3-70b-versatile`.

**Ключ Groq:** `groq_api_key_fallback` (отдельного нет, чтобы не плодить
аккаунты — режим экономный).

---

## 8. Длинные голосовые (chunked streaming)

### Параметры

| Параметр | Значение | Где |
|----------|----------|-----|
| `max_voice_duration_sec` | 3600 | абсолютный максимум, выше — `VOICE_TOO_LONG` |
| `chunk_threshold_sec` | 600 | выше — chunked-pipeline |
| `chunk_duration_sec` | 300 | размер одного чанка (5 мин) |
| `chunk_throttle_sec` | 1.5 | пауза между Groq STT-вызовами |
| Telegram message limit | 4096 | каждый чанк результата режется |
| Rate-limit pause | 25 сек + 1 ретрай | на Groq 429 |

### Алгоритм

1. `duration > chunk_threshold_sec` → `_process_long_voice`.
2. Cache lookup по `file_id`. Hit → fast-path (один LLM-вызов на полный
   transcript → `send_result`).
3. Miss → download bytes (ffmpeg для `video_note`) →
   `split_audio_to_chunks` (одна ffmpeg-команда `-f segment` на opus 64k).
4. Цикл по чанкам:
   - edit прогресс «🎙 Часть K/N — распознаю…»
   - `_transcribe_chunk_with_retry`: на 429 пауза 25 сек + 1 ретрай.
   - polish/translator: edit «🛠 Часть K/N — обрабатываю…»,
     `_run_mode_llm` per chunk, `send_chunk(...)` (с reply_markup на
     последнем чанке).
   - summary/prompt: накапливаем транскрипты.
   - `await asyncio.sleep(chunk_throttle_sec)`.
5. Финал:
   - polish/translator: edit «✓ Готово — обработано N частей.»
     с `mode_keyboard`.
   - summary/prompt: edit «✓ Расшифровка готова… Собираю итоговый…»,
     один `_run_mode_llm` на склейку всех транскриптов, `send_result`.
6. Кэш: `TranscriptionCache(file_id, full_transcript)`.

### Tradeoffs

- **Per-chunk LLM для polish/translator** ломает контекст между чанками
  (если фраза разорвалась). На границах склейка хуже, чем у одного
  большого вызова. Но: в обмен — стриминг (юзер видит результат сразу),
  отсутствие 4096-проблемы у LLM, устойчивость к 429.
- **Collect-all для summary/prompt** требует ждать конца расшифровки.
  Альтернатива (map-reduce) дала бы стриминг, но потеряла бы качество.
- **`transcription_ms` в `RequestHistory` для длинных голосов = 0**.
  Per-chunk STT-времена не агрегируются — это явный нуль вместо
  введения в заблуждение тотал-временем pipeline.

---

## 9. Хранилище

### Таблицы

#### `users`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | bigint, PK | Внутренний ID |
| `telegram_user_id` | bigint, unique | ID юзера в Telegram |
| `username`, `first_name`, `language_code` | text | Профиль |
| `default_mode` | text | Сохранённый режим |
| `default_style` | text | Сохранённый стиль |
| `target_lang` | text, default 'en' | Язык перевода |
| `llm_model` | text | Override модели для пользователя |
| `total_requests`, `total_voice_seconds` | int | Метрики |
| `is_admin`, `is_blocked` | bool | Флаги |
| `created_at`, `updated_at` | timestamptz | Аудит |

#### `request_history`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | bigint, PK | |
| `user_id` | bigint, FK→users (cascade) | |
| `mode`, `style` | text | Режим и подстиль |
| `input_type` | text | `voice`, `audio`, `video_note`, `text` |
| `input_length` | int | Символы или секунды |
| `input_preview` | text | Первые ~200 символов (для UI истории) |
| `output_text`, `output_length` | text/int | Результат |
| `llm_model` | text | Реально использованная модель |
| `transcription_ms`, `llm_ms`, `total_ms` | int | Тайминги |
| `error` | text | Если упало — текст ошибки |
| `created_at` | timestamptz | |

#### `transcription_cache`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `file_id` | text, PK | Telegram `file_id` |
| `transcript` | text | Полный транскрипт |
| `duration_sec` | int | Длина исходного аудио |
| `language` | text | Язык, если определён |
| `created_at` | timestamptz | |

Replay той же голосовой пропускает STT (один LLM-вызов на кэше).

#### `skills_index`

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | bigint, PK | |
| `source_repo` | text | Репозиторий-источник |
| `skill_name`, `description`, `body` | text | Skill content |
| `file_path` | text | Путь внутри репо |
| `tags` | text[] | Опциональные тэги |
| `created_at` | timestamptz | |

In-memory BM25-индекс строится на старте через `SkillsDB.load_from_db`.

### Миграции

Через Alembic. На старте контейнера выполняется `alembic upgrade head`.

---

## 10. Skills RAG

### Источники (8 репозиториев)

| # | Репозиторий | Что внутри | Используется в |
|---|-------------|------------|----------------|
| 1 | anthropics/skills | 17 официальных Claude Skills | Prompt Engineer |
| 2 | nextlevelbuilder/ui-ux-pro-max-skill | UI/UX-CSV (продукты, стили, палитры) | Designer + Coder |
| 3 | blader/humanizer | Humanizer skill | Humanizer |
| 4 | f/prompts.chat | 161k stars, коллекция промптов | Prompt Engineer |
| 5 | dair-ai/Prompt-Engineering-Guide | Гайды по промпт-инжинирингу | Prompt Engineer |
| 6 | danielrosehill/STT-Basic-Cleanup-System-Prompt | Cleanup-промпты | Polish |
| 7 | alirezarezvani/claude-skills | 232 production skills | Prompt Engineer, Coder |
| 8 | davila7/claude-code-templates | Шаблоны и skills | Prompt Engineer |

### Sync-pipeline

`scripts/sync_skills.py`:
1. Клонирует/обновляет каждый репо в `/tmp/skills/<repo>`.
2. Парсит `*.md` / `*.skill` / `*.txt` файлы.
3. Извлекает `name` / `description` / `body`.
4. `INSERT` в `skills_index` (truncate-first).

Запуск: `/sync_skills` командой админа или раз в `skills_sync_interval_hours`
(default 168 = неделя).

### Поиск

`SkillsDB.search(query, top_k=5)`:
- BM25-rank по `description + body`.
- Возвращает top_k skill-tuples.
- Тексты включаются в системный промпт Prompt Engineer как контекст.

---

## 11. Авторизация и безопасность

### Уровни доступа

- **Открытый бот:** `ALLOWED_USER_IDS` пуст — отвечает всем.
- **Закрытый бот:** `ALLOWED_USER_IDS=123,456` — только белый список.
- **Админ:** `ADMIN_USER_IDS=123` — доступ к `/sync_skills`, `/stats`.

### AuthMiddleware

- Проверяет `event.from_user.id` против белого списка.
- На `Message` — игнорирует.
- На `CallbackQuery` — `callback.answer("Доступ запрещён", show_alert=True)`.

### RateLimitMiddleware

- In-memory window: 20 запросов / 60 секунд / пользователь.
- При превышении — `callback.answer("Слишком часто", show_alert=True)` или
  игнор для `Message`.

### Webhook security

- `secret_token` (header `X-Telegram-Bot-Api-Secret-Token`) проверяется
  aiogram'ом — чужой POST не пройдёт.
- URL содержит `/webhook/<TOKEN>` — даже без secret сложно угадать.
- HTTPS обеспечивает Render (TLS termination на их edge).

### Не утекает

- API-ключи Groq никогда не попадают в логи (только в env).
- `request_history.error` обрезается до текста exception, без traceback.
- `parse_mode="HTML"` всегда в паре с `escape_html`.

---

## 12. Деплой

### Render (production)

- **Web Service** (Docker, Frankfurt regiо).
- **Postgres** (Free план, тот же региoн).
- **render.yaml** — blueprint с обоими сервисами.
- **env vars** (вручную через Dashboard, `sync: false`):
  - `TELEGRAM_BOT_TOKEN`
  - `GROQ_API_KEY_POLISH`, `_PROMPT`, `_HUMANIZER`, `_TRANSLATOR`,
    `_FALLBACK`
  - `WEBHOOK_URL=https://voice-polisher-bot.onrender.com`
  - `WEBHOOK_SECRET=<random hex>`
  - `ALLOWED_USER_IDS`, `ADMIN_USER_IDS`
- `DATABASE_URL` подставляется автоматически через `fromDatabase`.
- Деплой: push в `devin/1778145843-review-fixes` → автодеплой через
  GitHub.

### Local dev (Docker Compose)

```bash
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и хотя бы GROQ_API_KEY_FALLBACK
docker compose up --build
```

Что происходит на старте:
1. Поднимается Postgres.
2. `alembic upgrade head`.
3. `python scripts/sync_skills.py` (если первый запуск).
4. `python -m src.main` — поскольку `WEBHOOK_URL` не задан, идёт в polling.

### Webhook vs Polling

- В production (Render) — webhook (бот не «спит»).
- Локально — polling (нет публичного URL для webhook).
- Переключение полностью автоматическое: `if settings.webhook_url`.

---

## 13. Наблюдаемость

### Логи

`structlog` + JSON-output (Render умеет в JSON):

| Event | Когда |
|-------|-------|
| `starting_bot`, `mode=webhook/polling` | старт |
| `skills_loaded count=N` | старт |
| `webhook_set url=…` | webhook регистрация |
| `webhook_server_started port=…` | сервер запустился |
| `self_ping_ok url=…` | каждые 10 мин |
| `stt_retry attempt=… rate_limited=…` | ретрай Whisper |
| `stt_key_rotation` | переключение ключа |
| `groq_retry attempt=… model=… rate_limited=…` | ретрай LLM |
| `groq_key_rotation`, `groq_fallback` | переключение модели |
| `ffmpeg_split_failed`, `ffmpeg_split_timeout` | ошибки нарезки |
| `unhandled_error` | фолбэк в `dp.errors()` |

### Метрики (через `request_history`)

- `total_ms` — сколько занял весь pipeline.
- `transcription_ms` — STT (для длинных голосов = 0, осознанно).
- `llm_ms` — LLM-время.
- `error` — текст ошибки (если упало).

Запросы на `/stats` (только админ) показывают агрегаты.

---

## 14. Тестирование

### Юнит-тесты

`pytest tests/` — 46 тестов проходят. Часть пре-existing failures:
- `test_edge_cases.py::test_message_constants_exist` (MODE_NAMES).
- `test_edge_cases.py::test_fsm_states_exist` (несуществующий `src.states`).
- `test_modes.py` — AttributeError'ы.

Должны быть исправлены отдельной сессией.

### Линт

`ruff check src/ && ruff format --check src/` — проходит чисто. Конфиг в
`pyproject.toml`: line-length 100, кириллица разрешена через RUF001-003.

### Smoke

В прошлых сессиях (5, 7) бот проверялся локально через `docker compose up`
+ ручная отправка voice/text. На production проверяется через реальные
сообщения и `/health` endpoint.

---

## 15. Известные ограничения и риски

### Ограничения

1. **In-memory rate-limit и BM25** — не масштабируется на 2+ инстанса.
   Нужен Redis для rate-limit и Postgres-side BM25 (`pg_trgm` /
   `tsvector`) если будет нужен horizontal scale.
2. **Single-tenant**: бот один на инсталляцию. Multi-tenant потребует
   tenant-discriminator в БД.
3. **Free тир Groq имеет дневные лимиты** (по токенам и запросам). На
   высокой нагрузке нужны платные ключи.
4. **Render Free Tier**: 512 MB RAM, sleep после 15 мин (решено через
   self-ping). При высокой нагрузке нужен Standard план.
5. **ffmpeg на длинных голосах** грузит CPU — на 30-минутном файле
   нарезка занимает ~10-15 секунд.

### Риски

| Риск | Митигация |
|------|-----------|
| Groq blocks модель на одном из ключей | Fallback ключ + ротация ключей при ошибке |
| Telegram webhook падает | self-ping → быстрый перезапуск; `drop_pending_updates=True` |
| Postgres free план переполнен | LRU очистка `transcription_cache` (не реализована — отложено) |
| Юзер шлёт 1-часовое аудио на 1 GB | Telegram режет до 50 MB, плюс наш `MAX_VOICE_DURATION_SEC` |
| Утечка PAT/ключа в чате | Сейчас только ручная ротация — добавить pre-commit gitleaks |

---

## 16. Будущие шаги

| Приоритет | Что | Зачем |
|-----------|-----|-------|
| Высокий | Починить пре-existing test failures | Зелёный CI как маркёр здоровья |
| Высокий | Streaming генерации LLM (editMessageText по токенам) | Уменьшить TTFB для длинных текстов |
| Средний | Inline-mode (`@bot polish ...`) | UX в чужих чатах |
| Средний | Voice calibration в Humanizer | Текст по корпусу пользователя |
| Средний | Custom system prompts через `/prompts/new` | Гибкость без релиза |
| Средний | Map-reduce для summary длинных голосов | Стриминг + полный контекст |
| Низкий | TTS озвучивание ответа | Доступность |
| Низкий | Экспорт истории в Notion / Obsidian / .md | Power-юзеры |
| Низкий | Multi-tenant (один бот, много рабочих пространств) | SaaS-форма |

---

## 17. Глоссарий

- **STT** — Speech-to-Text (распознавание речи).
- **TTS** — Text-to-Speech (синтез речи).
- **LLM** — Large Language Model.
- **RAG** — Retrieval-Augmented Generation (LLM с подмешиванием
  контекста из БД/индекса).
- **BM25** — алгоритм ранжирования документов по запросу
  (вероятностная модель).
- **Webhook** — push-модель: сервер пушит апдейты POST'ом.
- **Long polling** — pull-модель: бот сам ходит за апдейтами.
- **Chunked streaming** — режем длинный вход на куски, шлём результаты
  по мере готовности.

---

## 18. Решения и компромиссы

| # | Решение | Альтернатива | Причина выбора |
|---|---------|--------------|----------------|
| 1 | aiogram 3 | python-telegram-bot, telethon | aiogram async-first, быстрая разработка, type hints |
| 2 | Groq | OpenAI / Anthropic | Бесплатный тир, скорость, no vendor lock |
| 3 | Postgres | SQLite | На Render multi-instance, async-драйвер mature |
| 4 | BM25 in-memory | pgvector / Qdrant | Skills <1000 — overkill держать external DB |
| 5 | Webhook | Long polling | Render Free Tier sleep |
| 6 | Per-chunk LLM (polish/translator) | One big LLM call | Стриминг UX + 4096-лимит + 429-устойчивость |
| 7 | Whisper Large v3 (full) | Whisper Large v3 Turbo | Пользователь выбрал качество над скоростью |
| 8 | Per-mode Groq keys | Один ключ | Распределение rate-limit |
| 9 | In-memory rate-limit | Redis | Single-instance, простота |
| 10 | Docker Compose локально, Render production | k8s | Минимальная сложность, оба деплоя без cold-start (после self-ping) |

---

## 19. Жизненный цикл сообщения

```
[Telegram] User присылает voice
   │
   ▼
[Telegram Cloud] POST https://voice-polisher-bot.onrender.com/webhook/<TOKEN>
   │
   ▼
[Render] aiohttp принимает POST
   │
   ▼
[aiogram] SimpleRequestHandler парсит Update, проверяет secret_token
   │
   ▼
[Middlewares]
   ├─ AuthMiddleware → user в whitelist?
   ├─ RateLimitMiddleware → 20/min?
   └─ DbSessionMiddleware → AsyncSession в handler
   │
   ▼
[voice.router] handle_voice матчит F.voice | F.audio
   │
   ▼
[voice handler] определяет:
   - mode (из user.default_mode или callback)
   - style (из user.default_style)
   - duration
   │
   ├─ duration ≤ 600 сек → _process_voice
   │       │
   │       ├─ download bytes
   │       ├─ transcribe (cache lookup)
   │       ├─ service.run(text, style, ...)
   │       └─ send_result
   │
   └─ duration > 600 сек → _process_long_voice
           │
           ├─ cache lookup → fast-path?
           ├─ download → split_audio_to_chunks
           └─ цикл по чанкам с прогресс-edit и send_chunk
   │
   ▼
[history] save_request(user, mode, style, input_type, output, llm_ms, ...)
   │
   ▼
[Telegram] sendMessage / editMessageText / sendDocument
   │
   ▼
[User] видит результат
```

---

## 20. Контрольный список нового разработчика

1. Прочитать этот файл целиком.
2. Прочитать `README.md` (3 минуты).
3. `git clone … && cp .env.example .env`.
4. Получить от @BotFather бот-токен → `TELEGRAM_BOT_TOKEN=…`.
5. Получить Groq-ключ на console.groq.com → `GROQ_API_KEY_FALLBACK=…`.
6. `docker compose up --build` → бот стартует в polling-режиме.
7. Отправить боту `/start` в Telegram.
8. Прочитать `docs/plan.md` чтобы понимать историю проекта.
9. Прочитать `docs/progress.md` чтобы знать текущее состояние.
10. Найти задачу в **Будущие шаги** (раздел 16) или взять issue.
11. Создать ветку `devin/<task>` от `devin/1778145843-review-fixes`.
12. Перед коммитом: `ruff check src/ && ruff format src/ && pytest tests/`.
13. Коммит / push / PR.

Готово.
