#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-ai-home-v2-promote-bootstrap.1"
RELEASE_COMMIT="d6418224eae292417a645b2a73da157d939526b9"
DEFAULT_BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${RELEASE_COMMIT}"
BASE_URL="${DVIZH_AI_HOME_V2_PROMOTE_BASE_URL:-$DEFAULT_BASE_URL}"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"
TEST_FAIL_AFTER_PROMOTE="${DVIZH_AI_HOME_V2_TEST_FAIL_AFTER_PROMOTE:-0}"

[[ $# -eq 0 ]] || { echo "Этот bootstrap не принимает аргументы: он выполняет только проверенный promote AI Home v2." >&2; exit 1; }
if [[ -n "${DVIZH_AI_HOME_V2_PROMOTE_BASE_URL:-}" && -z "$TEST_ROOT" ]]; then
  echo "Переопределение источника разрешено только в тестовом root." >&2
  exit 1
fi
if [[ "$TEST_FAIL_AFTER_PROMOTE" != 0 && -z "$TEST_ROOT" ]]; then
  echo "Тестовая инъекция ошибки запрещена на живом сервере." >&2
  exit 1
fi
if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через sudo: promote меняет только index.html/manual.html после всех проверок." >&2
  exit 1
fi
for tool in curl python3 bash sha256sum cmp grep; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done
if [[ -z "$TEST_ROOT" ]]; then
  command -v systemctl >/dev/null 2>&1 || { echo "Не найден systemctl" >&2; exit 1; }
fi

TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-v2-promote.XXXXXX)"
BACKUP_DIR=""
APP_ROOT=""
PROMOTION_STARTED=0
SUCCESS=0
ROLLBACK_FAILED=0
MANUAL_WAS_PRESENT=0

finish() {
  local code=$?
  trap - EXIT
  if [[ "$PROMOTION_STARTED" == 1 && "$SUCCESS" != 1 && -n "$APP_ROOT" && -n "$BACKUP_DIR" ]]; then
    echo "Promotion не подтверждён: автоматически возвращаю предыдущую главную." >&2
    if [[ -f "$BACKUP_DIR/index.html" ]]; then
      cp -a -- "$BACKUP_DIR/index.html" "$APP_ROOT/index.html" || ROLLBACK_FAILED=1
    else
      ROLLBACK_FAILED=1
    fi
    if [[ "$MANUAL_WAS_PRESENT" == 1 ]]; then
      cp -a -- "$BACKUP_DIR/manual.html" "$APP_ROOT/manual.html" || ROLLBACK_FAILED=1
    else
      rm -f -- "$APP_ROOT/manual.html" || ROLLBACK_FAILED=1
    fi
    if [[ "$ROLLBACK_FAILED" == 0 ]]; then
      echo "Автоматический rollback завершён. Backup: $BACKUP_DIR" >&2
    else
      echo "ВНИМАНИЕ: автоматический rollback неполный. Не закрывай терминал; backup: $BACKUP_DIR" >&2
      code=90
    fi
  fi
  rm -rf -- "$TMP_DIR"
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

mkdir -p "$TMP_DIR/ai-home-v2"
fetch() {
  local path="$1" target="$2"
  curl --fail --silent --show-error --location \
    --retry 4 --retry-delay 1 --connect-timeout 10 --max-time 60 \
    "$BASE_URL/$path" -o "$target"
}
fetch install-dvizh-ai-home-v2.sh "$TMP_DIR/install-dvizh-ai-home-v2.sh"
fetch ai-home-v2/index.html "$TMP_DIR/ai-home-v2/index.html"
fetch ai-home-v2/ai-home-v2.js "$TMP_DIR/ai-home-v2/ai-home-v2.js"
fetch ai-home-v2/ai-home-v2.css "$TMP_DIR/ai-home-v2/ai-home-v2.css"

verify_git_blob() {
  local file="$1" expected="$2" actual
  actual="$(python3 - "$file" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = p.read_bytes()
header = f"blob {len(data)}\0".encode("ascii")
print(hashlib.sha1(header + data).hexdigest())
PY
)"
  [[ "$actual" == "$expected" ]] || {
    echo "Проверка immutable payload не прошла: $(basename "$file")" >&2
    exit 1
  }
}
verify_git_blob "$TMP_DIR/install-dvizh-ai-home-v2.sh" "88ad4b9f4db39614ccc1ba4c70b256f4a3c4d2b0"
verify_git_blob "$TMP_DIR/ai-home-v2/index.html" "2a703fbc0ca731ae68cf733c0ce6fb9552fceb2e"
verify_git_blob "$TMP_DIR/ai-home-v2/ai-home-v2.js" "95b1ce6a09341840802efebb958f41441cc43560"
verify_git_blob "$TMP_DIR/ai-home-v2/ai-home-v2.css" "273934a33d7913c45f4b7656315aeedfd6e4e813"

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
for name in index.html app.js styles.css sw.js ai-home-v2-preview.html ai-home-v2.js ai-home-v2.css; do
  [[ -f "$APP_ROOT/$name" && ! -L "$APP_ROOT/$name" ]] || { echo "Нет безопасного установленного файла: $name" >&2; exit 1; }
done

# Promotion is allowed only for the exact preview that was already tested on the phone.
cmp -s "$TMP_DIR/ai-home-v2/index.html" "$APP_ROOT/ai-home-v2-preview.html" || { echo "Установленный preview не совпадает с проверенным release." >&2; exit 1; }
cmp -s "$TMP_DIR/ai-home-v2/ai-home-v2.js" "$APP_ROOT/ai-home-v2.js" || { echo "Установленный ai-home-v2.js отличается от release." >&2; exit 1; }
cmp -s "$TMP_DIR/ai-home-v2/ai-home-v2.css" "$APP_ROOT/ai-home-v2.css" || { echo "Установленный ai-home-v2.css отличается от release." >&2; exit 1; }

if [[ -z "$TEST_ROOT" ]]; then
  for unit in dvizh.service dvizh-auth.service dvizh-ai-home.service; do
    systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
  done
  curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
  python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
p = Path('/var/lib/dvizh/ai-home-status.json')
if not p.is_file():
    raise SystemExit('Нет свежего статуса AI Home bridge')
data = json.loads(p.read_text(encoding='utf-8'))
if data.get('ok') is not True or not str(data.get('model') or '').strip():
    raise SystemExit('AI Home bridge сейчас не готов к promotion')
raw = str(data.get('at') or '').strip().replace('Z', '+00:00')
at = datetime.fromisoformat(raw)
if at.tzinfo is None:
    at = at.replace(tzinfo=timezone.utc)
age = (datetime.now(timezone.utc) - at.astimezone(timezone.utc)).total_seconds()
if age < -10 or age > 60:
    raise SystemExit(f'Статус AI Home bridge устарел ({age:.0f} сек.)')
PY
fi

if [[ -n "$TEST_ROOT" ]]; then
  BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dvizh-ai-home-v2-promote-wrapper-backup.XXXXXX")"
else
  install -d -m 0700 /var/lib/dvizh/backups
  BACKUP_DIR="$(mktemp -d /var/lib/dvizh/backups/ai-home-v2-final-promote.XXXXXX)"
fi
cp -a -- "$APP_ROOT/index.html" "$BACKUP_DIR/index.html"
if [[ -f "$APP_ROOT/manual.html" ]]; then
  MANUAL_WAS_PRESENT=1
  cp -a -- "$APP_ROOT/manual.html" "$BACKUP_DIR/manual.html"
fi

sha256sum \
  "$APP_ROOT/app.js" "$APP_ROOT/styles.css" "$APP_ROOT/sw.js" \
  "$APP_ROOT/ai-home-v2-preview.html" "$APP_ROOT/ai-home-v2.js" "$APP_ROOT/ai-home-v2.css" \
  > "$TMP_DIR/readonly.sha256"

chmod 0755 "$TMP_DIR/install-dvizh-ai-home-v2.sh"
COMMON_ENV=(DVIZH_AI_HOME_V2_SOURCE_DIR="$TMP_DIR/ai-home-v2")
if [[ -n "$TEST_ROOT" ]]; then COMMON_ENV+=(DVIZH_AI_HOME_V2_ROOT="$APP_ROOT"); fi
env "${COMMON_ENV[@]}" bash "$TMP_DIR/install-dvizh-ai-home-v2.sh" --check
PROMOTION_STARTED=1
env "${COMMON_ENV[@]}" bash "$TMP_DIR/install-dvizh-ai-home-v2.sh" --promote

if [[ "$TEST_FAIL_AFTER_PROMOTE" == 1 ]]; then
  echo "TEST: имитация сбоя после promote" >&2
  exit 97
fi

# Verify the published files themselves first. This path also runs in CI fixtures.
grep -Fq '/ai-home-v2.js' "$APP_ROOT/index.html"
! grep -Eq "(src|href)=[\"']/?app\\.js" "$APP_ROOT/index.html"
grep -Eq "(src|href)=[\"']/?app\\.js" "$APP_ROOT/manual.html"
! grep -Fq '/ai-home-v2.js' "$APP_ROOT/manual.html"
sha256sum --check --status "$TMP_DIR/readonly.sha256"

if [[ -z "$TEST_ROOT" ]]; then
  # HTTP smoke happens before this wrapper commits success. A failure triggers rollback above.
  stamp="$(date +%s)"
  curl -fsS --max-time 8 -H 'Cache-Control: no-cache' "http://127.0.0.1:8000/?_ai_home_v2=${stamp}" -o "$TMP_DIR/root.http"
  curl -fsS --max-time 8 -H 'Cache-Control: no-cache' "http://127.0.0.1:8000/manual.html?_ai_home_v2=${stamp}" -o "$TMP_DIR/manual.http"
  grep -Fq '/ai-home-v2.js' "$TMP_DIR/root.http"
  ! grep -Eq "(src|href)=[\"']/?app\\.js" "$TMP_DIR/root.http"
  grep -Eq "(src|href)=[\"']/?app\\.js" "$TMP_DIR/manual.http"
  ! grep -Fq '/ai-home-v2.js' "$TMP_DIR/manual.http"
  curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
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
echo "app.js, styles.css, sw.js, preview-assets, БД, Hermes и сервисы не изменялись/не перезапускались."
