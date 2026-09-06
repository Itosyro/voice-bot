#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-microphone-permissions-policy.1"
TARGET="${DVIZH_SERVER_PATH:-/opt/dvizh/server.py}"
TEST_MODE=0
if [[ -n "${DVIZH_SERVER_PATH:-}" ]]; then
  TEST_MODE=1
elif [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Для установки в /opt нужен root." >&2
  exit 1
fi
[[ -f "$TARGET" && ! -L "$TARGET" ]] || { echo "Небезопасный или отсутствующий server.py." >&2; exit 1; }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT
cp -- "$TARGET" "$TMP_DIR/server.py"
python3 - "$TMP_DIR/server.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding='utf-8')
old = 'self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")'
new = 'self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=(), payment=()")'
if new in source:
    if source.count(new) != 1:
        raise SystemExit('Обнаружено несколько или неизвестное состояние microphone policy.')
elif source.count(old) == 1:
    source = source.replace(old, new, 1)
else:
    raise SystemExit('Ожидаемый Permissions-Policy контракт не найден; источник не изменён.')
path.write_text(source, encoding='utf-8')
PY
python3 -m py_compile "$TMP_DIR/server.py"
mv -f -- "$TMP_DIR/server.py" "$TARGET"
if [[ "$TEST_MODE" == 1 ]]; then
  echo "Fixture patched: $VERSION"
else
  echo "Установлен $VERSION. app.js, manual.html, sync.js, sw.js, БД, state и сервисы не изменены."
fi
