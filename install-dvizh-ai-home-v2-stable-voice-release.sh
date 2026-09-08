#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.08-ai-home-v2-stable-voice.1"
SOURCE_COMMIT="4c74d5216e2cfcca5a14bdaf179cf520aecfd685"
SOURCE_INDEX_BLOB="e27cbfedf3022525fff3d6b77a12d824055c252c"
SOURCE_JS_BLOB="c25a48d815f4cb05b0be90d4d3c5196d60be6e6f"
OLD_INDEX_BLOB="2a703fbc0ca731ae68cf733c0ce6fb9552fceb2e"
OLD_JS_BLOB="95b1ce6a09341840802efebb958f41441cc43560"
CSS_BLOB="273934a33d7913c45f4b7656315aeedfd6e4e813"
SOURCE_BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${SOURCE_COMMIT}/ai-home-v2"
EXPECTED_POLICY="Permissions-Policy: camera=(), microphone=(self), geolocation=(), payment=()"
TEST_ROOT="${DVIZH_STABLE_VOICE_ROOT:-}"
TEST_HTTP_BASE="${DVIZH_STABLE_VOICE_HTTP_BASE:-}"
TEST_SOURCE_DIR="${DVIZH_STABLE_VOICE_SOURCE_DIR:-}"
TEST_FAIL_AFTER_WRITE="${DVIZH_STABLE_VOICE_FAIL_AFTER_WRITE:-0}"

