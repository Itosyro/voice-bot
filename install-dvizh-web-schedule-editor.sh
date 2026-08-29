#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.08.29-web-editor.1"
BRANCH="codex/dvizh-web-schedule-editor-v1-2026-08-29"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BRANCH}/web-week-editor-v1"
DATA_DIR="/var/lib/dvizh"
MODULE_DIR="/opt/dvizh-web-editor"
SERVICE_FILE="/etc/systemd/system/dvizh-web-editor.service"
STATUS_FILE="$DATA_DIR/web-editor-status.json"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$DATA_DIR/backups/web-editor-$STAMP"
TMP_DIR="$(mktemp -d /tmp/dvizh-web-editor.XXXXXX)"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 1
fi

APP_ROOT=""
if [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT="/opt/dvizh"
else
  echo "Не найден веб-интерфейс ДВИЖа." >&2
  exit 1
fi

cleanup() { rm -rf "$TMP_DIR"; }
rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then cleanup; return 0; fi
  echo "Ошибка. Возвращаю веб-редактор к предыдущему состоянию..." >&2
  systemctl disable --now dvizh-web-editor.service >/dev/null 2>&1 || true
  if [[ -d "$BACKUP_DIR/static" ]]; then
    for name in index.html app.js styles.css sw.js; do
      [[ -f "$BACKUP_DIR/static/$name" ]] && cp -a "$BACKUP_DIR/static/$name" "$APP_ROOT/$name"
    done
  fi
  if [[ -f "$BACKUP_DIR/dvizh-web-editor.service" ]]; then
    cp -a "$BACKUP_DIR/dvizh-web-editor.service" "$SERVICE_FILE"
  else
    rm -f "$SERVICE_FILE"
  fi
  if [[ -f "$BACKUP_DIR/web_schedule_editor_bridge.py" ]]; then
    install -m 0755 "$BACKUP_DIR/web_schedule_editor_bridge.py" "$MODULE_DIR/web_schedule_editor_bridge.py"
  else
    rm -f "$MODULE_DIR/web_schedule_editor_bridge.py"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  [[ -f "$BACKUP_DIR/dvizh-web-editor.service" ]] && systemctl enable --now dvizh-web-editor.service >/dev/null 2>&1 || true
  cleanup
  exit "$code"
}
trap rollback ERR INT TERM
trap cleanup EXIT

for required in index.html app.js styles.css sw.js; do
  [[ -f "$APP_ROOT/$required" ]] || { echo "Не найден $APP_ROOT/$required" >&2; exit 1; }
done
for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service; do
  systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
done
[[ -f "$DATA_DIR/telegram.db" ]] || { echo "Не найдена telegram.db" >&2; exit 1; }
[[ -f "$DATA_DIR/auth-identity.json" ]] || { echo "Не найден стабильный ID аккаунта ДВИЖа. Сначала войди через логин/пароль." >&2; exit 1; }
grep -q 'DVIZH_WEEK_VIEW_V1' "$APP_ROOT/index.html"
grep -q 'DVIZH_WEEK_WEB_V1' "$APP_ROOT/app.js"

mkdir -p "$TMP_DIR"
for file in patch_web_editor.py web_schedule_editor_bridge.py dvizh-web-editor.service; do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/$file" -o "$TMP_DIR/$file"
done
bash -n "$0" 2>/dev/null || true
python3 -m py_compile "$TMP_DIR/patch_web_editor.py" "$TMP_DIR/web_schedule_editor_bridge.py"
python3 "$TMP_DIR/patch_web_editor.py" --root "$APP_ROOT" --check

echo "[1/6] Делаю backup веб-интерфейса и Telegram-базы..."
install -d -m 0700 "$BACKUP_DIR/static"
for name in index.html app.js styles.css sw.js; do cp -a "$APP_ROOT/$name" "$BACKUP_DIR/static/$name"; done
[[ -f "$SERVICE_FILE" ]] && cp -a "$SERVICE_FILE" "$BACKUP_DIR/dvizh-web-editor.service"
[[ -f "$MODULE_DIR/web_schedule_editor_bridge.py" ]] && cp -a "$MODULE_DIR/web_schedule_editor_bridge.py" "$BACKUP_DIR/web_schedule_editor_bridge.py"
python3 - "$DATA_DIR/telegram.db" "$BACKUP_DIR/telegram.db" <<'PY'
import sqlite3,sys
source,target=sys.argv[1:]
with sqlite3.connect(source) as src, sqlite3.connect(target) as dst: src.backup(dst)
with sqlite3.connect(target) as db:
    result=db.execute('PRAGMA integrity_check').fetchone()[0]
