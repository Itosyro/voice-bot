#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-ai-home-voice-preview.1"
PAYLOAD_REF="03ff9a86dc20aac4f13bd47f073ed3d987714f0d"
JS_BLOB="64e2698d90968cc0c8d86ae81207f97976710db2"
HTML_BLOB="05e4bef31c39ac4f917062e97609ada3c5513fa4"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/ai-home-v2-voice-v1"
TEST_ROOT="${DVIZH_AI_HOME_VOICE_ROOT:-}"
if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
else
  APP_ROOT="/opt/dvizh/static"
  [[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Для установки preview нужен root." >&2; exit 1; }
fi

[[ $# -eq 0 ]] || { echo "Этот установщик не принимает аргументы." >&2; exit 1; }
for tool in curl python3 mktemp cp mv rm sha256sum grep; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done
[[ -d "$APP_ROOT" && ! -L "$APP_ROOT" ]] || { echo "Небезопасный или отсутствующий static root: $APP_ROOT" >&2; exit 1; }
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"
[[ "$APP_ROOT" != "/" ]] || { echo "Отказ: static root не может быть /." >&2; exit 1; }

HTML_TARGET="$APP_ROOT/ai-home-v2-voice-preview.html"
JS_TARGET="$APP_ROOT/ai-home-v2-voice.js"
for target in "$HTML_TARGET" "$JS_TARGET"; do
  [[ ! -L "$target" ]] || { echo "Отказ: preview target является symlink: $target" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-voice-preview.XXXXXX)"
HAD_HTML=0
HAD_JS=0
INSTALLED=0
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ "$INSTALLED" == 1 ]]; then
    echo "Ошибка установки voice preview: возвращаю предыдущие preview-файлы." >&2
    if [[ "$HAD_HTML" == 1 ]]; then cp -a -- "$TMP_DIR/old.html" "$HTML_TARGET" || true; else rm -f -- "$HTML_TARGET" || true; fi
    if [[ "$HAD_JS" == 1 ]]; then cp -a -- "$TMP_DIR/old.js" "$JS_TARGET" || true; else rm -f -- "$JS_TARGET" || true; fi
  fi
  rm -rf -- "$TMP_DIR"
  exit "$rc"
}
trap cleanup EXIT INT TERM

if [[ -f "$HTML_TARGET" ]]; then HAD_HTML=1; cp -a -- "$HTML_TARGET" "$TMP_DIR/old.html"; fi
if [[ -f "$JS_TARGET" ]]; then HAD_JS=1; cp -a -- "$JS_TARGET" "$TMP_DIR/old.js"; fi

protected_snapshot() {
  local name path
  for name in index.html manual.html app.js styles.css sw.js sync.js ai-home-v2.js ai-home-v2.css; do
    path="$APP_ROOT/$name"
    if [[ -f "$path" && ! -L "$path" ]]; then sha256sum "$path"; fi
  done
}
BEFORE_PROTECTED="$(protected_snapshot)"

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/index.html" -o "$TMP_DIR/index.html"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/ai-home-v2.js" -o "$TMP_DIR/ai-home-v2.js"

verify_git_blob() {
  local file="$1" expected="$2" actual
  actual="$(python3 - "$file" <<'PY'
from pathlib import Path
import hashlib, sys
p=Path(sys.argv[1]); data=p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)"
  [[ "$actual" == "$expected" ]] || { echo "Immutable payload mismatch: $(basename "$file") ($actual)" >&2; exit 1; }
}
verify_git_blob "$TMP_DIR/index.html" "$HTML_BLOB"
verify_git_blob "$TMP_DIR/ai-home-v2.js" "$JS_BLOB"

grep -Fq '/ai-home-v2-voice.js?v=20260906-1' "$TMP_DIR/index.html"
grep -Fq '/ai-home-v2.css?v=20260905-3.1' "$TMP_DIR/index.html"
grep -Fq 'getUserMedia({ audio: true })' "$TMP_DIR/ai-home-v2.js"
grep -Fq 'stopMicrophoneStream' "$TMP_DIR/ai-home-v2.js"
if grep -Eq 'MutationObserver|setInterval[[:space:]]*\(|serviceWorker|caches[[:space:]]*\.|innerHTML[[:space:]]*=' "$TMP_DIR/ai-home-v2.js"; then
  echo "Voice preview нарушает изоляционные инварианты." >&2
  exit 1
fi

if [[ "${DVIZH_AI_HOME_VOICE_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "Voice preview payload verified: $PAYLOAD_REF"
  exit 0
fi

INSTALLED=1
cp -- "$TMP_DIR/index.html" "$TMP_DIR/new.html"
cp -- "$TMP_DIR/ai-home-v2.js" "$TMP_DIR/new.js"
chmod 0644 "$TMP_DIR/new.html" "$TMP_DIR/new.js"
mv -f -- "$TMP_DIR/new.html" "$HTML_TARGET"
mv -f -- "$TMP_DIR/new.js" "$JS_TARGET"

AFTER_PROTECTED="$(protected_snapshot)"
[[ "$BEFORE_PROTECTED" == "$AFTER_PROTECTED" ]] || {
  echo "Защищённые production-файлы изменились во время установки; откат preview." >&2
  exit 1
}
[[ "$(python3 - "$HTML_TARGET" <<'PY'
from pathlib import Path
import hashlib, sys
p=Path(sys.argv[1]); data=p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)" == "$HTML_BLOB" ]]
[[ "$(python3 - "$JS_TARGET" <<'PY'
from pathlib import Path
import hashlib, sys
p=Path(sys.argv[1]); data=p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)" == "$JS_BLOB" ]]

INSTALLED=0
trap - EXIT INT TERM
rm -rf -- "$TMP_DIR"
cat <<EOF
Voice preview установлен: $VERSION
Payload: $PAYLOAD_REF
HTML: $HTML_TARGET
JS: $JS_TARGET
Production root/manual/app/sync/AI Home assets НЕ изменены. Сервисы, БД, state и auth не трогались.
EOF
