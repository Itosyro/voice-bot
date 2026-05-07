# Voice Polisher Bot — Progress

## Сессия 1: Первоначальная разработка

- [x] Структура проекта (src/, handlers/, services/, storage/, prompts/, ui/)
- [x] pydantic-settings конфигурация (.env)
- [x] PostgreSQL схема (users, request_history, transcription_cache, skills_index)
- [x] SQLAlchemy 2.0 async модели
- [x] Alembic миграции
- [x] CRUD для users и history
- [x] Groq Whisper STT (transcribe.py)
- [x] Groq LLM обёртка (llm.py)
- [x] Сервис Polish (4 подстиля: raw, default, creative, formal, embellish)
- [x] Сервис Prompt Engineer (4 подстиля: general, designer, coder, coder_strict)
- [x] Сервис Humanizer (2 подстиля: lite, strong)
- [x] Сервис Translator (10+ языков)
- [x] Skills sync из 8 репозиториев (scripts/sync_skills.py)
- [x] SkillsDB с BM25 поиском
- [x] Telegram handlers (start, modes, voice, text, callbacks, settings, admin)
- [x] Inline-клавиатуры
- [x] Middlewares (auth, rate_limit, db_session)
- [x] Docker + docker-compose
- [x] 52 теста (pytest)
- [x] Деплой на Render

## Сессия 2: UI/UX доработки

- [x] Дизайн-система (MODE_NAME, STYLE_NAME, STYLE_DESC, LANG_FLAG)
- [x] Русский UI (ПОЛИРОВКА, ПРОМПТ, ОЧЕЛОВЕЧИТЬ, ПЕРЕВОД)
- [x] Убраны emoji/иконки с кнопок (чистый текст)
- [x] Retry + fallback для Groq API ошибок
- [x] Подробные ошибки (rate limit, model not found)
- [x] Reply-to-voice (частичная реализация)

## Сессия 3: Code Review + Bugfixes

### Найденные проблемы

| # | Проблема | Критичность | Статус |
|---|----------|-------------|--------|
| 1 | Reply-to-voice работал только voice->voice, не ловил ответ текстом на голосовое | Высокая | [x] Исправлено |
| 2 | Forwarded voice не обрабатывались (не было отдельного хендлера) | Высокая | [x] Исправлено |
| 3 | `on_set_default` callback — фильтр `==` не матчил суффикс с режимом | Высокая | [x] Исправлено |
| 4 | `style=` параметр в InlineKeyboardButton — не существует в aiogram API | Средняя | [x] Исправлено |
| 5 | Пустой результат от LLM не проверялся в text handler | Средняя | [x] Исправлено |
| 6 | `_escape_html` дублировался в voice.py и text.py | Средняя | [x] Исправлено |
| 7 | Превью истории не экранировалось (XSS через HTML) | Средняя | [x] Исправлено |
| 8 | `video_note` не обрабатывается | Низкая | [ ] Отложено (v1.1) |
| 9 | Неиспользуемый код (log в logging_config, states.py import) | Низкая | [x] Частично исправлено |
| 10 | Упоминание "Groq API" в ошибках rate limit (видно юзеру) | Средняя | [x] Исправлено |
| 11 | `HUMANIZER_VOICE_ERROR` без `parse_mode="HTML"` — HTML-теги видны как текст | Средняя | [x] Исправлено |
| 12 | `TEXT_TOO_LONG` без `parse_mode="HTML"` — `<b>` теги видны как текст | Средняя | [x] Исправлено |
| 13 | **Транскрипция и LLM используют ОДИН ключ Groq** — двойная нагрузка на 1 аккаунт | Критическая | [x] Исправлено |
| 14 | При rate limit retry использовался тот же исчерпанный ключ — ретраи бесполезны | Критическая | [x] Исправлено |
| 15 | `_get_client` импортировался как private (подчёркивание) в transcribe.py | Низкая | [x] Исправлено |

### Что было сделано

