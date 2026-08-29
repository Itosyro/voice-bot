#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.08.29-web-week.2"
BRANCH="codex/dvizh-weekly-schedule-v1-2026-08-29"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BRANCH}/web-week-v1"
APP_ROOT=""
if [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT="/opt/dvizh"
else
  echo "Не найден текущий веб-интерфейс ДВИЖа." >&2
  exit 1
fi
MODULE_DIR="/opt/dvizh-web-week"
DATA_DIR="/var/lib/dvizh"
STATUS_FILE="$DATA_DIR/weekly-web-status.json"
BACKUP_DIR="$DATA_DIR/backups/web-week-$(date -u +%Y%m%dT%H%M%SZ)"
SERVICE_FILE="/etc/systemd/system/dvizh-web-week.service"
TMP_DIR="$(mktemp -d /tmp/dvizh-web-week.XXXXXX)"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 1
fi

cleanup() { rm -rf "$TMP_DIR"; }
rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then cleanup; return 0; fi
  echo "Ошибка. Возвращаю веб-ДВИЖ к предыдущей версии..." >&2
  systemctl disable --now dvizh-web-week.service >/dev/null 2>&1 || true
  if [[ -d "$BACKUP_DIR/static" ]]; then
    for name in index.html app.js styles.css sw.js; do
      [[ -f "$BACKUP_DIR/static/$name" ]] && cp -a "$BACKUP_DIR/static/$name" "$APP_ROOT/$name"
    done
  fi
  if [[ -f "$BACKUP_DIR/dvizh-web-week.service" ]]; then
    cp -a "$BACKUP_DIR/dvizh-web-week.service" "$SERVICE_FILE"
  else
    rm -f "$SERVICE_FILE"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  cleanup
  exit "$code"
}
trap rollback ERR INT TERM
trap cleanup EXIT

for required in index.html app.js styles.css sw.js; do
  [[ -f "$APP_ROOT/$required" ]] || { echo "Не найден $APP_ROOT/$required" >&2; exit 1; }
done
for unit in dvizh.service dvizh-auth.service dvizh-telegram.service; do
  systemctl is-active --quiet "$unit"
done
[[ -f "$DATA_DIR/telegram.db" ]] || { echo "Не найдена Telegram-база" >&2; exit 1; }
python3 - "$DATA_DIR/telegram.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing={'schedule_items','schedule_occurrences'}-tables
    if missing: raise SystemExit('missing schedule tables: '+','.join(sorted(missing)))
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
print('weekly db=ok')
PY

mkdir -p "$TMP_DIR"
for file in patch_web.py weekly_web_bridge.py dvizh-web-week.service; do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/$file" -o "$TMP_DIR/$file"
done
python3 -m py_compile "$TMP_DIR/patch_web.py" "$TMP_DIR/weekly_web_bridge.py"
python3 "$TMP_DIR/patch_web.py" --root "$APP_ROOT" --check

# The existing backend and auth gateway are already live. Static assets are read
# from disk per request, so restarting dvizh.service here only creates a race in
# which the new bridge can observe a transient connection refusal.
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:8002/health >/dev/null

echo "[1/5] Делаю backup текущего веб-интерфейса..."
install -d -m 0700 "$BACKUP_DIR/static"
for name in index.html app.js styles.css sw.js; do cp -a "$APP_ROOT/$name" "$BACKUP_DIR/static/$name"; done
[[ -f "$SERVICE_FILE" ]] && cp -a "$SERVICE_FILE" "$BACKUP_DIR/dvizh-web-week.service"

echo "[2/5] Добавляю экран «Неделя» без замены остального приложения..."
python3 "$TMP_DIR/patch_web.py" --root "$APP_ROOT"
python3 "$TMP_DIR/patch_web.py" --root "$APP_ROOT" --check

echo "[3/5] Подключаю расписание Telegram к стабильному аккаунту ДВИЖа..."
install -d -m 0755 -o root -g root "$MODULE_DIR"
install -m 0755 -o root -g root "$TMP_DIR/weekly_web_bridge.py" "$MODULE_DIR/weekly_web_bridge.py"
printf '%s\n' "$VERSION" > "$MODULE_DIR/VERSION"
chmod 0644 "$MODULE_DIR/VERSION"
install -m 0644 -o root -g root "$TMP_DIR/dvizh-web-week.service" "$SERVICE_FILE"
systemctl daemon-reload
rm -f "$STATUS_FILE"
systemctl enable --now dvizh-web-week.service >/dev/null
systemctl is-active --quiet dvizh-web-week.service

echo "[4/5] Жду успешную синхронизацию и проверяю интерфейс..."
SYNC_OK=0
for _ in $(seq 1 60); do
  if [[ -f "$STATUS_FILE" ]] && python3 - "$STATUS_FILE" <<'PY' >/dev/null 2>&1
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
raise SystemExit(0 if p.get('ok') else 1)
PY
  then
    SYNC_OK=1
    break
  fi
  sleep 1
done
if [[ "$SYNC_OK" -ne 1 ]]; then
  echo "Мост не вышел в состояние ok за 60 секунд." >&2
  [[ -f "$STATUS_FILE" ]] && cat "$STATUS_FILE" >&2 || true
  journalctl -u dvizh-web-week.service -n 30 --no-pager >&2 || true
  exit 1
fi

grep -q 'DVIZH_WEEK_VIEW_V1' "$APP_ROOT/index.html"
grep -q 'DVIZH_WEEK_WEB_V1' "$APP_ROOT/app.js"
grep -q 'DVIZH_WEEK_WEB_V1' "$APP_ROOT/styles.css"
grep -q 'dvizh-week-web-v1' "$APP_ROOT/sw.js"
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:8002/health >/dev/null
python3 - "$DATA_DIR/telegram.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    print('telegram.db integrity='+db.execute('PRAGMA integrity_check').fetchone()[0])
    print('schedule_items='+str(db.execute('SELECT COUNT(*) FROM schedule_items').fetchone()[0]))
    print('schedule_occurrences='+str(db.execute('SELECT COUNT(*) FROM schedule_occurrences').fetchone()[0]))
PY
python3 - "$STATUS_FILE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print('web-week:', 'ok' if p.get('ok') else 'error')
print('mirrored items:', p.get('items',0))
print('mirrored occurrences:', p.get('occurrences',0))
print('web revision:', p.get('webRevision','—'))
if not p.get('ok'):
    print('detail:', p.get('error','—'))
    raise SystemExit(1)
PY

echo "[5/5] Проверяю все основные службы..."
for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service; do
  printf '%s: ' "$unit"; systemctl is-active "$unit"
done

cat > /usr/local/sbin/dvizh-web-week-info <<'INFO'
#!/usr/bin/env bash
set -u
printf 'dvizh-web-week: '; systemctl is-active dvizh-web-week.service 2>/dev/null || true
[[ -f /var/lib/dvizh/weekly-web-status.json ]] && cat /var/lib/dvizh/weekly-web-status.json
INFO
chmod 0755 /usr/local/sbin/dvizh-web-week-info

SUCCESS=1
trap - ERR INT TERM
cleanup

echo
echo "DVIZH web weekly $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Закрой ДВИЖ на телефоне, открой заново и выбери «Неделя»."