if result!='ok': raise SystemExit('backup integrity='+result)
print('backup integrity=ok')
PY
chmod 0600 "$BACKUP_DIR/telegram.db"

echo "[2/6] Добавляю создание и редактирование событий в веб-ДВИЖ..."
python3 "$TMP_DIR/patch_web_editor.py" --root "$APP_ROOT"
python3 "$TMP_DIR/patch_web_editor.py" --root "$APP_ROOT" --check

echo "[3/6] Добавляю безопасную очередь команд веб → Telegram..."
python3 - "$DATA_DIR/telegram.db" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
    db.execute('''CREATE TABLE IF NOT EXISTS schedule_web_commands(
      command_id TEXT PRIMARY KEY,chat_id INTEGER NOT NULL,action TEXT NOT NULL,
      result TEXT NOT NULL,detail TEXT,processed_at_utc TEXT NOT NULL)''')
    result=db.execute('PRAGMA integrity_check').fetchone()[0]
    if result!='ok': raise SystemExit('telegram.db integrity='+result)
print('editor schema=ok')
PY
install -d -m 0755 -o root -g root "$MODULE_DIR"
install -m 0755 -o root -g root "$TMP_DIR/web_schedule_editor_bridge.py" "$MODULE_DIR/web_schedule_editor_bridge.py"
printf '%s\n' "$VERSION" > "$MODULE_DIR/VERSION"
chmod 0644 "$MODULE_DIR/VERSION"
install -m 0644 -o root -g root "$TMP_DIR/dvizh-web-editor.service" "$SERVICE_FILE"
systemctl daemon-reload
rm -f "$STATUS_FILE"
systemctl enable --now dvizh-web-editor.service >/dev/null

 echo "[4/6] Проверяю новый мост и стабильный аккаунт..."
EDITOR_OK=0
for _ in $(seq 1 40); do
  if [[ -f "$STATUS_FILE" ]] && python3 - "$STATUS_FILE" <<'PY' >/dev/null 2>&1
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
raise SystemExit(0 if p.get('ok') else 1)
PY
  then EDITOR_OK=1; break; fi
  sleep 1
done
if [[ "$EDITOR_OK" -ne 1 ]]; then
  echo "Веб-редактор не вышел в состояние ok." >&2
  [[ -f "$STATUS_FILE" ]] && cat "$STATUS_FILE" >&2 || true
  journalctl -u dvizh-web-editor.service -n 30 --no-pager >&2 || true
  exit 1
fi
cat "$STATUS_FILE"

echo "[5/6] Проверяю интерфейс и базы..."
grep -q 'DVIZH_WEEK_EDITOR_V1' "$APP_ROOT/index.html"
grep -q 'DVIZH_WEEK_EDITOR_V1' "$APP_ROOT/app.js"
grep -q 'DVIZH_WEEK_EDITOR_V1' "$APP_ROOT/styles.css"
grep -q 'dvizh-week-editor-v1' "$APP_ROOT/sw.js"
python3 - "$DATA_DIR/telegram.db" "$DATA_DIR/dvizh.db" "$DATA_DIR/auth.db" <<'PY'
import sqlite3,sys
for path in sys.argv[1:]:
    with sqlite3.connect(path) as db: result=db.execute('PRAGMA integrity_check').fetchone()[0]
    print(path.split('/')[-1]+' integrity='+result)
    if result!='ok': raise SystemExit(1)
PY
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:8002/health >/dev/null

echo "[6/6] Проверяю службы..."
for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service dvizh-web-editor.service; do
  printf '%s: ' "$unit"; systemctl is-active "$unit"
done

cat > /usr/local/sbin/dvizh-web-editor-info <<'INFO'
#!/usr/bin/env bash
set -u
printf 'dvizh-web-editor: '; systemctl is-active dvizh-web-editor.service 2>/dev/null || true
[[ -f /var/lib/dvizh/web-editor-status.json ]] && cat /var/lib/dvizh/web-editor-status.json
INFO
chmod 0755 /usr/local/sbin/dvizh-web-editor-info

SUCCESS=1
trap - ERR INT TERM
cleanup

echo
echo "DVIZH web schedule editor $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Полностью закрой ДВИЖ на телефоне и открой снова → Неделя."
