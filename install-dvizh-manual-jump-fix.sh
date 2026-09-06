#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-manual-jump-sync.1"
TEST_ROOT="${DVIZH_MANUAL_JUMP_ROOT:-}"
if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/sync.js ]]; then
  APP_ROOT=/opt/dvizh/static
else
  echo "Не найден sync.js ручного режима." >&2
  exit 1
fi
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"
SYNC="$APP_ROOT/sync.js"
[[ -f "$SYNC" && ! -L "$SYNC" ]] || { echo "Небезопасный sync.js." >&2; exit 1; }
if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Для установки нужен root." >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT
cp -- "$SYNC" "$TMP_DIR/sync.js"
python3 - "$TMP_DIR/sync.js" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding='utf-8')
helper = """  function manualJumpRenderState(state) {
    const copy = clone(state);
    const packet = copy?.jumpLab?.coachPacket;
    if (packet && typeof packet === 'object') delete packet.exportedAt;
    return copy;
  }

"""
needle = """      const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
      const merged = queued ? mergeStates(local, remote.state) : normalizeState(remote.state);
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
"""
replacement = """      const local = normalizeState(safeParse(nativeGet.call(localStorage, STATE_KEY)));
      const merged = queued ? mergeStates(local, remote.state) : normalizeState(remote.state);
      const manualJumpChanged = JSON.stringify(manualJumpRenderState(local)) !== JSON.stringify(manualJumpRenderState(merged));
      nativeSet.call(localStorage, STATE_KEY, JSON.stringify(merged));
"""
reload = """      } else if (appLoaded) {
        window.setTimeout(() => location.reload(), 120);
      }
"""
reload_replacement = """      } else if (appLoaded && manualJumpChanged) {
        window.setTimeout(() => location.reload(), 120);
      }
"""
if 'function manualJumpRenderState(state)' in source:
    if replacement not in source or reload_replacement not in source:
        raise SystemExit('sync.js содержит неполный или неизвестный manual-jump фикс.')
elif needle in source and reload in source:
    source = source.replace('  async function pullLatest({ manual = false } = {}) {\n', helper + '  async function pullLatest({ manual = false } = {}) {\n', 1)
    source = source.replace(needle, replacement, 1)
    source = source.replace(reload, reload_replacement, 1)
else:
    raise SystemExit('Ожидаемый pullLatest-контракт не найден; sync.js не изменён.')
path.write_text(source, encoding='utf-8')
PY
node --check "$TMP_DIR/sync.js"
if [[ -n "$TEST_ROOT" ]]; then
  mv -f -- "$TMP_DIR/sync.js" "$SYNC"
  echo "Fixture patched: $VERSION"
  exit 0
fi
install -d -m 0700 /var/lib/dvizh/backups
BACKUP_DIR="$(mktemp -d /var/lib/dvizh/backups/manual-jump-sync.XXXXXX)"
cp -a -- "$SYNC" "$BACKUP_DIR/sync.js"
mv -f -- "$TMP_DIR/sync.js" "$SYNC"
echo "Установлен $VERSION. Backup: $BACKUP_DIR"
echo "Сервисы не перезапускались; app.js, manual.html, БД и настройки не изменены."