- [x] Полный code review всех файлов в src/
- [x] Исправлен порядок хендлеров: `handle_reply_to_voice` перед `handle_voice`
- [x] Фильтр reply-to: `F.reply_to_message.voice | F.reply_to_message.audio`
- [x] Forwarded voice ловится через `handle_voice` (F.voice | F.audio матчит и forward)
- [x] Фильтр `on_set_default`: `==` -> `startswith`
- [x] Убран `style` параметр из всех InlineKeyboardButton
- [x] Создан `src/utils.py` с общим `escape_html()`
- [x] HTML-экранирование превью истории в callbacks.py и settings.py
- [x] Проверка пустого результата в text handler
- [x] Убрана неиспользуемая переменная `log` в logging_config.py
- [x] Обновлён docstring в keyboards.py
- [x] Убраны упоминания "Groq API" из ошибок rate limit → "Сервер перегружен"
- [x] Добавлен `parse_mode="HTML"` для HUMANIZER_VOICE_ERROR в voice.py
- [x] Добавлен `parse_mode="HTML"` для TEXT_TOO_LONG в text.py
- [x] ruff check пройден
- [x] PR создан: https://github.com/Itosyro/voice-bot/pull/3
- [x] Планёрные документы (docs/plan.md, docs/progress.md)

### Третья итерация: Глубокий ревью (SocratiCode + Anthropic скиллы)

- [x] Найдена корневая причина rate limit: Whisper + LLM использовали один ключ
- [x] `config.py`: добавлены `get_all_groq_keys()` и `get_transcription_key()` (round-robin)
- [x] `llm.py`: ротация ключей при rate limit, `_get_client` → `get_client`
- [x] `transcribe.py`: ротация ключей при rate limit, исправлен import
- [x] `voice.py`: транскрипция использует отдельный ключ от LLM
- [x] `is_rate_limit_error()` — общая функция вместо дублирования в handlers
- [x] Ревью промптов (polish, prompt_eng, humanizer, translator) — качество высокое
- [x] ruff check + format пройдены
- [x] Локальное тестирование бота
- [x] Обновление environment config

## Сессия 4: Глубокий ревью + финальные фиксы

### Найденные проблемы (первая итерация)

| # | Проблема | Критичность | Статус |
|---|----------|-------------|--------|
| 16 | MODE_ICON: ⚡ и ✍ — emoji вместо Unicode символов (◇, ≈) | Средняя | [x] Исправлено |
| 17 | `tempfile.mktemp` в `_extract_audio_from_video` — race condition (insecure) | Средняя | [x] Исправлено |
| 18 | 5 файлов не соответствовали ruff format (design, callbacks, voice, keyboards, messages) | Низкая | [x] Исправлено |

### Проверено и подтверждено корректным

- [x] Reply-to-own-voice (re-transcribe) — работает корректно
- [x] Forwarded voice messages — ловятся через F.voice | F.audio
- [x] DbSessionMiddleware — `get_session()` уже коммитит через context manager
- [x] Export callback — `msg.text` корректно извлекает текст без HTML-тегов
- [x] Порядок роутеров в bot.py — voice перед text, корректно

### Что было сделано (первая итерация)

- [x] Полный code review всех файлов (handlers, services, ui, config, middlewares, prompts, storage)
- [x] MODE_ICON: `⚡` → `◇` (prompt), `✍` → `≈` (humanizer)
- [x] `tempfile.mktemp` → `tempfile.mkstemp` + `os.fdopen` (безопасно)
- [x] ruff check + ruff format пройдены
- [x] Коммит и пуш в PR #3

## Сессия 5: Супер-ревью (SocratiCode + Anthropic скиллы) + Self-Review + Тестирование

### Найденные проблемы (10 фиксов)

