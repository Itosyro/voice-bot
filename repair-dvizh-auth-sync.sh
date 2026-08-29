#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.08.29-auth-sync-repair.1"
ENV_FILE="/etc/dvizh/bridge.env"
IDENTITY_FILE="/var/lib/dvizh/auth-identity.json"
DATA_DIR="/var/lib/dvizh"
BACKUP_DIR="$DATA_DIR/backups/auth-sync-$(date -u +%Y%m%dT%H%M%SZ)"
WEEK_STATUS="$DATA_DIR/weekly-web-status.json"
BRIDGE_STATUS="$DATA_DIR/bridge-status.json"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 1
fi

rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then return 0; fi
  echo "Ошибка. Возвращаю прежний identity bridge..." >&2
  if [[ -f "$BACKUP_DIR/bridge.env" ]]; then
    cp -a "$BACKUP_DIR/bridge.env" "$ENV_FILE"
  fi
  systemctl restart dvizh-bridge.service >/dev/null 2>&1 || true
  systemctl restart dvizh-web-week.service >/dev/null 2>&1 || true
  exit "$code"
}
trap rollback ERR INT TERM

for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service; do
  systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
done
[[ -f "$ENV_FILE" ]] || { echo "Не найден $ENV_FILE" >&2; exit 1; }
[[ -f "$IDENTITY_FILE" ]] || { echo "Не найден $IDENTITY_FILE — сначала войди в новый аккаунт ДВИЖа." >&2; exit 1; }

install -d -m 0700 "$BACKUP_DIR"
cp -a "$ENV_FILE" "$BACKUP_DIR/bridge.env"

echo "[1/4] Сверяю старый bridge ID с новым аккаунтом ДВИЖа..."
python3 - "$IDENTITY_FILE" "$ENV_FILE" <<'PY'
from __future__ import annotations
import hashlib
import json
import os
import shlex
import sys
from pathlib import Path

identity_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
payload = json.loads(identity_path.read_text(encoding='utf-8'))

ID_KEYS = ('web_user_id','webUserId','user_id','userId','subject','uid')
EMAIL_KEYS = ('email','user_email','userEmail')

def find(value, keys):
    if isinstance(value, dict):
        for key in keys:
            item = value.get(key)
            if isinstance(item, (str, int)) and str(item).strip():
                return str(item).strip()
        for item in value.values():
            result = find(item, keys)
            if result:
                return result
    elif isinstance(value, list):
        for item in value:
            result = find(item, keys)
            if result:
                return result
    return None

new_id = find(payload, ID_KEYS)
new_email = find(payload, EMAIL_KEYS) or 'local-account@dvizh.invalid'
if not new_id:
    raise SystemExit('В auth-identity.json не найден стабильный user ID')

old_values = {}
for raw in env_path.read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    key, value = line.split('=', 1)
    try:
        parts = shlex.split(value.strip(), posix=True)
        old_values[key.strip()] = parts[0] if parts else ''
    except ValueError:
        old_values[key.strip()] = value.strip().strip('"\'')
old_id = old_values.get('DVIZH_WEB_USER_ID','')

mask = lambda text: hashlib.sha256(text.encode()).hexdigest()[:10] if text else '—'
print('old bridge identity:', mask(old_id))
print('auth account identity:', mask(new_id))
print('identity changed:', 'yes' if old_id != new_id else 'no')

lines = [
    line for line in env_path.read_text(encoding='utf-8').splitlines()
    if not line.startswith('DVIZH_WEB_USER_ID=') and not line.startswith('DVIZH_WEB_USER_EMAIL=')
]
quote = lambda text: json.dumps(str(text), ensure_ascii=False)
lines.append('DVIZH_WEB_USER_ID=' + quote(new_id))
lines.append('DVIZH_WEB_USER_EMAIL=' + quote(new_email))
tmp = env_path.with_suffix(env_path.suffix + '.tmp')
tmp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
os.chmod(tmp, 0o640)
os.replace(tmp, env_path)
PY
chown root:dvizh "$ENV_FILE"
chmod 0640 "$ENV_FILE"

echo "[2/4] Перезапускаю оба моста уже с identity нового аккаунта..."
rm -f "$WEEK_STATUS" "$BRIDGE_STATUS" "$DATA_DIR/bridge-sync-now"
systemctl restart dvizh-bridge.service
systemctl restart dvizh-web-week.service
systemctl is-active --quiet dvizh-bridge.service
systemctl is-active --quiet dvizh-web-week.service

echo "[3/4] Жду, пока расписание реально появится в состоянии нового аккаунта..."
SYNC_OK=0
for _ in $(seq 1 60); do
  if [[ -f "$WEEK_STATUS" ]] && python3 - "$WEEK_STATUS" <<'PY' >/dev/null 2>&1
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
raise SystemExit(0 if p.get('ok') and int(p.get('occurrences',0)) > 0 else 1)
PY
  then
    SYNC_OK=1
    break
  fi
  sleep 1
done
if [[ "$SYNC_OK" -ne 1 ]]; then
  echo "Недельный мост не подтвердил данные за 60 секунд." >&2
  [[ -f "$WEEK_STATUS" ]] && cat "$WEEK_STATUS" >&2 || true
  journalctl -u dvizh-web-week.service -n 30 --no-pager >&2 || true
  exit 1
fi

python3 - "$WEEK_STATUS" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print('web-week:', 'ok' if p.get('ok') else 'error')
print('mirrored items:', p.get('items',0))
print('mirrored occurrences:', p.get('occurrences',0))
print('web revision:', p.get('webRevision','—'))
PY

echo "[4/4] Проверяю службы и SQLite..."
python3 - <<'PY'
import sqlite3
for path in ('/var/lib/dvizh/dvizh.db','/var/lib/dvizh/telegram.db','/var/lib/dvizh/auth.db'):
    with sqlite3.connect(path) as db:
        result=db.execute('PRAGMA integrity_check').fetchone()[0]
    print(path.rsplit('/',1)[-1] + ' integrity=' + result)
    if result != 'ok':
        raise SystemExit(1)
PY
for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service; do
  printf '%s: ' "$unit"; systemctl is-active "$unit"
done

SUCCESS=1
trap - ERR INT TERM

echo
echo "DVIZH auth sync repair $VERSION complete."
echo "Backup: $BACKUP_DIR"
echo "Закрой веб-ДВИЖ полностью и открой заново. В «Неделя» должны появиться Telegram-события."
