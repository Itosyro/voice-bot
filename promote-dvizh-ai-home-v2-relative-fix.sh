#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-ai-home-v2-promote-relative-fix.1"
BASE_PROMOTE_COMMIT="575e174e9b2c1ad06c35fa2c428314f9ffaa2fa6"
BASE_PROMOTE_BLOB="81d8cbdaa351991f9e8bf0bd26ccac93b4a098d1"
DEFAULT_SOURCE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BASE_PROMOTE_COMMIT}/promote-dvizh-ai-home-v2-from-github.sh"
SOURCE_URL="${DVIZH_AI_HOME_V2_PATCH_SOURCE_URL:-$DEFAULT_SOURCE_URL}"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"

[[ $# -eq 0 ]] || { echo "Этот compatibility-wrapper не принимает аргументы." >&2; exit 1; }
if [[ -n "${DVIZH_AI_HOME_V2_PATCH_SOURCE_URL:-}" && -z "$TEST_ROOT" ]]; then
  echo "Переопределение исходного promote разрешено только в тестовом root." >&2
  exit 1
fi
for tool in curl python3 bash; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-v2-relative-fix.XXXXXX)"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
BASE_SCRIPT="$TMP_DIR/base-promote.sh"
PATCHED_SCRIPT="$TMP_DIR/promote-fixed.sh"

curl --fail --silent --show-error --location \
  --retry 4 --retry-delay 1 --connect-timeout 10 --max-time 60 \
  "$SOURCE_URL" -o "$BASE_SCRIPT"

python3 - "$BASE_SCRIPT" "$BASE_PROMOTE_BLOB" "$PATCHED_SCRIPT" <<'PY'
import hashlib
from pathlib import Path
import sys

src = Path(sys.argv[1])
expected_blob = sys.argv[2]
out = Path(sys.argv[3])
data = src.read_bytes()
actual_blob = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
if actual_blob != expected_blob:
    raise SystemExit(f"Исходный promote не совпадает с immutable blob: {actual_blob}")
text = data.decode("utf-8")
needle = "/?app\\\\.js"
count = text.count(needle)
if count != 4:
    raise SystemExit(f"Ожидалось 4 проверки app.js старого promote, найдено {count}")
text = text.replace(needle, r"(\\./|/)?app\\.js")
old_version = 'VERSION="2026.09.06-ai-home-v2-promote-bootstrap.1"'
if text.count(old_version) != 1:
    raise SystemExit("Не найден ожидаемый VERSION исходного promote")
text = text.replace(old_version, 'VERSION="2026.09.06-ai-home-v2-promote-bootstrap.2-relative-path"', 1)
out.write_text(text, encoding="utf-8")
PY

bash -n "$PATCHED_SCRIPT"
grep -Fq '(\./|/)?app\.js' "$PATCHED_SCRIPT"
grep -Fq 'автоматически возвращаю предыдущую главную' "$PATCHED_SCRIPT"
grep -Fq 'http://127.0.0.1:8000/manual.html' "$PATCHED_SCRIPT"
! grep -Eq 'systemctl[[:space:]]+(restart|start|stop|enable|disable|daemon-reload)' "$PATCHED_SCRIPT"

chmod 0755 "$PATCHED_SCRIPT"
echo "Применён compatibility-fix: старый ручной интерфейс может использовать ./app.js?v=..."
exec bash "$PATCHED_SCRIPT"
