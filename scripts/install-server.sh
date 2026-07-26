#!/usr/bin/env bash
# Установка voice-bot на свой сервер одной командой.
#
#   bash scripts/install-server.sh
#
# Что делает: проверяет окружение и место на диске, создаёт .env (спросит
# токен и ключ), собирает образ и поднимает контейнер с автозапуском.
# Никаких внешних сервисов: база — файл SQLite внутри docker-тома.
set -euo pipefail

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$OFF" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$OFF" "$*"; }
die()  { printf '%s✗%s %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }

cd "$(dirname "$0")/.."
say "${BOLD}Установка Voice Polisher Bot на этот сервер${OFF}"
say ""

# ── 1. Docker ──
if ! command -v docker >/dev/null 2>&1; then
  die "Docker не найден. Поставь его: curl -fsSL https://get.docker.com | sh"
fi
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "Docker Compose не найден. Поставь плагин: apt install docker-compose-plugin"
fi
ok "Docker и Compose на месте"

# ── 2. Место на диске ──
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

# ── 3. .env ──
if [ -f .env ]; then
  ok ".env уже есть — оставляю как есть"
  say "  (перезаписать ключи: make reconfigure — или вручную nano .env)"
else
  say ""
  say "${BOLD}Настройка (2 обязательных значения)${OFF}"
  printf 'Токен бота от @BotFather: '
  read -r TG_TOKEN </dev/tty
  [ -n "$TG_TOKEN" ] || die "Токен обязателен."

  printf 'Ключ Groq (console.groq.com, бесплатный): '
  read -r GROQ_KEY </dev/tty
  [ -n "$GROQ_KEY" ] || die "Ключ Groq обязателен."

  printf 'Твой Telegram user_id (узнать: @userinfobot), можно пусто: '
  read -r ADMIN_ID </dev/tty

  printf 'Кому разрешён доступ — user_id через запятую (пусто = всем): '
  read -r ALLOWED_IDS </dev/tty

  cat > .env <<EOF
# Создан scripts/install-server.sh
TELEGRAM_BOT_TOKEN=$TG_TOKEN
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
fi

# ── 4. Сборка и запуск ──
say ""
say "${BOLD}Собираю образ (первый раз — несколько минут)${OFF}"
$COMPOSE -f docker-compose.server.yml build

say ""
say "${BOLD}Запускаю${OFF}"
$COMPOSE -f docker-compose.server.yml up -d --force-recreate

sleep 5
say ""
if [ "$(docker inspect -f '{{.State.Running}}' voice-bot 2>/dev/null)" = "true" ]; then
  ok "Бот запущен и будет подниматься сам после перезагрузки сервера"
else
  warn "Контейнер не поднялся — смотри логи ниже"
fi

say ""
say "${BOLD}Команды на каждый день${OFF}"
say "  Логи:       $COMPOSE -f docker-compose.server.yml logs -f"
say "  Перезапуск: $COMPOSE -f docker-compose.server.yml up -d --force-recreate"
say "  Стоп:       $COMPOSE -f docker-compose.server.yml down"
say "  Обновиться: git pull && $COMPOSE -f docker-compose.server.yml up -d --build"
say ""
say "Последние строки лога:"
$COMPOSE -f docker-compose.server.yml logs --tail 20
