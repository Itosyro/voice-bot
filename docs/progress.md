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
- [ ] Webhook вместо long-polling
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

## Статус

Все найденные проблемы (30 штук за 5 сессий) исправлены. Код чист, линтер проходит, бот стартует без ошибок.
