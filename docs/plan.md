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

## Сессия 9 — Длинные голосовые до 1 часа (chunked streaming)

### Проблема

Лимит `max_voice_duration_sec = 600` (10 мин) — голосовые/audio/кружочки
дольше 10 мин получали `VOICE_TOO_LONG`. Реальные пользователи присылают
15-30-минутные записи (лекции, длинные комментарии, кружочки).

### Решение

Отдельный pipeline для voices > 10 мин: ffmpeg режет файл на ~5-минутные
opus-куски, каждый кусок транскрибируется отдельно, результат стримится в
чат частями по мере готовности.

Между Groq-вызовами throttle 1.5 сек, чтобы не упирать в rate-limit. На 429
пауза 25 сек + 1 ретрай. Полный транскрипт кэшируется в `TranscriptionCache`
по `file_id` — replays того же голосового пропускают STT.

### Ключевые цифры

| Параметр | Значение | Что делает |
|----------|----------|------------|
| `max_voice_duration_sec` | 3600 | Абсолютный максимум (1 час) |
| `chunk_threshold_sec` | 600 | Выше — chunked-режим |
| `chunk_duration_sec` | 300 | Размер одного чанка (5 мин) |
| `chunk_throttle_sec` | 1.5 | Пауза между Groq-вызовами |
| Telegram-лимит сообщения | 4096 | Каждый чанк результата режется при превышении |

### Поведение по режимам

| Режим      | Стратегия                                                |
|------------|----------------------------------------------------------|
| polish     | Per-chunk LLM, стримим результат каждой части            |
| translator | Per-chunk LLM, стримим результат каждой части            |
| summary    | Collect-all → один LLM-вызов в конце на полный текст     |
| prompt     | Collect-all → один LLM-вызов в конце на полный текст     |
| humanizer  | Только текст, неприменимо для voice                      |

### UX

1. Voice > 10 мин →
   `🕐 Длинное аудио (X мин) — режу на N частей по ~5 мин и расшифровываю
   по очереди.`
2. Каждый чанк K/N:
   - edit прогресса: `🎙 Часть K/N — распознаю…`
   - после STT: `🛠 Часть K/N — обрабатываю…` *(только polish/translator)*
   - результат отдельным сообщением:
     `<b>Часть K/N</b>\n<blockquote><code>...</code></blockquote>`
     (если > 4096 символов — `[i/n]` подразделы).
3. После всех чанков:
   - polish/translator: `✓ Готово — обработано N частей.`
   - summary/prompt: `✓ Расшифровка готова (Z симв.). Собираю итоговый…` →
     финальное сообщение через `send_result`.
4. На rate-limit чанка: `⏳ Сервер перегружен на части K/N — пауза 25с и
   продолжаю.`
5. На пустую/упавшую расшифровку чанка: `⚠ Часть K/N не распозналась —
   пропускаю и иду дальше.`

### Какие файлы меняются

| Файл | Что меняется |
|------|-------------|
| `src/config.py` | +`chunk_threshold_sec`, +`chunk_duration_sec`, +`chunk_throttle_sec`, `max_voice_duration_sec` 600 → 3600 |
| `src/services/transcribe.py` | +`split_audio_to_chunks(audio_bytes, chunk_sec)` — ffmpeg `-f segment` нарезка на opus 64k |
| `src/ui/messages.py` | +`LONG_VOICE_NOTICE`, `CHUNK_TRANSCRIBING`, `CHUNK_PROCESSING`, `CHUNK_FINAL_PROCESSING`, `CHUNK_RATE_LIMIT_PAUSE`, `LONG_VOICE_PARTIAL`, `LONG_VOICE_DONE`. `VOICE_TOO_LONG` теперь `{max_min}` (минуты) |
| `src/utils.py` | +`send_chunk(target, header, text, reply_markup)` — посылает один streaming-кусок (одно или несколько сообщений ≤4096 символов с разметкой `[i/n]`) |
| `src/handlers/voice.py` | +`_process_long_voice` (chunked-pipeline), +`_transcribe_chunk_with_retry`, +`_run_chunk_llm`. `_process_voice` ветвится на `duration > chunk_threshold_sec` |

### Итого

