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
- [ ] Локальное тестирование бота
- [ ] Обновление environment config

## Отложено на будущее (v1.1)

- [ ] Обработка video_note
- [ ] Streaming ответов (editMessageText по мере генерации)
- [ ] Голосовой ответ (TTS)
- [ ] Длинные аудио (> 10 мин) — нарезка на чанки
- [ ] Webhook вместо long-polling
- [ ] Inline-mode (@bot полировать ...)
- [ ] Voice calibration в Humanizer
- [ ] Custom system prompts через /prompts/new
- [ ] Экспорт истории в Notion / Obsidian / .md
