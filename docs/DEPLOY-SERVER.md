# Вариант Б: свой сервер — установка и обслуживание

> Рантбук на каждый день. Внешних сервисов ноль: ни Supabase, ни Render.
> База — файл SQLite внутри docker-тома. Нужны только **токен бота** и
> **бесплатный ключ Groq**.

---

## 1. Первая установка

```bash
cd ~
git clone https://github.com/Itosyro/voice-bot.git
cd voice-bot
bash scripts/install-server.sh
```

Скрипт: проверит Docker и свободное место → спросит токен, ключ Groq, твой
`user_id` → создаст `.env` с правами 600 → соберёт образ → запустит контейнер
с автозапуском после перезагрузки сервера.

**Если репозиторий приватный** и `git clone` просит пароль:
- по SSH: `git clone git@github.com:Itosyro/voice-bot.git`
- или по HTTPS: вместо пароля вставить Personal Access Token
  (github.com/settings/tokens).

**Требования:** Docker + Compose (`docker compose version`), ~1.2 ГБ свободного
диска на сборку, ffmpeg внутри образа (ставить на хост не надо).

---

## 2. Команды на каждый день

| Что нужно | Команда |
|---|---|
| Посмотреть логи | `make logs` |
| Работает ли | `make status` |
| Перезапустить (подхватит правки `.env`) | `make restart` |
| Ввести ключи заново | `make reconfigure` |
| Обновиться с GitHub | `make update` |
| Сделать копию базы | `make backup` |
| Остановить | `make down` |
| Зайти внутрь контейнера | `make shell` |

Без `make` — то же через `docker compose -f docker-compose.server.yml …`.

---

## 3. Если что-то не так

### Указал не тот ключ Groq (или сменил токен бота)

```bash
nano .env          # поправить строку GROQ_API_KEY_FALLBACK= или TELEGRAM_BOT_TOKEN=
make restart       # ВАЖНО: обычный docker compose restart .env не перечитывает
```

Или заново, как при установке: `make reconfigure` (старый `.env` → `.env.bak`).

Проверить ключ, не трогая бота:

```bash
curl -s -H "Authorization: Bearer ТВОЙ_КЛЮЧ" https://api.groq.com/openai/v1/models | head -5
```

Список моделей — ключ живой. `invalid_api_key` — нет.

### Бот молчит

```bash
make logs
```

Что искать в логах:

| В логах | Что значит | Что делать |
|---|---|---|
| `llm_permanent_error` + 401 | неверный ключ Groq | см. пункт выше |
| `TelegramConflictError` | у бота остался вебхук с прошлого деплоя | `make restart` (бот сам удаляет вебхук на старте) |
| `TelegramUnauthorizedError` | неверный токен бота | поправить `.env` → `make restart` |
| `llm_model_unavailable` | провайдер отключил модель | обновиться: `make update` |
| `sqlite_schema_ready` | база в порядке | это норма при старте |
| `db_init_failed_starting_anyway` | база недоступна | бот всё равно работает, но без истории |

### Кончилось место на диске

```bash
df -h /                 # сколько свободно
docker system df        # сколько занял Docker
docker system prune -a  # удалить неиспользуемые образы (запущенные контейнеры не тронет)
```

### Контейнер не поднимается

```bash
docker compose -f docker-compose.server.yml logs --tail 50
docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' voice-bot
```

Старт спроектирован так, чтобы **не** уходить в restart-loop: падение миграций
или синка skills только пишет предупреждение. Если контейнер всё же падает —
почти всегда дело в `.env` (нет токена).

---

## 4. База данных

- Живёт в docker-томе `voicebot_data`, файл `/app/data/voicebot.db`.
- Схема создаётся автоматически при первом старте (`init_db`).
- Старые записи чистятся сами: кэш транскриптов — 7 дней, история — 30
  (настраивается в `config.py`).
- `make down` том **не** удаляет — данные переживают перезапуск и пересборку.

**Копия:**

```bash
make backup       # → backup-20260726-2130.db в папке проекта
```

**Восстановление:**

```bash
make down
docker run --rm -v voicebot_data:/data -v "$PWD":/backup alpine \
  sh -c "cp /backup/backup-20260726-2130.db /data/voicebot.db"
make up
```

**Удалить всё вместе с данными** (осторожно):

```bash
docker compose -f docker-compose.server.yml down -v
```

---

## 5. Соседство с другими проектами

Бот изолирован: отдельный контейнер `voice-bot`, свой том, лимиты **1 ГБ
памяти / 1.5 CPU**, ротация логов (3 файла × 10 МБ). На том же сервере спокойно
живут другие проекты — общего у них только Docker.

Лимиты меняются в `docker-compose.server.yml` (`mem_limit`, `cpus`).

---

## 6. Необязательные улучшения

Добавить в `.env` и сделать `make restart`:

```
OPENROUTER_API_KEY=   # голосовые длиннее ~25 минут (у Groq free лимит 8K токенов/мин)
CEREBRAS_API_KEY=     # запасной LLM: 1 млн токенов/день бесплатно, очень быстрый
ENABLE_DRAFT_STREAMING=true   # превью генерации на лету (включать после проверки)
```

Оба ключа бесплатные: openrouter.ai и cloud.cerebras.ai. Без них бот работает,
но очень длинные голосовые вернут честное «текст слишком длинный».

---

## 7. Обновления

```bash
cd ~/voice-bot
make update      # git pull + пересборка + перезапуск
```

Данные не теряются: том с базой не пересоздаётся. Если после обновления
что-то сломалось — откатиться на предыдущий коммит:

```bash
git log --oneline -5
git checkout <хеш-предыдущего>
make restart
```