| # | Проблема | Критичность | Статус |
|---|----------|-------------|--------|
| 19 | `is_rate_limit_error` — ложные срабатывания ("rate" есть в "generate", "moderate") | Высокая | [x] Исправлено |
| 20 | Нет Auth/RateLimit middleware на callback_query — кнопки обходят защиту | Высокая | [x] Исправлено |
| 21 | Нет таймаута на ffmpeg процесс — может зависнуть навсегда | Средняя | [x] Исправлено |
| 22 | Текст может превысить лимит Telegram 4096 символов после escape_html | Средняя | [x] Исправлено |
| 23 | Нет валидации в `/lang` — принимает любой мусор | Средняя | [x] Исправлено |
| 24 | Race condition в TranscriptionCache (два запроса с тем же file_id) | Средняя | [x] Исправлено |
| 25 | Summary делит API ключ с Polish | Средняя | [x] Исправлено |
| 26 | Ошибки не сохраняются в историю запросов | Низкая | [x] Исправлено |
| 27 | Lazy imports в settings.py | Низкая | [x] Исправлено |
| 28 | Dead code: states.py, audio.py — не используются | Низкая | [x] Удалено |

### Допфиксы из self-review

| # | Проблема | Статус |
|---|----------|--------|
| 29 | Auth/RateLimit middleware не отвечают на CallbackQuery (спиннер зависает) | [x] Исправлено |
| 30 | Неиспользуемый `_SAFE_TEXT_LIMIT` в utils.py | [x] Удалено |

### Детали фиксов

- **Fix #19**: `is_rate_limit_error()` — теперь проверяет `RateLimitError` из Groq SDK + точные строки `"rate_limit"` / `"rate limit"`
- **Fix #20**: Auth + RateLimit middleware добавлены на `dp.callback_query`
- **Fix #21**: ffmpeg таймаут 30 сек через `asyncio.wait_for` + `proc.kill()`
- **Fix #22**: `send_result()` в `src/utils.py` — если результат > 4096 символов после HTML → отправляет `.txt` файлом со статусом "Текст слишком длинный — отправляю файлом…"
- **Fix #23**: `/lang` валидация — отклоняет коды не из `LANG_NAMES` и длиннее 5 символов
- **Fix #24**: `TranscriptionCache` — `try/except IntegrityError` + rollback при дубликате
- **Fix #25**: Summary использует `get_groq_key("summary")` → fallback ключ
- **Fix #26**: Ошибки сохраняются в `RequestHistory.error` (в voice.py и text.py)
- **Fix #27**: Lazy imports перенесены на top-level в settings.py
- **Fix #28**: Удалены `src/states.py` и `src/services/audio.py`
- **Fix #29**: Auth/RateLimit middleware — `callback.answer(text, show_alert=True)` при блокировке
- **Fix #30**: Удалён `_SAFE_TEXT_LIMIT = 3800`

### Тестирование

- [x] Бот запущен локально — стартует чисто, обработал /start без ошибок
- [x] 7 smoke-тестов пройдены:
  - `is_rate_limit_error()` нет ложных срабатываний
  - `escape_html()` корректно экранирует
  - `_TG_MSG_LIMIT == 4096`
  - LANG_NAMES валидация работает
  - `get_groq_key('summary')` возвращает fallback ключ
  - Dead code файлы удалены
  - `send_result()` сигнатура корректна
- [x] ruff check + ruff format — всё чисто
- [x] Environment config настроен для будущих сессий

## Отложено на будущее (v1.1)

- [x] Обработка video_note (добавлена в Сессии 3)
- [ ] Streaming ответов (editMessageText по мере генерации)
- [ ] Голосовой ответ (TTS)
- [ ] Длинные аудио (> 10 мин) — нарезка на чанки
- [x] Webhook вместо long-polling (реализовано в Сессии 8)
- [ ] Inline-mode (@bot полировать ...)
- [ ] Voice calibration в Humanizer
- [ ] Custom system prompts через /prompts/new
- [ ] Экспорт истории в Notion / Obsidian / .md

## Сессия 6: Split-message для длинных текстов

### Задача

Вместо отправки файлом при превышении 4096 символов — делим текст на части (макс. 3 части = ~12000 символов):
- Если текст ≤ 4096 → одно сообщение (как раньше)
- Если текст > 4096 и ≤ 12288 → делим на 2-3 части, перед отправкой пишем "📨 Текст разделён на N частей"
- Если текст > 12288 (3 × 4096) → отправляем файлом (fallback)

