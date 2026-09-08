#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.08-ai-home-v2-voice-preview-cleanup.1"
APP_ROOT="${DVIZH_VOICE_CLEANUP_ROOT:-/opt/dvizh/static}"
HTTP_BASE="${DVIZH_VOICE_CLEANUP_HTTP_BASE:-http://127.0.0.1:8000}"
HTML="$APP_ROOT/ai-home-v2-voice-preview.html"
JS="$APP_ROOT/ai-home-v2-voice.js"
EXPECTED_HTML_BLOB="05e4bef31c39ac4f917062e97609ada3c5513fa4"
EXPECTED_JS_BLOB="64e2698d90968cc0c8d86ae81207f97976710db2"
STABLE_INDEX_BLOB="e27cbfedf3022525fff3d6b77a12d824055c252c"
STABLE_JS_BLOB="c25a48d815f4cb05b0be90d4d3c5196d60be6e6f"
EXPECTED_POLICY="Permissions-Policy: camera=(), microphone=(self), geolocation=(), payment=()"
TEST_FAIL_AFTER_DELETE="${DVIZH_VOICE_CLEANUP_FAIL_AFTER_DELETE:-0}"

[[ $# -eq 0 ]] || { echo "Этот cleanup не принимает аргументы." >&2; exit 1; }
if [[ "$APP_ROOT" == "/opt/dvizh/static" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Для cleanup production нужен root." >&2
  exit 1
fi
for tool in curl python3 sha256sum cmp grep flock mktemp cp rm find sort xargs date tr awk mkdir chmod; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done
[[ -d "$APP_ROOT" && ! -L "$APP_ROOT" ]] || { echo "Небезопасный или отсутствующий static root: $APP_ROOT" >&2; exit 1; }
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"
[[ "$APP_ROOT" != "/" ]] || { echo "Отказ: static root не может быть /." >&2; exit 1; }
HTML="$APP_ROOT/ai-home-v2-voice-preview.html"
JS="$APP_ROOT/ai-home-v2-voice.js"

for file in "$APP_ROOT/index.html" "$APP_ROOT/ai-home-v2.js" "$APP_ROOT/ai-home-v2.css" "$APP_ROOT/manual.html" "$APP_ROOT/app.js" "$APP_ROOT/sync.js" "$APP_ROOT/sw.js"; do
  [[ -f "$file" && ! -L "$file" ]] || { echo "Небезопасный или отсутствующий protected file: $file" >&2; exit 1; }
done
for file in "$HTML" "$JS"; do
  [[ ! -L "$file" ]] || { echo "Отказ: preview target является symlink: $file" >&2; exit 1; }
done

exec 9< "$APP_ROOT"
flock -n 9 || { echo "Другая установка web-root уже выполняется." >&2; exit 1; }

git_blob() {
  python3 - "$1" <<'PY'
from pathlib import Path
import hashlib, sys
p = Path(sys.argv[1]); data = p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
}

[[ "$(git_blob "$APP_ROOT/index.html")" == "$STABLE_INDEX_BLOB" ]] || { echo "Stable index.html не совпадает с принятым voice build." >&2; exit 1; }
[[ "$(git_blob "$APP_ROOT/ai-home-v2.js")" == "$STABLE_JS_BLOB" ]] || { echo "Stable ai-home-v2.js не совпадает с принятым voice build." >&2; exit 1; }

if [[ -f "$HTML" ]]; then
  [[ "$(git_blob "$HTML")" == "$EXPECTED_HTML_BLOB" ]] || { echo "Неизвестный voice preview HTML; ничего не удалено." >&2; exit 1; }
fi
if [[ -f "$JS" ]]; then
  [[ "$(git_blob "$JS")" == "$EXPECTED_JS_BLOB" ]] || { echo "Неизвестный voice preview JS; ничего не удалено." >&2; exit 1; }
fi

TMP="$(mktemp -d /tmp/dvizh-voice-preview-cleanup.XXXXXX)"
BACKUP_DIR=""
CHANGED=0

protected_snapshot() {
  local out="$1"
  find "$APP_ROOT" -maxdepth 1 -type f \
    ! -name 'ai-home-v2-voice-preview.html' ! -name 'ai-home-v2-voice.js' -print0 \
    | sort -z | xargs -0 sha256sum > "$out"
}

policy_ok() {
  local headers
  headers="$(curl --fail --silent --show-error --dump-header - --output /dev/null --max-time 8 \
    "$HTTP_BASE/ai-home-v2.js?_voice_cleanup_policy=$(date +%s%N)" | tr -d '\r')" || return 1
  grep -Fqi "$EXPECTED_POLICY" <<<"$headers"
}

http_exact() {
  local label="$1" path="$2" expected="$3" body="$TMP/${label}.body" code
  code="$(curl --silent --show-error --max-time 8 -H 'Cache-Control: no-cache' -o "$body" -w '%{http_code}' "$HTTP_BASE$path")" || return 1
  [[ "$code" == 200 ]] || { echo "HTTP $label: ожидался 200, получен $code" >&2; return 1; }
  cmp -s "$expected" "$body" || { echo "HTTP $label: body не совпал байт-в-байт." >&2; return 1; }
}

restore_preview() {
  [[ -n "$BACKUP_DIR" ]] || return 1
  if [[ -f "$BACKUP_DIR/preview.html" ]]; then cp -a -- "$BACKUP_DIR/preview.html" "$HTML"; else rm -f -- "$HTML"; fi
  if [[ -f "$BACKUP_DIR/preview.js" ]]; then cp -a -- "$BACKUP_DIR/preview.js" "$JS"; else rm -f -- "$JS"; fi
}

finish() {
  local rc=$?
  trap - EXIT INT TERM HUP
  if [[ $rc -ne 0 && "$CHANGED" == 1 ]]; then
    echo "Cleanup не подтверждён: возвращаю preview backup." >&2
    if restore_preview; then
      echo "Автоматический rollback preview завершён. Backup: $BACKUP_DIR" >&2
    else
      echo "ВНИМАНИЕ: rollback preview не подтверждён. Backup: $BACKUP_DIR" >&2
      rc=90
    fi
  fi
  rm -rf -- "$TMP"
  if [[ "$APP_ROOT" != "/opt/dvizh/static" && -n "$BACKUP_DIR" ]]; then rm -rf -- "$BACKUP_DIR"; fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

policy_ok || { echo "Prerequisite не выполнен: backend не отдаёт $EXPECTED_POLICY" >&2; exit 1; }
protected_snapshot "$TMP/protected.before"
http_exact root "/?_voice_cleanup_pre=$(date +%s%N)" "$APP_ROOT/index.html"
http_exact manual "/manual.html?_voice_cleanup_pre=$(date +%s%N)" "$APP_ROOT/manual.html"

if [[ ! -e "$HTML" && ! -e "$JS" ]]; then
  sha256sum --check --status "$TMP/protected.before"
  trap - EXIT INT TERM HUP
  rm -rf -- "$TMP"
  echo "Voice Preview уже удалён; stable AI Home повторно проверен: $VERSION"
  exit 0
fi

if [[ "$APP_ROOT" == "/opt/dvizh/static" ]]; then
  mkdir -p /var/lib/dvizh/backups
  chmod 0700 /var/lib/dvizh/backups
  BACKUP_DIR="$(mktemp -d /var/lib/dvizh/backups/ai-home-v2-voice-preview-cleanup.XXXXXX)"
  chmod 0700 "$BACKUP_DIR"
else
  BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dvizh-voice-preview-cleanup-backup.XXXXXX")"
fi
[[ -f "$HTML" ]] && cp -a -- "$HTML" "$BACKUP_DIR/preview.html"
[[ -f "$JS" ]] && cp -a -- "$JS" "$BACKUP_DIR/preview.js"

CHANGED=1
rm -f -- "$HTML" "$JS"
[[ ! -e "$HTML" && ! -e "$JS" ]] || { echo "Preview-файлы не удалились полностью." >&2; exit 1; }

if [[ "$TEST_FAIL_AFTER_DELETE" == 1 ]]; then
  echo "Test-only forced failure after preview delete." >&2
  exit 77
fi

sha256sum --check --status "$TMP/protected.before" || { echo "Изменился protected static-файл." >&2; exit 1; }
http_exact root "/?_voice_cleanup_post=$(date +%s%N)" "$APP_ROOT/index.html"
http_exact manual "/manual.html?_voice_cleanup_post=$(date +%s%N)" "$APP_ROOT/manual.html"
http_exact js "/ai-home-v2.js?_voice_cleanup_post=$(date +%s%N)" "$APP_ROOT/ai-home-v2.js"
policy_ok || { echo "После cleanup microphone=(self) prerequisite исчез." >&2; exit 1; }

CHANGED=0
trap - EXIT INT TERM HUP
rm -rf -- "$TMP"
echo "Voice Preview удалён: $VERSION"
echo "Удалены только: $HTML и $JS"
echo "Stable AI Home / и Manual /manual.html подтверждены byte-exact."
echo "Backend policy: $EXPECTED_POLICY"
echo "Backup: $BACKUP_DIR"
echo "Сервисы, БД, state, backend, app.js, sync.js, sw.js и CSS не изменялись."
