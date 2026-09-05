#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-ai-home-v2-preview-bootstrap.2"
RELEASE_COMMIT="86c6f20d887551c77dd5ffe140da928b16370582"
DEFAULT_BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${RELEASE_COMMIT}"
BASE_URL="${DVIZH_AI_HOME_V2_BOOTSTRAP_BASE_URL:-$DEFAULT_BASE_URL}"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"

[[ $# -eq 0 ]] || { echo "Этот bootstrap не принимает аргументы и никогда не переключает главную." >&2; exit 1; }
if [[ -n "${DVIZH_AI_HOME_V2_BOOTSTRAP_BASE_URL:-}" && -z "$TEST_ROOT" ]]; then
  echo "Переопределение источника разрешено только в тестовом root." >&2
  exit 1
fi
if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через sudo: bootstrap устанавливает только отдельный preview." >&2
  exit 1
fi
for tool in curl python3 bash; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-v2-preview.XXXXXX)"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT
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
  local file="$1" expected="$2"
  local actual
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
verify_git_blob "$TMP_DIR/ai-home-v2/ai-home-v2.js" "e33dd200b00d3557dac3839beb5bc2537f4c1868"
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

if [[ -z "$TEST_ROOT" ]]; then
  python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
p = Path('/var/lib/dvizh/ai-home-status.json')
if not p.is_file():
    raise SystemExit('dvizh-ai-home-status.json отсутствует: live Hermes bridge ещё не подтвердил работу')
try:
    data = json.loads(p.read_text(encoding='utf-8'))
except Exception as exc:
    raise SystemExit(f'Некорректный ai-home-status.json: {exc}')
if data.get('ok') is not True:
    raise SystemExit('Live Hermes bridge сейчас сообщает ошибку; preview не устанавливался')
if not str(data.get('model') or '').strip():
    raise SystemExit('Live Hermes bridge не сообщает модель')
raw = str(data.get('at') or '').strip().replace('Z', '+00:00')
try:
    at = datetime.fromisoformat(raw)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - at.astimezone(timezone.utc)).total_seconds()
except Exception as exc:
    raise SystemExit(f'Некорректное время статуса Hermes bridge: {exc}')
if age < -10 or age > 60:
    raise SystemExit(f'Статус Hermes bridge устарел ({age:.0f} сек.); preview не устанавливался')
PY
fi

snapshot_file() {
  local name="$1"
  if [[ -f "$APP_ROOT/$name" ]]; then
    python3 - "$APP_ROOT/$name" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
print(hashlib.sha256(p.read_bytes()).hexdigest())
PY
  else
    printf '%s\n' ABSENT
  fi
}

INDEX_BEFORE="$(snapshot_file index.html)"
APP_BEFORE="$(snapshot_file app.js)"
CSS_BEFORE="$(snapshot_file styles.css)"
SW_BEFORE="$(snapshot_file sw.js)"
MANUAL_BEFORE="$(snapshot_file manual.html)"

chmod 0755 "$TMP_DIR/install-dvizh-ai-home-v2.sh"
DVIZH_AI_HOME_V2_SOURCE_DIR="$TMP_DIR/ai-home-v2" \
  bash "$TMP_DIR/install-dvizh-ai-home-v2.sh" --check
DVIZH_AI_HOME_V2_SOURCE_DIR="$TMP_DIR/ai-home-v2" \
  bash "$TMP_DIR/install-dvizh-ai-home-v2.sh" --install-preview

[[ "$(snapshot_file index.html)" == "$INDEX_BEFORE" ]] || { echo "Bootstrap изменил главную /." >&2; exit 1; }
[[ "$(snapshot_file app.js)" == "$APP_BEFORE" ]] || { echo "Bootstrap изменил app.js." >&2; exit 1; }
[[ "$(snapshot_file styles.css)" == "$CSS_BEFORE" ]] || { echo "Bootstrap изменил styles.css." >&2; exit 1; }
[[ "$(snapshot_file sw.js)" == "$SW_BEFORE" ]] || { echo "Bootstrap изменил sw.js." >&2; exit 1; }
[[ "$(snapshot_file manual.html)" == "$MANUAL_BEFORE" ]] || { echo "Bootstrap изменил manual.html." >&2; exit 1; }
cmp -s "$TMP_DIR/ai-home-v2/index.html" "$APP_ROOT/ai-home-v2-preview.html"
cmp -s "$TMP_DIR/ai-home-v2/ai-home-v2.js" "$APP_ROOT/ai-home-v2.js"
cmp -s "$TMP_DIR/ai-home-v2/ai-home-v2.css" "$APP_ROOT/ai-home-v2.css"

echo
echo "AI Home v2 preview готов: /ai-home-v2-preview.html"
echo "Release: $RELEASE_COMMIT ($VERSION)"
echo "Главная /, manual.html, app.js, styles.css, sw.js, БД и сервисы не изменены."
echo "Preview использует существующий same-origin /api/state и уже работающий dvizh-ai-home.service -> Hermes."
