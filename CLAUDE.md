# Voice Polisher Bot — CLAUDE.md

> Главный план-документ проекта. Держим его **актуальным**: что добавили, что
> убрали, на какие грабли наступили и почему приняли то или иное решение —
> чтобы будущие агенты не повторяли ошибок и понимали контекст.

---

## 1. Что это

Telegram-бот для обработки **голосовых сообщений и текста** через Groq AI.
Личный сервис на ~10–50 человек, закрыт через `ALLOWED_USER_IDS`.

**5 режимов:**

| Режим | Иконка | Что делает | Стили / параметры |
|---|---|---|---|
| **Polish** (Полировка) | ✎ | Чистит речь/текст: убирает «э-э», повторы, ставит пунктуацию | Сырой (как есть, temp 0.0) · Обычный · Творческий · Деловой · Литературный |
| **Prompt** (Промпт) | ◇ | Идея → готовый промпт для ИИ; подбирает роль/стек, тянет skills | Общий · Дизайнер · Кодер · Строгий (coder_strict) |
| **Humanizer** (Очеловечить) | ≈ | Убирает следы нейросети из текста | Лёгкий · Сильный · **только текст, не голос** |
| **Translator** (Перевод) | ⇄ | Перевод с сохранением тона | 14 языков (`LANG_FLAG` в design.py) |
| **Summary** (Саммари) | ∑ | Сжимает в 3–7 пунктов | без стилей |

**Вход:** голос / аудио / видео-кружки / видео — **напрямую, пересланные
(форвард) или реплаем** на чужое/своё сообщение. Голосовые **до 1 часа**
(длинные режутся на чанки). Транскрипт кэшируется по `file_id`.

**Выход:** результат — копируемая цитата (`<blockquote><code>`), тап-чтобы-скопировать.
Длинное бьётся на части или уходит файлом `.txt`. Под ответом кнопки:
Повтор · Другой режим · Скачать .txt · Меню.

---

## 2. Архитектура

```
src/
  main.py          — точка входа: skills load, выбор polling/webhook, health-сервер,
                     self-ping, фоновая TTL-очистка БД
  bot.py           — create_bot (parse_mode=None!) + create_dispatcher (роутеры/middleware)
  config.py        — Pydantic Settings (читает .env), get_groq_key/get_all_groq_keys
  logging_config.py— structlog (json/text)
  utils.py         — escape_html
  handlers/
    voice.py       — приём медиа (прямое/форвард/реплай), транскрипция, _process_media
    text.py        — текстовые сообщения, _process_text
    _reply.py      — send_result: копи-блок, разбивка на части, .txt-фолбэк
    _last.py       — in-memory стор последнего запроса (для кнопки «Повтор»)
    callbacks.py   — все inline-кнопки (выбор режима/стиля/языка, навигация, regenerate, export)
    start.py       — /start, /help
    modes.py       — /modes
    settings.py    — /settings, /lang, /history
    admin.py       — /stats, /users, /user, /ban, /unban, /sync_skills + бан-callbacks
  services/
    llm.py         — complete(): Groq chat (стриминг внутрь, retry, ротация ключей при 429)
    transcribe.py  — transcribe(), split_audio_to_chunks(), extract_audio_from_video() (ffmpeg)
    polish.py / prompt_eng.py / humanizer.py / translator.py / summary.py — режимы
    skills_db.py   — BM25-поиск по skills (in-memory из БД)
    audio.py       — (legacy-хелперы аудио)
  storage/
    models.py      — User, RequestHistory, TranscriptionCache, Skill, …
    db.py          — async engine (pool_size=5, statement_cache_size=0), get_session
    users.py       — get_or_create_user (атомарный upsert), update_user_settings, бан
    history.py     — save_request, get_user_history
    cleanup.py     — cleanup_old_records (TTL для cache/history)
  middlewares/
    auth.py        — ALLOWED_USER_IDS + динамический бан (is_blocked), админов не банит
    rate_limit.py  — in-memory скользящее окно, idle-юзеры выпиливаются из dict
    db_session.py  — открывает сессию на каждый апдейт, кладёт в data["session"]
  prompts/         — системные промпты на каждый режим/стиль
  ui/
    design.py      — ЕДИНЫЙ источник: BRAND, MODE_ICON, STYLE_*, BTN_STYLE_*, DIV, LANG_FLAG
    keyboards.py   — все клавиатуры (style= для цветных кнопок, Bot API 9.4+)
    messages.py    — все тексты (HTML), settings_text(), MODE_INFO, константы ошибок
scripts/sync_skills.py — заливка skills из GitHub-репозиториев в БД
migrations/        — Alembic
```

