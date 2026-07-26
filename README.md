# Voice Polisher Bot

Telegram-бот для обработки голосовых сообщений и текста с использованием Groq AI.

## Возможности

### 4 режима обработки

| Режим | Вход | Что делает |
|-------|------|------------|
| **Polish** | Голос / текст | Убирает слова-паразиты, расставляет пунктуацию, исправляет грамматику |
| **Prompt Engineer** | Голос / текст | Превращает идею в структурированный промпт для LLM |
| **Humanizer** | Только текст | Убирает признаки AI-генерации (em-dash, шаблонные фразы, идеальная структура) |
| **Translator** | Голос / текст | Перевод с сохранением тона (14 языков) |

### Подстили

- **Polish**: Default, Creative, Formal, Embellish
- **Prompt Engineer**: General, Designer, Coder, Coder Strict
- **Humanizer**: Lite, Strong
- **Translator**: EN, RU, ES, FR, DE, ZH, JA, KO, AR, TR, PT, IT, PL, UK

### Skills RAG

Режим Prompt Engineer использует BM25-поиск по 8 skill-репозиториям для обогащения промптов релевантными знаниями.

## Быстрый старт

### 1. Клонируй и настрой

```bash
git clone <repo-url>
cd voice-bot
cp .env.example .env
```

### 2. Заполни `.env`

Минимально необходимые переменные:

```
TELEGRAM_BOT_TOKEN=<от @BotFather>
GROQ_API_KEY_FALLBACK=<ключ с console.groq.com>
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/voicebot
```

Опционально — отдельный Groq ключ на каждый режим. ВАЖНО: лимиты Groq
считаются на организацию, поэтому смысл в отдельных ключах есть только если
это ключи **разных** аккаунтов Groq:

```
GROQ_API_KEY_POLISH=gsk_...
GROQ_API_KEY_PROMPT=gsk_...
GROQ_API_KEY_HUMANIZER=gsk_...
GROQ_API_KEY_TRANSLATOR=gsk_...
GROQ_API_KEY_SUMMARY=gsk_...
```

## 🚀 Вариант Б: свой сервер (рекомендуется)

Никаких внешних сервисов: ни Supabase, ни Render. База — файл SQLite внутри
docker-тома, нужен только **токен бота** и **бесплатный ключ Groq**.

```bash
git clone https://github.com/Itosyro/voice-bot.git
cd voice-bot
bash scripts/install-server.sh
```

Скрипт проверит Docker и место на диске, спросит токен и ключ, соберёт образ
и поднимет контейнер с автозапуском после перезагрузки сервера.

**Команды на каждый день** (из папки проекта):

| Что | Команда |
|---|---|
| Логи | `make logs` |
| Статус | `make status` |
| Перезапуск (подхватит новый `.env`) | `make restart` |
| Переписать ключи заново | `make reconfigure` |
| Обновиться с GitHub | `make update` |
| Бэкап базы | `make backup` |
| Остановить | `make down` |

Без `make` — то же самое через `docker compose -f docker-compose.server.yml …`.

**Сколько занимает:** образ ~600 МБ, база растёт медленно (TTL чистит старое
автоматически). Если места мало — `docker system prune -a` освободит
неиспользуемые образы.

---

### 3. Запусти через Docker

```bash
docker compose up --build
```

Бот автоматически:
1. Поднимет PostgreSQL
2. Применит миграции (`alembic upgrade head`)
3. Синхронизирует skills из 8 репозиториев
4. Запустит polling

### Альтернатива: локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Postgres должен быть запущен
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/voicebot
alembic upgrade head
python scripts/sync_skills.py
python -m src.main
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие + выбор режима |
| `/help` | Справка |
| `/modes` | Выбор режима |
| `/settings` | Настройки |
| `/lang <код>` | Сменить язык перевода |
| `/history` | Последние 10 запросов |
| `/cancel` | Отменить действие |
| `/sync_skills` | Синхронизировать skills (admin) |
| `/stats` | Статистика (admin) |

## Получение ключей

### Telegram Bot Token
1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. `/newbot` → следуй инструкциям
3. Скопируй токен

### Groq API Keys
1. Зарегистрируйся на [console.groq.com](https://console.groq.com)
2. Создай 4 API ключа (один на каждый режим)
3. Бесплатный тир включает достаточно запросов

## Стек

- **Python 3.11+**, aiogram 3
- **Groq API** (Whisper + LLM)
- **PostgreSQL 16** + SQLAlchemy 2.0 + Alembic
- **BM25** для skills search
- **Docker Compose** для деплоя

## Ограничения

- Аудио до 10 минут
- Текст до 10000 символов
- 20 запросов в минуту на пользователя
- Humanizer работает только с текстом (не голосом)
- Зависит от Groq API (бесплатный тир имеет rate limits)

## Деплой

### Fly.io

```bash
fly auth login
fly launch --config fly.toml
fly secrets set TELEGRAM_BOT_TOKEN=... GROQ_API_KEY_FALLBACK=...
fly deploy
```

### Railway

Подключи GitHub репозиторий, добавь PostgreSQL addon, задай env variables.

## Лицензия

MIT
