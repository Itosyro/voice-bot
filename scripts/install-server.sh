#!/usr/bin/env bash
# Установка voice-bot на свой сервер одной командой — и переезд на новый сервер.
#
#   bash scripts/install-server.sh                          # первичная установка (спросит ключи)
#   bash scripts/install-server.sh --restore архив.tar.gz    # переезд из скачанного архива
#   curl -fsSL <raw-url>/scripts/install-server.sh | TG_TOKEN=<токен> bash -s -- --tg <FILE_ID>
#                                                           # переезд: архив заберём из Telegram
#
# Что делает: при запуске вне репозитория ставит git/curl/make/Docker и клонирует
# проект; создаёт (или восстанавливает) .env, кладёт базу в docker-том, собирает
# образ и поднимает контейнер с автозапуском.
# Никаких внешних сервисов: база — файл SQLite внутри docker-тома.
set -euo pipefail

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$OFF" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$OFF" "$*"; }
die()  { printf '%s✗%s %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }

REPO_URL="https://github.com/Itosyro/voice-bot.git"
REPO_DIR="${HOME:-/root}/voice-bot"
COMPOSE_FILE="docker-compose.server.yml"

usage() {
  say "Использование:"
  say "  bash scripts/install-server.sh                        первичная установка"
  say "  bash scripts/install-server.sh --restore ФАЙЛ.tar.gz  переезд из архива"
  say "  ... | TG_TOKEN=токен bash -s -- --tg FILE_ID          переезд: архив из Telegram"
}

# ── Аргументы ──
MODE=install; TG_TOKEN="${TG_TOKEN:-}"; TG_FILE_ID=""; ARCHIVE=""
parse_args() {
  MODE=install; TG_FILE_ID=""; ARCHIVE=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --tg)
        MODE=tg
        # Токен — из окружения (TG_TOKEN=… перед bash): в argv его видно всем
        # локальным пользователям через ps. Старая форма «--tg ТОКЕН FILE_ID» тоже
        # принимается — вдруг команда сохранилась со старого сервера.
        if [ $# -ge 3 ]; then
          TG_TOKEN="$2"; TG_FILE_ID="$3"; shift 3
        else
          [ $# -ge 2 ] || { usage; die "--tg требует FILE_ID"; }
          TG_FILE_ID="$2"; shift 2
        fi
        [ -n "$TG_TOKEN" ] || die \
          "Нет токена бота. Запусти так: TG_TOKEN=<токен> bash -s -- --tg <FILE_ID>" ;;
      --restore)
        [ $# -ge 2 ] || { usage; die "--restore требует путь к архиву"; }
        MODE=restore; ARCHIVE="$2"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) usage; die "Неизвестный аргумент: $1" ;;
    esac
  done
  # Дальше мы перейдём в папку проекта — относительный путь к архиву потеряется.
  case "$ARCHIVE" in ""|/*) ;; *) ARCHIVE="$PWD/$ARCHIVE" ;; esac
}

# ── Репозиторий: работаем изнутри проекта, иначе поднимаем его с нуля ──
bootstrap() {
  say "${BOLD}Готовлю чистый сервер${OFF}"
  command -v apt-get >/dev/null 2>&1 || die \
    "Автоустановка есть только для Debian/Ubuntu. Поставь git, curl, make и Docker сам, потом:
  git clone $REPO_URL && cd voice-bot && bash scripts/install-server.sh"
  [ "$(id -u)" = "0" ] || die "Запусти под root (например: sudo -i, затем повтори команду)."

  MISSING=""
  for tool in git curl make; do
    command -v "$tool" >/dev/null 2>&1 || MISSING="$MISSING $tool"
  done
  if [ -n "$MISSING" ]; then
    say "Ставлю пакеты:$MISSING"
    apt-get update -qq
    # shellcheck disable=SC2086  # список пакетов обязан разбиться на слова
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates $MISSING
    ok "Пакеты установлены"
  fi

  if [ -d "$REPO_DIR/.git" ]; then
    say "Репозиторий уже есть — обновляю"
    git -C "$REPO_DIR" pull --ff-only || warn "git pull не прошёл — работаю с текущим кодом"
  else
    say "Клонирую $REPO_URL → $REPO_DIR"
    git clone --depth 1 "$REPO_URL" "$REPO_DIR"
  fi
  cd "$REPO_DIR"
  ok "Проект: $REPO_DIR"
}

enter_repo() {
  SELF_DIR=$(cd -- "$(dirname -- "$0")" 2>/dev/null && pwd || true)
  if [ -n "$SELF_DIR" ] && [ -f "$SELF_DIR/install-server.sh" ] && [ -f "$SELF_DIR/../$COMPOSE_FILE" ]
  then
    cd "$SELF_DIR/.."          # запуск из репозитория: bash scripts/install-server.sh
  elif [ -f "$COMPOSE_FILE" ]; then
    :                          # уже в корне проекта
  else
    bootstrap                  # запуск через curl | bash на голом сервере
  fi
}

ensure_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = "0" ] || die \
      "Docker не найден. Поставь его: curl -fsSL https://get.docker.com | sh"
    say "Ставлю Docker (официальный скрипт get.docker.com)…"
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker >/dev/null 2>&1 || true
  fi
  if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose"
  else
    die "Docker Compose не найден. Поставь плагин: apt install docker-compose-plugin"
  fi
  ok "Docker и Compose на месте"
}

check_disk() {
  FREE_MB=$(df -Pm . | awk 'NR==2 {print $4}')
  say "Свободно на диске: ${FREE_MB} МБ"
  if [ "$FREE_MB" -lt 1200 ]; then
    warn "Меньше 1.2 ГБ свободно — сборка образа может не влезть."
    warn "Освободить место: docker system prune -a  (удалит неиспользуемые образы)"
    printf 'Продолжить всё равно? [y/N] '
    read -r answer </dev/tty
    [ "$answer" = "y" ] || [ "$answer" = "Y" ] || die "Отменено."
  else
    ok "Места достаточно"
  fi
}

# ── .env: спросить ключи (первичная установка) ──
create_env_interactive() {
  if [ -f .env ]; then
    ok ".env уже есть — оставляю как есть"
    say "  (перезаписать ключи: make reconfigure — или вручную nano .env)"
    return
  fi
  say ""
  say "${BOLD}Настройка (2 обязательных значения)${OFF}"
  printf 'Токен бота от @BotFather: '
  read -r TG_BOT_TOKEN </dev/tty
  [ -n "$TG_BOT_TOKEN" ] || die "Токен обязателен."

  printf 'Ключ Groq (console.groq.com, бесплатный): '
  read -r GROQ_KEY </dev/tty
  [ -n "$GROQ_KEY" ] || die "Ключ Groq обязателен."

  printf 'Твой Telegram user_id (узнать: @userinfobot), можно пусто: '
  read -r ADMIN_ID </dev/tty

  printf 'Кому разрешён доступ — user_id через запятую (пусто = всем): '
  read -r ALLOWED_IDS </dev/tty

  cat > .env <<EOF
# Создан scripts/install-server.sh
TELEGRAM_BOT_TOKEN=$TG_BOT_TOKEN
GROQ_API_KEY_FALLBACK=$GROQ_KEY
ADMIN_USER_IDS=$ADMIN_ID
ALLOWED_USER_IDS=$ALLOWED_IDS

# База — файл внутри docker-тома, ничего подключать не надо.
# (Значение подставляет docker-compose.server.yml.)

# Необязательно: запасные бесплатные LLM-провайдеры.
# OPENROUTER_API_KEY нужен для голосовых длиннее ~25 минут.
CEREBRAS_API_KEY=
OPENROUTER_API_KEY=
EOF
  chmod 600 .env
  ok ".env создан (права 600)"
}

# ── Переезд: скачать архив из Telegram по file_id ──
tg_download() {
  say "Скачиваю архив из Telegram…"
  RESP=$(curl -fsS "https://api.telegram.org/bot$TG_TOKEN/getFile?file_id=$TG_FILE_ID") \
    || die "Telegram не ответил. Проверь токен бота и file_id."
  # jq на свежем сервере нет — вытаскиваем "file_path":"documents/file_0.tar.gz" руками.
  FILE_PATH=$(printf '%s' "$RESP" | grep -o '"file_path":"[^"]*"' | sed 's/.*:"//; s/"$//') \
    || FILE_PATH=""
  [ -n "$FILE_PATH" ] || die "Telegram не отдал file_path (файл больше 20 МБ или истёк). Ответ: $RESP"
  ARCHIVE="$(mktemp -d)/migration.tar.gz"
  curl -fsSL "https://api.telegram.org/file/bot$TG_TOKEN/$FILE_PATH" -o "$ARCHIVE" \
    || die "Архив не скачался."
  ok "Архив скачан: $(wc -c < "$ARCHIVE") байт"
}

# ── Переезд: .env из архива на диск, базу — во временную папку под том ──
RESTORE_DIR=""; DB_BYTES=0; ENV_BACKED_UP=no
restore_env_and_stage_db() {
  [ -f "$ARCHIVE" ] || die "Файл архива не найден: $ARCHIVE"
  RESTORE_DIR=$(mktemp -d)
  tar -xzf "$ARCHIVE" -C "$RESTORE_DIR" || die "Архив не распаковался (битый файл?)."
  [ -f "$RESTORE_DIR/.env" ] || die "В архиве нет .env — это не архив переезда."
  [ -f "$RESTORE_DIR/voicebot.db" ] || die "В архиве нет voicebot.db — это не архив переезда."

  if [ -f .env ]; then
    cp .env .env.bak
    ENV_BACKED_UP=yes
    warn "Старый .env сохранён как .env.bak"
  fi
  cp "$RESTORE_DIR/.env" .env
  chmod 600 .env
  rm -f "$RESTORE_DIR/.env"   # в общей папке секретам делать нечего
  ok ".env восстановлен (права 600)"

  DB_BYTES=$(wc -c < "$RESTORE_DIR/voicebot.db")
  # Контейнер работает под uid 1000 — папку mktemp (700, root) он бы не прочитал.
  chmod 755 "$RESTORE_DIR"
  chmod 644 "$RESTORE_DIR/voicebot.db"
}

# ── Переезд: положить базу в том ДО старта бота ──
restore_db_into_volume() {
  say "Кладу базу в том (имя тома берётся из compose, руками не задаём)…"
  $COMPOSE -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh \
    -v "$RESTORE_DIR:/restore:ro" bot -c \
    'cp /restore/voicebot.db /app/data/voicebot.db && rm -f /app/data/voicebot.db-wal /app/data/voicebot.db-shm' \
    || die "Не удалось записать базу в том. Вручную:
  $COMPOSE -f $COMPOSE_FILE up -d
  docker cp $RESTORE_DIR/voicebot.db voice-bot:/app/data/voicebot.db
  docker exec -u 0 voice-bot chown 1000:1000 /app/data/voicebot.db
  $COMPOSE -f $COMPOSE_FILE restart"
  ok "База восстановлена: $DB_BYTES байт"
}

# ── Основной сценарий ──
parse_args "$@"
enter_repo

if [ "$MODE" = "install" ]; then
  say "${BOLD}Установка Voice Polisher Bot на этот сервер${OFF}"
else
  say "${BOLD}Переезд Voice Polisher Bot на этот сервер${OFF}"
fi
say ""

ensure_docker
check_disk

case "$MODE" in
  install) create_env_interactive ;;
  tg)      tg_download; restore_env_and_stage_db ;;
  restore) restore_env_and_stage_db ;;
esac

say ""
say "${BOLD}Собираю образ (первый раз — несколько минут)${OFF}"
$COMPOSE -f "$COMPOSE_FILE" build

if [ "$MODE" != "install" ]; then
  say ""
  restore_db_into_volume
fi

say ""
say "${BOLD}Запускаю${OFF}"
$COMPOSE -f "$COMPOSE_FILE" up -d --force-recreate

sleep 5
say ""
if [ "$(docker inspect -f '{{.State.Running}}' voice-bot 2>/dev/null)" = "true" ]; then
  ok "Бот запущен и будет подниматься сам после перезагрузки сервера"
else
  warn "Контейнер не поднялся — смотри логи ниже"
fi

if [ "$MODE" != "install" ]; then
  say ""
  say "${BOLD}Итог переезда${OFF}"
  if [ "$ENV_BACKED_UP" = yes ]; then
    say "  .env: восстановлен из архива (прежний сохранён как .env.bak)"
  else
    say "  .env: восстановлен из архива"
  fi
  say "  База: восстановлена, $DB_BYTES байт (skills пересобираются на старте сами)"
  say "  Дальше: проверь бота в Telegram, потом удали архив из чата (в нём ключи)"
  say "          и погаси старый сервер."
fi

say ""
say "${BOLD}Команды на каждый день${OFF}"
say "  Логи:       $COMPOSE -f $COMPOSE_FILE logs -f"
say "  Перезапуск: $COMPOSE -f $COMPOSE_FILE up -d --force-recreate"
say "  Стоп:       $COMPOSE -f $COMPOSE_FILE down"
say "  Обновиться: git pull && $COMPOSE -f $COMPOSE_FILE up -d --build"
say "  Переезд:    /migrate в личке с ботом (или make migrate)"
say ""
say "Последние строки лога:"
$COMPOSE -f "$COMPOSE_FILE" logs --tail 20