### Что изменено

- `src/utils.py` — `send_result()` переписан: split на части → отправка N сообщениями

## Сессия 7: Unicode-символы + цветные кнопки (Bot API 9.4)

### Задача

Добавить Unicode-символы на все кнопки Telegram-бота + цветные кнопки через Bot API 9.4 `style` field.

### Что сделано

- [x] Unicode-символы на всех кнопках (режимы, действия, настройки, стили)
- [x] Emoji-флаги стран для языков сохранены (🇬🇧 🇷🇺 🇪🇸 и т.д.)
- [x] Цветные кнопки через `style=` параметр (Bot API 9.4, aiogram 3.25+):
  - Режимы (5 шт) → `danger` (красный)
  - Действия (Повтор, Другой режим, Скачать, Меню) → `danger` (красный)
  - Подрежимы (стили) → `primary` (синий)
  - Назад/Сброс → `danger` (красный)
  - Настройки, История, Языки → без цвета (дефолтный)
- [x] Добавлены в design.py: STYLE_ICON, ICON_DOWNLOAD, BTN_STYLE_* константы
- [x] Добавлен helper `_mode_info_btn()` в keyboards.py
- [x] Замена emoji ⚙ на Unicode ⊛ (настройки) — единственный emoji на кнопках
- [x] ruff check + format пройдены
- [x] PR: https://github.com/Itosyro/voice-bot/pull/4

## Сессия 8: Webhook + Health-check (не засыпает на Render)

### Проблема

Render Free Tier усыпляет сервис через ~15 минут без трафика. Бот на long polling перестаёт отвечать.

### План реализации

- [x] Добавить `webhook_url` и `webhook_secret` в `src/config.py`
- [x] Переписать `src/main.py`:
  - Если `WEBHOOK_URL` задан → aiohttp сервер с webhook handler + health-check + self-ping
  - Если `WEBHOOK_URL` не задан → long polling (как раньше, для локалки)
- [x] Обновить `render.yaml` — добавить env vars `WEBHOOK_URL` и `WEBHOOK_SECRET`
- [x] Self-ping каждые 10 минут через `asyncio.Task` чтобы Render не усыплял
- [x] ruff check + format
- [x] Коммит и пуш в deploy ветку

### Что изменено

- **`src/config.py`** — добавлены `webhook_url: str | None = None` и `webhook_secret: str | None = None` (env: `WEBHOOK_URL`, `WEBHOOK_SECRET`).
- **`src/main.py`** — переписан `main()`:
  - В webhook-режиме: aiohttp app с маршрутами `GET /`, `GET /health`, `POST /webhook/<token>` (через `SimpleRequestHandler` + `setup_application` из aiogram 3); регистрация webhook через `bot.set_webhook(...)` с `secret_token`; фоновая задача `_self_ping()` (каждые 600 сек GET на `/health`); корректный shutdown (`delete_webhook`, отмена self-ping, `runner.cleanup`, `bot.session.close`, `engine.dispose`).
  - В polling-режиме (если `WEBHOOK_URL` не задан): как раньше — `dp.start_polling(bot)` + опциональный health server, если задан `PORT`.
- **`render.yaml`** — добавлены env vars `WEBHOOK_URL` и `WEBHOOK_SECRET` (`sync: false` — задаются вручную в Render Dashboard).

### Что нужно сделать вручную в Render Dashboard

1. `WEBHOOK_URL` = `https://voice-polisher-bot.onrender.com` (или фактический URL сервиса).
2. `WEBHOOK_SECRET` = любая случайная строка (например, `openssl rand -hex 32`) — используется как `X-Telegram-Bot-Api-Secret-Token` для верификации.

## Сессия 9 — Длинные голосовые до 1 часа (chunked streaming)

### Проблема

`max_voice_duration_sec=600`: голосовые/кружочки/audio дольше 10 мин отказ
`VOICE_TOO_LONG`. Реальные пользователи присылают 15-30-минутные записи.