**Стек:** aiogram 3.28, SQLAlchemy 2 async, asyncpg, Groq SDK (LLM + Whisper STT),
aiohttp (health/webhook), rank-bm25 (skills), Alembic, ffmpeg (чанкинг/видео).

---

## 3. Ключевые технические решения

- **`parse_mode=None` у бота по умолчанию** (`create_bot`). Сырой вывод LLM может
  содержать `<`, `&`, `*` — как HTML/Markdown не парсится. Поэтому:
  - **результат** экранируется `escape_html` и кладётся в `<blockquote><code>…</code></blockquote>`
    с явным `parse_mode="HTML"` → цитата + тап-чтобы-скопировать;
  - готовые **текстовые константы** с HTML-тегами шлются с явным `parse_mode="HTML"`;
  - транскрипт/прогресс — plain.
- **Доставка ответа** (`_reply.py:send_result`): прогресс-сообщение
  («✨ Полирую…») редактируется в финальный результат. Длинное (>3500 симв.)
  бьётся по границам абзац→предложение; >10 частей → весь ответ файлом `.txt`.
  **Стриминг-превью `sendMessageDraft` УБРАН** (см. грабли). `on_delta` в сервисах
  оставлен (default `None`) на будущее.
- **Источник медиа** (`voice.py`): фильтр `_HAS_MEDIA | _REPLY_HAS_MEDIA`,
  `_pick_media()` берёт из самого сообщения (прямое/форвард) или из
  `reply_to_message`. Видео/кружки → ffmpeg извлекает аудио (`extract_audio_from_video`).
- **Чанкинг длинных голосовых**: ≤ `chunk_threshold_sec` (600) — один запрос с кэшем;
  длиннее — `split_audio_to_chunks` (ffmpeg segment muxer, ogg/opus 64k), каждый кусок
  транскрибируется по очереди с паузой `chunk_throttle_sec`, потом склейка. Кэш только
  на single-shot пути.
- **Кэш транскрипции** по `file_id` (`transcription_cache`). `force_retranscribe=True`
  удаляет запись и гонит Whisper заново.
- **Кнопка «Повтор»** (`action:regenerate`): полный свежий прогон последнего запроса —
  для голоса `force_retranscribe=True` (сброс кэша → свежий Whisper) + свежая генерация
  LLM. Последний запрос держим в памяти процесса (`_last.py`, `LastRequest` по
  `telegram_user_id`); ядро вынесено в `_process_media`/`_process_text`, их же зовут
  `regenerate_voice`/`regenerate_text`. После рестарта стор пуст — «Повтор» просит
  прислать заново.
- **Whisper = `whisper-large-v3` (НЕ turbo).** Осознанно: качество распознавания
  важнее скорости. turbo быстрее, но хуже на сложной речи/акцентах/матах.
  **Не менять на turbo без явной просьбы владельца.**
- **Снаппи-кнопки**: callback-хендлеры зовут `callback.answer()` сразу (до DB/edit),
  чтобы спиннер на кнопке гас мгновенно.
- **Groq retry**: до 3 попыток, паузы 2с/4с; при 429 ротация по всем ключам из
  `get_all_groq_keys()` — и в LLM (`complete`), и в STT (`transcribe`).
- **coder_strict / gpt-oss-120b** — reasoning-модель: нужны
  `reasoning_effort` + `reasoning_format="hidden"` + `max_completion_tokens`,
  иначе пустой `content`.
- **БД-пул** (`db.py`): pool_size=5, max_overflow=5, pool_pre_ping, pool_recycle=300,
  `statement_cache_size=0` (совместимость с PgBouncer Supabase/Neon).
- **Бан**: `users.is_blocked`; `AuthMiddleware` проверяет (своя сессия), админов забанить нельзя.

---

## 4. ⚠️ Грабли и подводные камни (institutional memory)

Сюда пишем то, что уже сломалось/удивило — чтобы не наступать второй раз.

1. **`sendMessageDraft` оставляет «осиротевшие» пустые пузыри.** По API эфемерный
   драфт нужно финализировать **новым** `SendMessage`, а мы редактировали другое
   (прогресс-) сообщение. В чате висели полупустые превью-бабблы («большое пустое
   место»). → Стриминг-превью удалён, доставка через edit прогресс-сообщения.
