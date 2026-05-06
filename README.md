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

Для полного функционала — отдельный Groq ключ на каждый режим:

```
GROQ_API_KEY_POLISH=gsk_...
GROQ_API_KEY_PROMPT=gsk_...
GROQ_API_KEY_HUMANIZER=gsk_...
GROQ_API_KEY_TRANSLATOR=gsk_...
```

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