[[ $# -eq 0 ]] || { echo "Этот установщик не принимает аргументы." >&2; exit 1; }
if [[ -z "$TEST_ROOT" && ( -n "$TEST_HTTP_BASE" || -n "$TEST_SOURCE_DIR" || "$TEST_FAIL_AFTER_WRITE" != 0 ) ]]; then
  echo "Тестовые переопределения запрещены на живом сервере." >&2
  exit 1
fi
if [[ -n "$TEST_ROOT" && ( -z "$TEST_HTTP_BASE" || -z "$TEST_SOURCE_DIR" ) ]]; then
  echo "Для fixture нужны DVIZH_STABLE_VOICE_HTTP_BASE и DVIZH_STABLE_VOICE_SOURCE_DIR." >&2
  exit 1
fi
if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Для stable-update нужен root." >&2
  exit 1
fi
for tool in curl python3 sha256sum cmp grep flock mktemp cp mv rm find sort xargs; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT=/opt/dvizh/static
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT=/opt/dvizh
else
  echo "Не найден stable web-root ДВИЖа." >&2
  exit 1
fi
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"
HTTP_BASE="${TEST_HTTP_BASE:-http://127.0.0.1:8000}"
INDEX="$APP_ROOT/index.html"
JS="$APP_ROOT/ai-home-v2.js"
CSS="$APP_ROOT/ai-home-v2.css"

for file in "$INDEX" "$JS" "$CSS" "$APP_ROOT/manual.html" "$APP_ROOT/app.js" "$APP_ROOT/sync.js" "$APP_ROOT/sw.js"; do
  [[ -f "$file" && ! -L "$file" ]] || { echo "Небезопасный или отсутствующий файл: $file" >&2; exit 1; }
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

current_index_blob="$(git_blob "$INDEX")"
current_js_blob="$(git_blob "$JS")"
current_css_blob="$(git_blob "$CSS")"
[[ "$current_index_blob" == "$OLD_INDEX_BLOB" || "$current_index_blob" == "$SOURCE_INDEX_BLOB" ]] || {
  echo "Текущий index.html не относится к ожидаемому stable contract: $current_index_blob" >&2; exit 1;
}
[[ "$current_js_blob" == "$OLD_JS_BLOB" || "$current_js_blob" == "$SOURCE_JS_BLOB" ]] || {
  echo "Текущий ai-home-v2.js не относится к ожидаемому stable contract: $current_js_blob" >&2; exit 1;
}
[[ "$current_css_blob" == "$CSS_BLOB" ]] || { echo "ai-home-v2.css отличается от stable contract: $current_css_blob" >&2; exit 1; }

grep -Fq '/ai-home-v2.js?v=20260905-3.1' "$INDEX" || { echo "Текущая главная не похожа на stable AI Home v2." >&2; exit 1; }

tmp="$(mktemp -d /tmp/dvizh-stable-voice.XXXXXX)"
backup_dir=""
changed=0
success=0

protected_snapshot() {
  local output="$1"
  find "$APP_ROOT" -maxdepth 1 -type f ! -name 'index.html' ! -name 'ai-home-v2.js' -print0 \
    | sort -z | xargs -0 sha256sum > "$output"
}

policy_ok() {
  local headers
  headers="$(curl --fail --silent --show-error --dump-header - --output /dev/null --max-time 8 \
    "$HTTP_BASE/ai-home-v2.js?_stable_voice_policy=$(date +%s%N)" | tr -d '\r')" || return 1
  grep -Fqi "$EXPECTED_POLICY" <<<"$headers"
}

http_exact() {
  local label="$1" path="$2" expected="$3" body="$tmp/${label}.body" code
  code="$(curl --silent --show-error --max-time 8 -H 'Cache-Control: no-cache' \
    -o "$body" -w '%{http_code}' "$HTTP_BASE$path")" || return 1
  [[ "$code" == 200 ]] || { echo "HTTP $label: ожидался 200, получен $code" >&2; return 1; }
  cmp -s "$expected" "$body" || {
    echo "HTTP $label: ответ не совпал байт-в-байт." >&2
    echo "expected=$(sha256sum "$expected" | awk '{print $1}') actual=$(sha256sum "$body" | awk '{print $1}')" >&2
    return 1
  }
}

restore_backup() {
  [[ -n "$backup_dir" && -f "$backup_dir/index.html" && -f "$backup_dir/ai-home-v2.js" ]] || return 1
  local stage
  stage="$(mktemp "$APP_ROOT/.index.rollback.XXXXXX")"; rm -f -- "$stage"; cp -a -- "$backup_dir/index.html" "$stage"; mv -f -- "$stage" "$INDEX"
  stage="$(mktemp "$APP_ROOT/.js.rollback.XXXXXX")"; rm -f -- "$stage"; cp -a -- "$backup_dir/ai-home-v2.js" "$stage"; mv -f -- "$stage" "$JS"
  cmp -s "$backup_dir/index.html" "$INDEX" && cmp -s "$backup_dir/ai-home-v2.js" "$JS"
}

finish() {
  local rc=$?
  trap - EXIT INT TERM HUP
  if [[ $rc -ne 0 && "$changed" == 1 ]]; then
    echo "Stable voice update не подтверждён: возвращаю backup index.html и ai-home-v2.js." >&2
    if restore_backup; then
      http_exact rollback-root "/?_stable_voice_rollback=$(date +%s%N)" "$backup_dir/index.html" || true
      http_exact rollback-js "/ai-home-v2.js?_stable_voice_rollback=$(date +%s%N)" "$backup_dir/ai-home-v2.js" || true
      echo "Автоматический rollback завершён. Backup: $backup_dir" >&2
    else
      echo "ВНИМАНИЕ: автоматический rollback не подтверждён. Backup: $backup_dir" >&2
      rc=90
    fi
  fi
  rm -rf -- "$tmp"
  if [[ -n "$TEST_ROOT" && -n "$backup_dir" ]]; then rm -rf -- "$backup_dir"; fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

policy_ok || { echo "Prerequisite не выполнен: backend не отдаёт $EXPECTED_POLICY" >&2; exit 1; }
protected_snapshot "$tmp/protected.before"

mkdir -p "$tmp/source"
if [[ -n "$TEST_SOURCE_DIR" ]]; then
  cp -- "$TEST_SOURCE_DIR/index.html" "$tmp/source/index.html"
  cp -- "$TEST_SOURCE_DIR/ai-home-v2.js" "$tmp/source/ai-home-v2.js"
else
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 --connect-timeout 10 --max-time 60 \
    "$SOURCE_BASE_URL/index.html" -o "$tmp/source/index.html"
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 --connect-timeout 10 --max-time 60 \
    "$SOURCE_BASE_URL/ai-home-v2.js" -o "$tmp/source/ai-home-v2.js"
fi
[[ "$(git_blob "$tmp/source/index.html")" == "$SOURCE_INDEX_BLOB" ]] || { echo "Immutable source mismatch: index.html" >&2; exit 1; }
[[ "$(git_blob "$tmp/source/ai-home-v2.js")" == "$SOURCE_JS_BLOB" ]] || { echo "Immutable source mismatch: ai-home-v2.js" >&2; exit 1; }
grep -Fq '/ai-home-v2.js?v=20260905-3.1-voice-20260908' "$tmp/source/index.html"
grep -Fq 'getUserMedia({ audio: true })' "$tmp/source/ai-home-v2.js"
grep -Fq 'stopMicrophoneStream(stream)' "$tmp/source/ai-home-v2.js"

if [[ "$current_index_blob" == "$SOURCE_INDEX_BLOB" && "$current_js_blob" == "$SOURCE_JS_BLOB" ]]; then
  http_exact root "/?_stable_voice_verify=$(date +%s%N)" "$tmp/source/index.html"
  http_exact js "/ai-home-v2.js?v=20260905-3.1-voice-20260908&_stable_voice_verify=$(date +%s%N)" "$tmp/source/ai-home-v2.js"
  policy_ok
  sha256sum --check --status "$tmp/protected.before"
  success=1
  trap - EXIT INT TERM HUP
  rm -rf -- "$tmp"
  echo "Stable voice уже установлен и повторно проверен: $VERSION"
  echo "Source: $SOURCE_COMMIT"
  echo "Verified: $EXPECTED_POLICY"
  exit 0
fi

if [[ -n "$TEST_ROOT" ]]; then
  backup_dir="$(mktemp -d "${TMPDIR:-/tmp}/dvizh-stable-voice-backup.XXXXXX")"
else
  mkdir -p /var/lib/dvizh/backups
  chmod 0700 /var/lib/dvizh/backups
  backup_dir="$(mktemp -d /var/lib/dvizh/backups/ai-home-v2-stable-voice.XXXXXX)"
  chmod 0700 "$backup_dir"
fi
cp -a -- "$INDEX" "$backup_dir/index.html"
cp -a -- "$JS" "$backup_dir/ai-home-v2.js"

replace_from_source() {
  local source="$1" target="$2" stage
  stage="$(mktemp "$APP_ROOT/.stable-voice.stage.XXXXXX")"
  rm -f -- "$stage"
  cp -a -- "$target" "$stage"
  cat -- "$source" > "$stage"
  mv -f -- "$stage" "$target"
}

changed=1
# JS first: the old immutable cache key remains valid until index.html switches to the new key.
replace_from_source "$tmp/source/ai-home-v2.js" "$JS"
replace_from_source "$tmp/source/index.html" "$INDEX"

[[ "$(git_blob "$INDEX")" == "$SOURCE_INDEX_BLOB" ]] || { echo "После записи index blob не совпал." >&2; exit 1; }
[[ "$(git_blob "$JS")" == "$SOURCE_JS_BLOB" ]] || { echo "После записи JS blob не совпал." >&2; exit 1; }

if [[ "$TEST_FAIL_AFTER_WRITE" == 1 ]]; then
  echo "Test-only forced failure after write." >&2
  exit 77
fi

http_exact root "/?_stable_voice_release=$(date +%s%N)" "$tmp/source/index.html"
http_exact js "/ai-home-v2.js?v=20260905-3.1-voice-20260908&_stable_voice_release=$(date +%s%N)" "$tmp/source/ai-home-v2.js"
policy_ok || { echo "После записи microphone=(self) prerequisite исчез." >&2; exit 1; }
sha256sum --check --status "$tmp/protected.before" || { echo "Изменился защищённый static-файл вне index.html/ai-home-v2.js." >&2; exit 1; }

changed=0
success=1
trap - EXIT INT TERM HUP
rm -rf -- "$tmp"

echo "Установлен $VERSION"
echo "Source: $SOURCE_COMMIT"
echo "index.html: $SOURCE_INDEX_BLOB"
echo "ai-home-v2.js: $SOURCE_JS_BLOB"
echo "Verified: $EXPECTED_POLICY"
echo "Backup: $backup_dir"
echo "Изменены только index.html и ai-home-v2.js. manual.html, app.js, sync.js, sw.js, CSS, preview, backend, БД, state и сервисы не изменялись."