```
src/config.py            — +3 поля, max 600→3600
src/services/transcribe.py — +split_audio_to_chunks
src/ui/messages.py       — +7 шаблонов, VOICE_TOO_LONG переформатирован
src/utils.py             — +send_chunk
src/handlers/voice.py    — +_process_long_voice + 2 helper
docs/progress.md         — Сессия 9
docs/plan.md             — Сессия 9
```

### Обратная совместимость

- Voices ≤ 10 мин обрабатываются как раньше (один transcribe + send_result),
  никаких изменений.
- Кэш транскрипта (`TranscriptionCache`) расширен: теперь по `file_id`
  кэшируется и склеенный транскрипт длинного голосового — replays идут мимо
  STT (один LLM-вызов на финальный transcript для summary/prompt либо стрим
  per-chunk LLM с уже кэшированным trannskript).
- ffmpeg уже в Dockerfile — деплой не ломается.

## Сессия 10 — STT upgrade + Документация (product-spec)

### Что произошло

После Сессии 9 был сделан строгий code-review длинного voice-pipeline,
найдено и зафиксировано 6 проблем (отдельный коммит `b7f3f9b`,
[review summary](../session9-review.md) — внутренний артефакт сессии).
Затем пользователь попросил три вещи: повысить качество STT, переписать
README под продукт, сделать большой design-doc по архитектуре.

### Решения

1. **STT — `whisper-large-v3-turbo` → `whisper-large-v3` (full).**
   - Полная модель работает медленнее turbo на ~30-50 %, но качество
     заметно выше: устойчивее к акцентам, мату, редкой лексике, меньше
     галлюцинаций на тихих фрагментах. Юзер явно выбрал качество над
     скоростью.
   - Меняем только `whisper_model` в `src/config.py` и `.env.example`.
     В `.env.example` заодно дописан блок параметров chunked-режима
     (`MAX_VOICE_DURATION_SEC`, `CHUNK_THRESHOLD_SEC`,
     `CHUNK_DURATION_SEC`, `CHUNK_THROTTLE_SEC`) — раньше они были только
     в коде.
   - На обработку длинных голосовых это влияет: 1 час аудио → 12 чанков
     × 5 мин, каждый чанк теперь идёт чуть медленнее, но финальный
     транскрипт точнее. Throttle и retry-логика не меняются.

2. **README → product-only.**
   - Вычистить deploy-инструкции (Render / Fly / Railway), `.env`,
     `docker compose up`, инструкции по получению ключей.
   - Оставить: что бот делает, 5 режимов, подстили, длинные голосовые,
     качество (модели), команды, безопасность, ссылки на дев-доки.
   - Цель: первый экран README'а отвечает «что это и кому полезно», а не
     «как поднять».

3. **`docs/architecture.md`** — новый design-doc.
   - Структура: цели → scope → стек → архитектура (компоненты + потоки)
     → структура кода → инварианты слоёв → режимы детально → длинные
     голосовые → хранилище → Skills RAG → авторизация и безопасность →
     деплой → наблюдаемость → тестирование → ограничения и риски →
     будущие шаги → глоссарий → решения и компромиссы → жизненный цикл
     сообщения → онбординг.
   - Размер: ~1000 строк. Самодостаточен — новый разработчик должен
     дочитать и быть продуктивным без сторонних источников.
   - Файл живёт в `docs/`, README ссылается на него.

### Файлы

| Файл | Что меняется |
|------|--------------|
| `src/config.py` | `whisper_model` → `"whisper-large-v3"` |
| `.env.example` | `WHISPER_MODEL=whisper-large-v3` + блок chunking-параметров |
| `README.md` | Полная замена на product-описание |
| `docs/architecture.md` | Новый файл — design-doc |
| `docs/plan.md` | Этот раздел |
| `docs/progress.md` | Чеклист Сессии 10 |

### Чего не меняем

- Webhook и self-ping — стабильно работают с Сессии 8.
- Chunked-pipeline — стабилен после Code-review (Сессия 9 + review fixes).
- Список зависимостей в Dockerfile / pyproject.toml не трогаем.
- Тесты остаются как есть (пре-existing failures документированы в
  Сессии 9 — отдельная задача).

### Обратная совместимость

- Бот работает на тех же ключах Groq.
- API Whisper Large v3 принимает те же файлы opus, что и turbo.
- Никаких миграций БД — модель указывается параметром API-вызова.
- На Render деплой автоматически подтянет новый коммит.
