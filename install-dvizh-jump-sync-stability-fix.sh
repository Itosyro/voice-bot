#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-jump-sync-stability.1"
TARGET="${DVIZH_JUMP_BRIDGE_PATH:-/opt/dvizh-jump/dvizh_jump/jump_web_bridge.py}"
TEST_MODE=0
if [[ -n "${DVIZH_JUMP_BRIDGE_PATH:-}" ]]; then
  TEST_MODE=1
elif [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Для установки в /opt нужен root." >&2
  exit 1
fi
[[ -f "$TARGET" && ! -L "$TARGET" ]] || { echo "Небезопасный или отсутствующий jump_web_bridge.py." >&2; exit 1; }

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT
cp -- "$TARGET" "$TMP_DIR/jump_web_bridge.py"
python3 - "$TMP_DIR/jump_web_bridge.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding='utf-8')
needle = '''    for key in ("syncedAt", "optimisticProfile", "optimisticMeasurements", "selectedDay"):
        result.pop(key, None)
    return result
'''
replacement = '''    for key in ("syncedAt", "optimisticProfile", "optimisticMeasurements", "selectedDay"):
        result.pop(key, None)
    packet = result.get("coachPacket")
    if isinstance(packet, dict):
        packet = dict(packet)
        packet.pop("exportedAt", None)
        result["coachPacket"] = packet
    return result
'''
if 'packet.pop("exportedAt", None)' in source:
    if replacement not in source:
        raise SystemExit('Обнаружен неполный или неизвестный jump sync-фикс.')
elif needle in source:
    source = source.replace(needle, replacement, 1)
else:
    raise SystemExit('Ожидаемый normalized-контракт не найден; источник не изменён.')
path.write_text(source, encoding='utf-8')
PY
python3 -m py_compile "$TMP_DIR/jump_web_bridge.py"
mv -f -- "$TMP_DIR/jump_web_bridge.py" "$TARGET"
if [[ "$TEST_MODE" == 1 ]]; then
  echo "Fixture patched: $VERSION"
else
  echo "Установлен $VERSION. Сервисы не перезапускались; state, БД и настройки не изменены."
fi
