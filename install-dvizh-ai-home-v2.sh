#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-v2.2"
MODE="${DVIZH_AI_HOME_V2_MODE:-preview}"
PAYLOAD_REF="1bba0cf27c76caaa2c725bc29df3873359844e60"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/ai-home-v2"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"
SOURCE_DIR="${DVIZH_AI_HOME_V2_SOURCE_DIR:-}"

case "$MODE" in
  preview|promote) ;;
  *)
    echo "DVIZH_AI_HOME_V2_MODE должен быть preview или promote." >&2
    exit 1
    ;;
esac

if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через sudo. По умолчанию установится только preview, без замены главной." >&2
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
PREVIEW="$APP_ROOT/ai-home-v2-preview.html"
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

put_file() {
  local source="$1"
  local target="$2"
  if [[ -n "$TEST_ROOT" ]]; then
    cp "$source" "$target"
    chmod 0644 "$target"
  else
    install -m 0644 -o root -g root "$source" "$target"
  fi
}

get_payload index.html
get_payload ai-home-v2.js
get_payload ai-home-v2.css

grep -q 'ai-home-v2.js?v=20260905-2' "$TMP_DIR/index.html"
grep -q 'ai-home-v2.css?v=20260905-2' "$TMP_DIR/index.html"
grep -q "const API = '/api/state';" "$TMP_DIR/ai-home-v2.js"
grep -q "return promoted ? '/manual.html' : '/';" "$TMP_DIR/ai-home-v2.js"
if grep -qE 'MutationObserver|setInterval\(|serviceWorker|caches\.' "$TMP_DIR/ai-home-v2.js"; then
  echo "AI Home v2 содержит запрещённое вмешательство в основной frontend/runtime." >&2
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
  BACKUP_DIR="/var/lib/dvizh/backups/ai-home-v2-${MODE}-$STAMP"
  install -d -o root -g root -m 0700 "$BACKUP_DIR"
else
  BACKUP_DIR="$APP_ROOT/.ai-home-v2-${MODE}-backup"
  rm -rf "$BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"
fi

cp -a "$INDEX" "$BACKUP_DIR/index.html"
cp -a "$APP_JS" "$BACKUP_DIR/app.js"
cp -a "$APP_CSS" "$BACKUP_DIR/styles.css"
cp -a "$SW" "$BACKUP_DIR/sw.js"
[[ -f "$MANUAL" ]] && cp -a "$MANUAL" "$BACKUP_DIR/manual.html"
[[ -f "$PREVIEW" ]] && cp -a "$PREVIEW" "$BACKUP_DIR/ai-home-v2-preview.html"
[[ -f "$AI_JS" ]] && cp -a "$AI_JS" "$BACKUP_DIR/ai-home-v2.js"
[[ -f "$AI_CSS" ]] && cp -a "$AI_CSS" "$BACKUP_DIR/ai-home-v2.css"

if [[ "$MODE" == "preview" ]]; then
  put_file "$TMP_DIR/index.html" "$PREVIEW"
  put_file "$TMP_DIR/ai-home-v2.js" "$AI_JS"
  put_file "$TMP_DIR/ai-home-v2.css" "$AI_CSS"

  cmp -s "$INDEX" "$BACKUP_DIR/index.html" || { echo "Preview неожиданно изменил index.html" >&2; exit 1; }
  cmp -s "$APP_JS" "$BACKUP_DIR/app.js" || { echo "Preview неожиданно изменил app.js" >&2; exit 1; }
  cmp -s "$APP_CSS" "$BACKUP_DIR/styles.css" || { echo "Preview неожиданно изменил styles.css" >&2; exit 1; }
  cmp -s "$SW" "$BACKUP_DIR/sw.js" || { echo "Preview неожиданно изменил sw.js" >&2; exit 1; }
  if [[ -f "$BACKUP_DIR/manual.html" ]]; then
    cmp -s "$MANUAL" "$BACKUP_DIR/manual.html" || { echo "Preview неожиданно изменил manual.html" >&2; exit 1; }
  else
    [[ ! -e "$MANUAL" ]] || { echo "Preview неожиданно создал manual.html" >&2; exit 1; }
  fi
  grep -q 'ai-home-v2.js?v=20260905-2' "$PREVIEW"
  grep -q 'Напиши или скажи' "$PREVIEW"
else
  # Promotion is explicit. Until this mode is requested, the stable root stays untouched.
  if ! grep -q 'ai-home-v2.js?v=20260905-2' "$INDEX"; then
    cp -a "$INDEX" "$MANUAL"
  elif [[ ! -f "$MANUAL" ]]; then
    echo "AI Home v2 уже стоит, но manual.html отсутствует. Останавливаюсь безопасно." >&2
    exit 1
  fi

  put_file "$TMP_DIR/index.html" "$INDEX"
  put_file "$TMP_DIR/ai-home-v2.js" "$AI_JS"
  put_file "$TMP_DIR/ai-home-v2.css" "$AI_CSS"

  cmp -s "$APP_JS" "$BACKUP_DIR/app.js" || { echo "app.js неожиданно изменился" >&2; exit 1; }
  cmp -s "$APP_CSS" "$BACKUP_DIR/styles.css" || { echo "styles.css неожиданно изменился" >&2; exit 1; }
  cmp -s "$SW" "$BACKUP_DIR/sw.js" || { echo "sw.js неожиданно изменился" >&2; exit 1; }
  grep -q 'ai-home-v2.js?v=20260905-2' "$INDEX"
  grep -q 'Напиши или скажи' "$INDEX"
  [[ -s "$MANUAL" ]]
fi

if [[ -z "$TEST_ROOT" ]]; then
  systemctl is-active --quiet dvizh.service
  systemctl is-active --quiet dvizh-ai-home.service
fi

echo
if [[ "$MODE" == "preview" ]]; then
  echo "DVIZH AI Home v2 preview installed: $VERSION"
  echo "Preview: /ai-home-v2-preview.html"
  echo "Главная /, app.js, styles.css, sw.js и manual.html не изменены."
  echo "Hermes bridge не перезапускался и базы не изменялись."
else
  echo "DVIZH AI Home v2 promoted: $VERSION"
  echo "Главная / теперь полностью изолирована от старого app.js."
  echo "Полный старый интерфейс сохранён: /manual.html"
  echo "Hermes bridge не перезапускался и базы не изменялись."
fi
echo "Backup: $BACKUP_DIR"