2. **`TelegramConflictError` = полная тишина бота.** Если у бота зарегистрирован
   вебхук (остался с прошлого деплоя), Telegram отклоняет `getUpdates` →
   polling не получает апдейты, бот «молчит». → В `main.py` перед `start_polling`
   обязательно `bot.delete_webhook(drop_pending_updates=False)`.
3. **main НЕ обновлялся, а Render деплоит с main.** Фиксы лежали в **draft-PR** и не
   были смержены → прод крутил старый сломанный код. Урок: **доводить PR до merge в
   main** (см. раздел 6). Render не видит ветки-PR.
4. **HTML-копи-блок ломается без экранирования.** Если результат с `<`/`&` сунуть в
   `<code>` без `escape_html` и `parse_mode="HTML"` — Telegram вернёт ошибку парсинга
   или пустоту. Всегда `escape_html` перед HTML.
5. **Пустой транскрипт нельзя кормить в LLM.** Тихий/неразборчивый голос → Whisper даёт
   пустую строку → polish отвечал «вы не предоставили текст для транскрибации». →
   Проверяем `transcript.strip()`, показываем `EMPTY_TRANSCRIPT`.
6. **Нельзя редактировать сообщение в пустой текст** — Telegram отклоняет. `send_result`
   на пустом результате показывает явную ошибку, а не пустоту.
7. **Whisper turbo деградирует качество.** Ставил turbo ради скорости — владелец
   откатил. Качество > скорость. См. решение в разделе 3.
8. **Кнопка «Повтор» была фейковой** — просто писала «отправь ещё раз». Стала реальным
   прогоном с `force_retranscribe`.
9. **Цветные кнопки `style=`** требуют aiogram ≥ 3.21 (Bot API 9.4+). Стоит 3.28.
10. **csv.field_size_limit** — парсер `awesome-chatgpt-prompts` падал на больших полях.
11. **Авто-мерж git оставляет дубликаты.** При `git merge origin/main` авто-склейка
    задублировала `admin_user_keyboard` и `OnDelta`. → После мержа проверять
    авто-смерженные файлы на дубли/битость.
12. **Чистый diff PR после squash-merge.** squash меняет SHA main, но **дерево то же**.
    Чтобы новый PR показывал только новые изменения, новую ветку ре-рутим на
    `origin/main` (деревья идентичны — `git checkout -B <branch> origin/main`).
13. **Промпт-инъекция** (PR #6) — пользовательский ввод не должен влиять на системный
    промпт; обёрнут в `<user_input>…</user_input>`.

---

## 5. Тесты и проверки

```bash
ruff check . && ruff format --check .            # линт/формат
python -m pytest tests/ -q                       # 69 тестов
python -c "from src.bot import create_dispatcher; create_dispatcher()"  # сборка без циклов
```

Покрыто: чанкинг/видео/реплай-голос (`test_voice_chunking`), копи-формат
(`test_reply_format`), «Повтор» с cache-bust (`test_regenerate`), TTL-очистка
(`test_cleanup`), промпты, skills, edge-cases, config.

> ⚠️ В CI репозитория **нет автотестов** (`get_check_runs` → 0). Прогоняем
> локально перед мержем.

---

## 6. 🔄 Рабочий процесс и деплой

**Деплой:** Render (free tier), long-polling. Деплоит **с ветки `main`**.
Keep-alive: внешний пингер (cron-job.org/UptimeRobot) дёргает `/health` каждые 10 мин
(+ есть self-ping в webhook-режиме). БД — Supabase (session pooler, порт 5432).
При старте автоматически: `alembic upgrade head` + `python scripts/sync_skills.py`.

**Опциональный webhook-режим:** если задан `WEBHOOK_URL` — бот поднимает aiohttp +
`set_webhook`; иначе (по умолчанию) — polling с предварительным `delete_webhook`.

**Как агент ведёт работу (ВАЖНО):**

1. Разработка в отдельной ветке (`claude/...`), коммиты с понятными сообщениями.
2. Открывается **draft-PR** в `main`.
3. **Агент сам прогоняет тесты/линт, сам помечает PR ready и САМ МЕРЖИТ его в `main`**
   (squash). CI в репо нет — ждать нечего. После мержа Render автоматически
   передеплоивает прод.
4. Если возникает конфликт мержа — агент ресолвит (в пользу актуальной ветки),
   чистит дубликаты от авто-склейки, прогоняет тесты, мержит.

> То есть: **новые изменения попадают в прод только после merge в `main`, и этот
> merge делает сам агент.** Не оставлять фиксы висеть в draft — это уже один раз
> привело к простою прода (грабли №3).

---

## 7. Переменные окружения

```
TELEGRAM_BOT_TOKEN=        # обязателен
GROQ_API_KEY_FALLBACK=     # общий ключ; или отдельные groq_api_key_<mode>
DATABASE_URL=              # postgresql+asyncpg://...
ADMIN_USER_IDS=            # твой telegram user_id, через запятую
ALLOWED_USER_IDS=          # пусто = открыт всем, список = только они
# опционально:
WEBHOOK_URL=               # если задан → webhook-режим вместо polling
WEBHOOK_SECRET=
# модели/лимиты/TTL берутся из config.py (есть дефолты)
```

---

## 8. Команды разработки

```bash
docker compose up --build          # локально с postgres
alembic upgrade head               # применить миграции
python scripts/sync_skills.py      # залить skills в БД
python -m src.main                 # запустить бота
```

---

## 9. Команды бота (для админа)

- `/stats` — юзеры, запросы, активные за 7 дней, режимы
- `/users` — список пользователей (username, кол-во запросов, активность, статус)
- `/user <id>` — карточка + inline-кнопки бан/разбан
- `/ban <id>` / `/unban <id>` — по telegram_id
- `/sync_skills` — перезалить skills из GitHub
- `/history` — последние 10 запросов

Пользовательские: `/start`, `/help`, `/modes`, `/settings`, `/lang <код>`, `/history`.

---

## 10. История изменений (по PR)

- **#1** — первичная реализация бота.
- **#5/#6** — security-аудит; фикс indirect prompt injection.
- **#7** — Supabase-ready пул, non-root Docker, атомарный upsert, защита от огромных файлов.
- **#9** (`2833c20`) — стриминг, фикс coder_strict, дизайнерские skills (Taste-Skill,
  Impeccable), фикс csv.field_size_limit, админ-дашборд (/users, /ban…).
