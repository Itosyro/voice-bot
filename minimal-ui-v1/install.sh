#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.04-minimal-ui.1"
PAYLOAD_DIR="${DVIZH_MINIMAL_UI_PAYLOAD_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)}"
PATCHER="$PAYLOAD_DIR/patch_minimal_ui.py"
DATA_DIR="/var/lib/dvizh"
MODULE_ROOT="/opt/dvizh-minimal-ui"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$DATA_DIR/backups/minimal-ui-$STAMP"
LOCK_FILE="/run/lock/dvizh-minimal-ui-install.lock"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n env DVIZH_MINIMAL_UI_PAYLOAD_DIR="$PAYLOAD_DIR" bash "$0" "$@"
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Другая установка ДВИЖа уже выполняется." >&2
  exit 1
fi

APP_ROOT=""
if [[ -f /opt/dvizh/static/index.html ]]; then APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then APP_ROOT="/opt/dvizh"
else echo "Не найден веб-интерфейс ДВИЖа." >&2; exit 1
fi

cleanup() { :; }
rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then return 0; fi
  echo "Ошибка. Возвращаю прежний дизайн ДВИЖа..." >&2
  if [[ -d "$BACKUP_DIR/static" ]]; then
    for name in index.html app.js styles.css sw.js; do
      [[ -f "$BACKUP_DIR/static/$name" ]] && cp -a "$BACKUP_DIR/static/$name" "$APP_ROOT/$name"
    done
  fi
  if [[ -d "$BACKUP_DIR/module" ]]; then
    rm -rf "$MODULE_ROOT"
    cp -a "$BACKUP_DIR/module" "$MODULE_ROOT"
  elif [[ -f "$BACKUP_DIR/.module-missing" ]]; then
    rm -rf "$MODULE_ROOT"
  fi
  exit "$code"
}
trap rollback ERR INT TERM
trap cleanup EXIT

required_units=(dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service dvizh-web-editor.service dvizh-training.service dvizh-jump.service dvizh-social.service)
for unit in "${required_units[@]}"; do
  systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
done
for name in index.html app.js styles.css sw.js; do
  [[ -f "$APP_ROOT/$name" ]] || { echo "Не найден $APP_ROOT/$name" >&2; exit 1; }
done
[[ -f "$PATCHER" ]] || { echo "Не найден $PATCHER" >&2; exit 1; }
grep -q 'DVIZH_SOCIAL_HUB_V1' "$APP_ROOT/app.js" || { echo "Сначала должен быть установлен модуль «Соцсети»." >&2; exit 1; }

python3 -m py_compile "$PATCHER"
python3 "$PATCHER" --root "$APP_ROOT" --check

echo "[1/4] Сохраняю текущий дизайн..."
install -d -m 0700 "$BACKUP_DIR/static"
for name in index.html app.js styles.css sw.js; do cp -a "$APP_ROOT/$name" "$BACKUP_DIR/static/$name"; done
if [[ -d "$MODULE_ROOT" ]]; then cp -a "$MODULE_ROOT" "$BACKUP_DIR/module"; else touch "$BACKUP_DIR/.module-missing"; fi

echo "[2/4] Включаю спокойный минимальный интерфейс..."
python3 "$PATCHER" --root "$APP_ROOT"
python3 "$PATCHER" --root "$APP_ROOT" --check

echo "[3/4] Проверяю итоговые файлы..."
grep -q 'DVIZH_MINIMAL_UI_V1' "$APP_ROOT/index.html"
grep -q 'DVIZH_MINIMAL_UI_V1' "$APP_ROOT/app.js"
grep -q 'DVIZH_MINIMAL_UI_V1' "$APP_ROOT/styles.css"
grep -q 'dvizh-minimal-ui-v1' "$APP_ROOT/sw.js"
if command -v node >/dev/null 2>&1; then node --check "$APP_ROOT/app.js" >/dev/null; fi

install -d -m 0755 "$MODULE_ROOT"
install -m 0644 "$PATCHER" "$MODULE_ROOT/patch_minimal_ui.py"
printf '%s\n' "$VERSION" > "$MODULE_ROOT/VERSION"
chmod 0644 "$MODULE_ROOT/VERSION"

echo "[4/4] Проверяю сайт и службы..."
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:8002/health >/dev/null
for unit in "${required_units[@]}"; do
  printf '%s: ' "$unit"; systemctl is-active "$unit"
done

SUCCESS=1
trap - ERR INT TERM

echo
echo "DVIZH minimal UI $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Полностью закрой ДВИЖ и открой снова. Спокойный режим включён по умолчанию."
echo "Вернуть полный вид можно: Ещё → Спокойный режим → Выключен."
