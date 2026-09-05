#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-v2.1"
PAYLOAD_REF="39ac7fc2299d7725d64986412e8d0c6c3d91ae17"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/ai-home-v2"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"
SOURCE_DIR="${DVIZH_AI_HOME_V2_SOURCE_DIR:-}"

if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 1
fi

if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT="/opt/dvizh"
else
  echo "Не найден веб-интерфейс ДВИЖа." >&2
  exit 1
fi

INDEX="$APP_ROOT/index.html"
MANUAL="$APP_ROOT/manual.html"
APP_JS="$APP_ROOT/app.js"
APP_CSS="$APP_ROOT/styles.css"
SW="$APP_ROOT/sw.js"
AI_JS="$APP_ROOT/ai-home-v2.js"
AI_CSS="$APP_ROOT/ai-home-v2.css"

for required in "$INDEX" "$APP_JS" "$APP_CSS" "$SW"; do
  [[ -f "$required" ]] || { echo "Не найден обязательный файл: $required" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-v2.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

get_payload() {
  local name="$1"
  if [[ -n "$SOURCE_DIR" ]]; then
    cp "$SOURCE_DIR/$name" "$TMP_DIR/$name"
  else
    curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
      "$BASE_URL/$name" -o "$TMP_DIR/$name"
  fi
}

get_payload index.html
get_payload ai-home-v2.js
get_payload ai-home-v2.css

grep -q 'ai-home-v2.js?v=20260905-1' "$TMP_DIR/index.html"
grep -q 'ai-home-v2.css?v=20260905-1' "$TMP_DIR/index.html"
grep -q "const API = '/api/state';" "$TMP_DIR/ai-home-v2.js"
grep -q "location.assign('/manual.html')" "$TMP_DIR/ai-home-v2.js"
if grep -qE 'MutationObserver|setInterval\(' "$TMP_DIR/ai-home-v2.js"; then
  echo "AI Home v2 содержит запрещённый постоянный DOM-цикл." >&2
  exit 1
fi
if command -v node >/dev/null 2>&1; then
  node --check "$TMP_DIR/ai-home-v2.js" >/dev/null
fi

if [[ -z "$TEST_ROOT" ]]; then
  systemctl is-active --quiet dvizh.service || { echo "dvizh.service не активен" >&2; exit 1; }
  systemctl is-active --quiet dvizh-auth.service || { echo "dvizh-auth.service не активен" >&2; exit 1; }
  systemctl is-active --quiet dvizh-ai-home.service || { echo "dvizh-ai-home.service не активен" >&2; exit 1; }
  curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
fi

if [[ -z "$TEST_ROOT" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_DIR="/var/lib/dvizh/backups/ai-home-v2-$STAMP"
  install -d -o root -g root -m 0700 "$BACKUP_DIR"
else
  BACKUP_DIR="$APP_ROOT/.ai-home-v2-backup"
  mkdir -p "$BACKUP_DIR"
fi

cp -a "$INDEX" "$BACKUP_DIR/index.html"
cp -a "$APP_JS" "$BACKUP_DIR/app.js"
cp -a "$APP_CSS" "$BACKUP_DIR/styles.css"
cp -a "$SW" "$BACKUP_DIR/sw.js"
[[ -f "$MANUAL" ]] && cp -a "$MANUAL" "$BACKUP_DIR/manual.html"
[[ -f "$AI_JS" ]] && cp -a "$AI_JS" "$BACKUP_DIR/ai-home-v2.js"
[[ -f "$AI_CSS" ]] && cp -a "$AI_CSS" "$BACKUP_DIR/ai-home-v2.css"

# First install: the currently stable root becomes the full manual interface.
# Re-running v2 never overwrites manual.html with the AI-only root.
if ! grep -q 'ai-home-v2.js?v=20260905-1' "$INDEX"; then
  cp -a "$INDEX" "$MANUAL"
elif [[ ! -f "$MANUAL" ]]; then
  echo "AI Home v2 уже стоит, но manual.html отсутствует. Останавливаюсь безопасно." >&2
  exit 1
fi

if [[ -n "$TEST_ROOT" ]]; then
  cp "$TMP_DIR/index.html" "$INDEX"
  cp "$TMP_DIR/ai-home-v2.js" "$AI_JS"
  cp "$TMP_DIR/ai-home-v2.css" "$AI_CSS"
  chmod 0644 "$INDEX" "$AI_JS" "$AI_CSS"
else
  install -m 0644 -o root -g root "$TMP_DIR/index.html" "$INDEX"
  install -m 0644 -o root -g root "$TMP_DIR/ai-home-v2.js" "$AI_JS"
  install -m 0644 -o root -g root "$TMP_DIR/ai-home-v2.css" "$AI_CSS"
fi

# Invariants: the old application bundle remains byte-for-byte untouched.
cmp -s "$APP_JS" "$BACKUP_DIR/app.js" || { echo "app.js неожиданно изменился" >&2; exit 1; }
cmp -s "$APP_CSS" "$BACKUP_DIR/styles.css" || { echo "styles.css неожиданно изменился" >&2; exit 1; }
cmp -s "$SW" "$BACKUP_DIR/sw.js" || { echo "sw.js неожиданно изменился" >&2; exit 1; }
grep -q 'ai-home-v2.js?v=20260905-1' "$INDEX"
grep -q 'Напиши или скажи' "$INDEX"
[[ -s "$MANUAL" ]]

if [[ -z "$TEST_ROOT" ]]; then
  systemctl is-active --quiet dvizh.service
  systemctl is-active --quiet dvizh-ai-home.service
fi

echo
echo "DVIZH AI Home v2 installed: $VERSION"
echo "Backup: $BACKUP_DIR"
echo "Главная / теперь полностью изолирована от старого app.js."
echo "Полный старый интерфейс сохранён: /manual.html"
echo "Hermes bridge не перезапускался и базы не изменялись."
echo "Скрытый выход в ручной режим: удерживай AI-орб ~1 секунду или введи /manual."