- **#10** (`5544556`) — консолидация фич ветки devin + фикс прода:
  delete_webhook перед polling (фикс `TelegramConflictError`), UI «✦ VOICE ✦»,
  режим Summary + стиль «Сырой», whisper-large-v3, чанкинг до 1 часа, видео-кружки,
  опциональный webhook, TTL-очистка БД, обработка пустого транскрипта.
- **#11** (`79c59e1`) — копируемый результат (`<blockquote><code>`), транскрипция
  пересланных/реплай-голосовых, снаппи-кнопки (`callback.answer()` first),
  *(временно ставил whisper turbo — откатил в #12)*, ротация Groq-ключей в LLM.
- **#12** (`703f3e3`) — рабочая кнопка «Повтор» (force_retranscribe + свежий прогон),
  возврат whisper-large-v3 (качество > скорость), вынос ядра в `_process_media`/`_process_text`.

---

## 11. Roadmap / планы

- [x] Промпт-инъекция закрыта (PR #6)
- [x] Supabase-ready DB pool, non-root Docker, атомарный upsert (PR #7)
- [x] Retry + ротация ключей для Groq (LLM и STT)
- [x] Разбивка длинных ответов / `.txt`-фолбэк
- [x] Кэш транскрипции + «Перетранскрибировать» / «Повтор» (force_retranscribe)
- [x] Активные юзеры за 7 дней в /stats
- [x] coder_strict (gpt-oss-120b) reasoning-параметры
- [x] Дизайнерские skills (Taste-Skill, Impeccable), фикс csv.field_size_limit
- [x] Админ-дашборд + бан через AuthMiddleware
- [x] Режим Summary + стиль Polish «Сырой»
- [x] Голосовые до 1 часа (чанкинг), видео-кружки/видео
- [x] Транскрипция пересланных и реплай-голосовых
- [x] Копируемый результат (цитата + тап-чтобы-скопировать)
- [x] Фикс webhook/polling-конфликта, опциональный webhook, TTL-очистка БД
- [ ] **Redis для rate-limit** при масштабировании >1 реплики (сейчас in-memory → не
      переживёт несколько реплик)
- [ ] **Стор последнего запроса в Redis/БД** — сейчас «Повтор» теряется при рестарте
- [ ] Полноценный корректный стриминг (через отдельный `SendMessage`, не draft)
- [ ] Webhook как основной режим (нужен стабильный публичный HTTPS)
