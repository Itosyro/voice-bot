#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-ai-home-v2-byte-smoke.1"
RELEASE_COMMIT="d6418224eae292417a645b2a73da157d939526b9"
DEFAULT_BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${RELEASE_COMMIT}/ai-home-v2"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"
TEST_HTTP_BASE_URL="${DVIZH_AI_HOME_V2_TEST_HTTP_BASE_URL:-}"
TEST_SOURCE_DIR="${DVIZH_AI_HOME_V2_TEST_SOURCE_DIR:-}"

[[ $# -eq 0 ]] || { echo "Этот promote не принимает аргументы." >&2; exit 1; }
if [[ -z "$TEST_ROOT" && ( -n "$TEST_HTTP_BASE_URL" || -n "$TEST_SOURCE_DIR" ) ]]; then
  echo "Тестовые переопределения запрещены на живом сервере." >&2
  exit 1
fi
if [[ -n "$TEST_ROOT" && -z "$TEST_HTTP_BASE_URL" ]]; then
  echo "В тестовом root обязателен DVIZH_AI_HOME_V2_TEST_HTTP_BASE_URL." >&2
  exit 1
fi
if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через sudo: promote меняет только index.html/manual.html." >&2
  exit 1
fi
for tool in curl python3 sha256sum cmp grep flock; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done
if [[ -z "$TEST_ROOT" ]]; then
  command -v systemctl >/dev/null 2>&1 || { echo "Не найден systemctl" >&2; exit 1; }
fi

if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT=/opt/dvizh/static
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT=/opt/dvizh
else
  echo "Не найден веб-интерфейс ДВИЖа." >&2
  exit 1
fi
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"
HTTP_BASE="${TEST_HTTP_BASE_URL:-http://127.0.0.1:8000}"

exec 9< "$APP_ROOT"
flock -n 9 || { echo "Другая установка AI Home v2 уже выполняется." >&2; exit 1; }

for name in index.html app.js styles.css sw.js ai-home-v2-preview.html ai-home-v2.js ai-home-v2.css; do
  [[ -f "$APP_ROOT/$name" && ! -L "$APP_ROOT/$name" ]] || {
    echo "Нет ожидаемого обычного файла: $APP_ROOT/$name" >&2
    exit 1
  }
done
if [[ -L "$APP_ROOT/manual.html" || ( -e "$APP_ROOT/manual.html" && ! -f "$APP_ROOT/manual.html" ) ]]; then
  echo "Небезопасный путь manual.html" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-v2-byte-smoke.XXXXXX)"
BACKUP_DIR=""
SUCCESS=0
PROMOTION_STARTED=0
MANUAL_WAS_PRESENT=0
ROLLBACK_FAILED=0

finish() {
  local code=$?
  trap - EXIT
  if [[ "$PROMOTION_STARTED" == 1 && "$SUCCESS" != 1 && -n "$BACKUP_DIR" ]]; then
    echo "Promotion не подтверждён: возвращаю предыдущую главную и ручной маршрут." >&2
    cp -a -- "$BACKUP_DIR/index.html" "$APP_ROOT/index.html" || ROLLBACK_FAILED=1
    if [[ "$MANUAL_WAS_PRESENT" == 1 ]]; then
      cp -a -- "$BACKUP_DIR/manual.html" "$APP_ROOT/manual.html" || ROLLBACK_FAILED=1
    else
      rm -f -- "$APP_ROOT/manual.html" || ROLLBACK_FAILED=1
    fi
    if [[ "$ROLLBACK_FAILED" == 0 ]]; then
      echo "Автоматический rollback завершён. Backup: $BACKUP_DIR" >&2
    else
      echo "ВНИМАНИЕ: rollback неполный. Backup: $BACKUP_DIR" >&2
      code=90
    fi
  fi
  rm -rf -- "$TMP_DIR"
  if [[ -n "$TEST_ROOT" && -n "$BACKUP_DIR" ]]; then rm -rf -- "$BACKUP_DIR"; fi
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

mkdir -p "$TMP_DIR/release"
if [[ -n "$TEST_SOURCE_DIR" ]]; then
  for name in index.html ai-home-v2.js ai-home-v2.css; do
    cp -- "$TEST_SOURCE_DIR/$name" "$TMP_DIR/release/$name"
  done
else
  for name in index.html ai-home-v2.js ai-home-v2.css; do
    curl --fail --silent --show-error --location \
      --retry 4 --retry-delay 1 --connect-timeout 10 --max-time 60 \
      "$DEFAULT_BASE_URL/$name" -o "$TMP_DIR/release/$name"
  done
fi

verify_git_blob() {
  local file="$1" expected="$2" actual
  actual="$(python3 - "$file" <<'PY'
import hashlib, pathlib, sys
p=pathlib.Path(sys.argv[1]); data=p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)"
  [[ "$actual" == "$expected" ]] || {
    echo "Immutable release mismatch: $(basename "$file") ($actual)" >&2
    exit 1
  }
}
verify_git_blob "$TMP_DIR/release/index.html" "2a703fbc0ca731ae68cf733c0ce6fb9552fceb2e"
verify_git_blob "$TMP_DIR/release/ai-home-v2.js" "95b1ce6a09341840802efebb958f41441cc43560"
verify_git_blob "$TMP_DIR/release/ai-home-v2.css" "273934a33d7913c45f4b7656315aeedfd6e4e813"

grep -Fq '/ai-home-v2.js?v=20260905-3' "$TMP_DIR/release/index.html"
grep -Fq '/ai-home-v2.css?v=20260905-3' "$TMP_DIR/release/index.html"
grep -Fq "const API = '/api/state';" "$TMP_DIR/release/ai-home-v2.js"

cmp -s "$TMP_DIR/release/index.html" "$APP_ROOT/ai-home-v2-preview.html" || {
  echo "Установленный preview не совпадает с проверенным release." >&2; exit 1;
}
cmp -s "$TMP_DIR/release/ai-home-v2.js" "$APP_ROOT/ai-home-v2.js" || {
  echo "Установленный ai-home-v2.js отличается от release." >&2; exit 1;
}
cmp -s "$TMP_DIR/release/ai-home-v2.css" "$APP_ROOT/ai-home-v2.css" || {
  echo "Установленный ai-home-v2.css отличается от release." >&2; exit 1;
}

if grep -Fq '/ai-home-v2.js' "$APP_ROOT/index.html"; then
  [[ -f "$APP_ROOT/manual.html" ]] || { echo "Главная уже AI Home, но manual.html отсутствует." >&2; exit 1; }
  echo "Главная уже AI Home v2; выполняю только byte-exact HTTP-проверку текущего состояния."
fi

if [[ -z "$TEST_ROOT" ]]; then
  for unit in dvizh.service dvizh-auth.service dvizh-ai-home.service; do
    systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
  done
  curl -fsS --max-time 8 "$HTTP_BASE/api/health" >/dev/null
  python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
p=Path('/var/lib/dvizh/ai-home-status.json')
if not p.is_file(): raise SystemExit('Нет свежего статуса AI Home bridge')
data=json.loads(p.read_text(encoding='utf-8'))
if data.get('ok') is not True or not str(data.get('model') or '').strip():
    raise SystemExit('AI Home bridge сейчас не готов к promotion')
raw=str(data.get('at') or '').strip().replace('Z','+00:00')
at=datetime.fromisoformat(raw)
if at.tzinfo is None: at=at.replace(tzinfo=timezone.utc)
age=(datetime.now(timezone.utc)-at.astimezone(timezone.utc)).total_seconds()
if age < -10 or age > 60: raise SystemExit(f'Статус AI Home bridge устарел ({age:.0f} сек.)')
PY
fi

if [[ -n "$TEST_ROOT" ]]; then
  BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dvizh-ai-home-v2-byte-backup.XXXXXX")"
else
  install -d -m 0700 /var/lib/dvizh/backups
  BACKUP_DIR="$(mktemp -d /var/lib/dvizh/backups/ai-home-v2-byte-promote.XXXXXX)"
fi
cp -a -- "$APP_ROOT/index.html" "$BACKUP_DIR/index.html"
if [[ -f "$APP_ROOT/manual.html" ]]; then
  MANUAL_WAS_PRESENT=1
  cp -a -- "$APP_ROOT/manual.html" "$BACKUP_DIR/manual.html"
  if ! grep -Fq '/ai-home-v2.js' "$APP_ROOT/index.html"; then
    cmp -s "$APP_ROOT/index.html" "$APP_ROOT/manual.html" || {
      echo "Существующий manual.html отличается от текущей стабильной главной; остановка." >&2
      exit 1
    }
  fi
fi

sha256sum "$APP_ROOT/app.js" "$APP_ROOT/styles.css" "$APP_ROOT/sw.js" \
  "$APP_ROOT/ai-home-v2-preview.html" "$APP_ROOT/ai-home-v2.js" "$APP_ROOT/ai-home-v2.css" \
  > "$TMP_DIR/readonly.sha256"

http_exact() {
  local label="$1" path="$2" expected="$3" body="$TMP_DIR/$label.http" code
  code="$(curl --silent --show-error --location --max-time 8 \
    -H 'Cache-Control: no-cache' -o "$body" -w '%{http_code}' \
    "$HTTP_BASE$path?_ai_home_v2_byte=$(date +%s%N)")" || {
      echo "HTTP $label: curl failed for $path" >&2; return 1;
    }
  [[ "$code" == 200 ]] || {
    echo "HTTP $label: ожидался 200 для $path, получен $code" >&2; return 1;
  }
  if ! cmp -s "$expected" "$body"; then
    echo "HTTP $label: body не совпадает байт-в-байт с $(basename "$expected")." >&2
    echo "  expected sha256=$(sha256sum "$expected" | awk '{print $1}') bytes=$(wc -c < "$expected")" >&2
    echo "  actual   sha256=$(sha256sum "$body" | awk '{print $1}') bytes=$(wc -c < "$body")" >&2
    return 1
  fi
  echo "HTTP $label: OK (byte-exact)"
}

# Stage 1: publish only the manual copy, while / is still the stable old UI.
PROMOTION_STARTED=1
if [[ ! -f "$APP_ROOT/manual.html" ]]; then
  stage_manual="$(mktemp "$APP_ROOT/.manual.html.stage.XXXXXX")"
  cp --preserve=mode,timestamps "$APP_ROOT/index.html" "$stage_manual"
  mv -f -- "$stage_manual" "$APP_ROOT/manual.html"
fi
http_exact manual-preflight /manual.html "$APP_ROOT/manual.html"
# Root must still be untouched at this point.
cmp -s "$BACKUP_DIR/index.html" "$APP_ROOT/index.html" || {
  echo "Preflight неожиданно изменил index.html." >&2; exit 1;
}

# Stage 2: only after the manual route is proven live, atomically publish AI Home at /.
stage_index="$(mktemp "$APP_ROOT/.index.html.stage.XXXXXX")"
install -m 0644 "$TMP_DIR/release/index.html" "$stage_index"
mv -f -- "$stage_index" "$APP_ROOT/index.html"
cmp -s "$TMP_DIR/release/index.html" "$APP_ROOT/index.html"

http_exact root / "$APP_ROOT/index.html"
http_exact index /index.html "$APP_ROOT/index.html"
http_exact manual /manual.html "$APP_ROOT/manual.html"
sha256sum --check --status "$TMP_DIR/readonly.sha256"

if [[ -z "$TEST_ROOT" ]]; then
  curl -fsS --max-time 8 "$HTTP_BASE/api/health" >/dev/null
  for unit in dvizh.service dvizh-auth.service dvizh-ai-home.service; do
    systemctl is-active --quiet "$unit" || { echo "$unit перестал быть active" >&2; exit 1; }
  done
fi

SUCCESS=1
echo
echo "AI Home v2 promotion подтверждён: $VERSION"
echo "Release: $RELEASE_COMMIT"
echo "AI Home: /"
echo "Ручной режим: /manual.html"
echo "Rollback backup: $BACKUP_DIR"
echo "HTTP /, /index.html и /manual.html совпали с файлами байт-в-байт."
echo "app.js, styles.css, sw.js, preview-assets, БД, Hermes, server.py и сервисы не изменялись/не перезапускались."