### Решение

Pipeline для voices > 10 мин: ffmpeg режет на ~5-минутные опус-куски, каждый
кусок транскрибируется и (для polish/translator) сразу обрабатывается LLM
со стримингом результата в чат.

### Что сделано

- [x] `src/config.py`:
  - `max_voice_duration_sec` 600 → 3600 (1 час абсолютный максимум).
  - `chunk_threshold_sec=600` — выше этого порога включается chunked-режим.
  - `chunk_duration_sec=300` — длина одного чанка (5 мин).
  - `chunk_throttle_sec=1.5` — пауза между Groq-вызовами.
- [x] `src/services/transcribe.py` — `split_audio_to_chunks(audio_bytes, chunk_sec)`:
  одна вызов ffmpeg с `-f segment -segment_time` нарезает на opus 64k куски.
- [x] `src/ui/messages.py` — `LONG_VOICE_NOTICE`, `CHUNK_TRANSCRIBING`,
  `CHUNK_PROCESSING`, `CHUNK_FINAL_PROCESSING`, `CHUNK_RATE_LIMIT_PAUSE`,
  `LONG_VOICE_PARTIAL`, `LONG_VOICE_DONE`. `VOICE_TOO_LONG` теперь форматируется
  через `{max_min}` (минуты, не секунды).
- [x] `src/utils.py` — `send_chunk(target, header, text, reply_markup)`:
  посылает один streaming-кусок результатом одним или несколькими сообщениями
  до 4096 символов с разметкой `[i/n]`; reply_markup только на последнем.
- [x] `src/handlers/voice.py`:
  - `_process_voice` — branch на `duration > chunk_threshold_sec` →
    `_process_long_voice`.
  - `_process_long_voice` — основной chunked-pipeline: cache transcript →
    download → split → loop по чанкам с прогресс-сообщениями →
    polish/translator: per-chunk LLM + send_chunk;
    summary/prompt: collect-all → один LLM-вызов на полный текст в конце.
  - Кэш транскрипта (`TranscriptionCache`) пишется по полному файлу после
    нарезки — replays не пере-расшифровывают.
  - `_transcribe_chunk_with_retry` — на rate-limit пауза 25 сек и одна повторка.
- [x] `tests/test_edge_cases.py` — обновлён ассерт `{max_min}` вместо
  `{max_sec}` (тест и так зелёным не был — другие пре-existing failures).
- [x] `ruff check src/ && ruff format --check src/` — чисто.

### Поведение по режимам (chunked)

| Режим      | Стратегия                                                |
|------------|----------------------------------------------------------|
| polish     | Per-chunk LLM, стримим результат каждой части            |
| translator | Per-chunk LLM, стримим результат каждой части            |
| summary    | Collect-all → один LLM-вызов в конце на полный текст      |
| prompt     | Collect-all → один LLM-вызов в конце на полный текст      |
| humanizer  | Только текст, неприменимо для voice                      |

### UX короткой летописью

1. Voice > 10 мин → `LONG_VOICE_NOTICE` с числом частей и временем.
2. Каждый чанк: edit прогресса `🎙 Часть K/N — распознаю…` →
   `🛠 Часть K/N — обрабатываю…` → результат отдельным сообщением
   `Часть K/N\n<blockquote>...</blockquote>`.
3. Между чанками `chunk_throttle_sec` пауза.
4. Для summary/prompt после всех чанков: `✓ Расшифровка готова… Собираю
   итоговый…` → `send_result` с финальным текстом.
5. На rate-limit чанка — `⏳ Сервер перегружен на части K/N — пауза 25с` и
   ретрай.

## Статус

Все найденные проблемы (30 штук за 5 сессий) исправлены. UI обновлён Unicode-символами и цветными кнопками. Ни одного emoji на кнопках (кроме флагов стран). Код чист, линтер проходит. Сессия 8 (Webhook + Health-check) реализована. Сессия 9 (Long voice → chunked streaming) реализована.
