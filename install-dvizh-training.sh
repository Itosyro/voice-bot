#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.08.30-training.1"
BRANCH="codex/dvizh-training-readiness-v1-2026-08-30"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BRANCH}/training-readiness-v1"
DATA_DIR="/var/lib/dvizh"
TG_DIR="/opt/dvizh-telegram/telegram_bot"
WEB_MODULE_DIR="/opt/dvizh-training/dvizh_training"
SERVICE_FILE="/etc/systemd/system/dvizh-training.service"
STATUS_FILE="$DATA_DIR/training-status.json"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$DATA_DIR/backups/training-$STAMP"
TMP_DIR="$(mktemp -d /tmp/dvizh-training.XXXXXX)"
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
  echo "Ошибка. Возвращаю интерфейс и Telegram-модули к предыдущей версии..." >&2
  systemctl disable --now dvizh-training.service >/dev/null 2>&1 || true
  if [[ -d "$BACKUP_DIR/static" ]]; then
    for name in index.html app.js styles.css sw.js; do
      [[ -f "$BACKUP_DIR/static/$name" ]] && cp -a "$BACKUP_DIR/static/$name" "$APP_ROOT/$name"
    done
  fi
  if [[ -d "$BACKUP_DIR/telegram" ]]; then
    for name in main.py keyboards.py readiness.py training_store.py training_router.py training_scheduler.py; do
      if [[ -f "$BACKUP_DIR/telegram/$name" ]]; then
        cp -a "$BACKUP_DIR/telegram/$name" "$TG_DIR/$name"
      else
        rm -f "$TG_DIR/$name"
      fi
    done
  fi
  if [[ -f "$BACKUP_DIR/dvizh-training.service" ]]; then
    cp -a "$BACKUP_DIR/dvizh-training.service" "$SERVICE_FILE"
  else
    rm -f "$SERVICE_FILE"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl restart dvizh-telegram.service >/dev/null 2>&1 || true
  cleanup
  exit "$code"
}
trap rollback ERR INT TERM
trap cleanup EXIT

for required in index.html app.js styles.css sw.js; do
  [[ -f "$APP_ROOT/$required" ]] || { echo "Не найден $APP_ROOT/$required" >&2; exit 1; }
done
for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service dvizh-web-editor.service; do
  systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
done
[[ -f "$DATA_DIR/telegram.db" ]] || { echo "Не найдена telegram.db" >&2; exit 1; }
[[ -f "$DATA_DIR/auth-identity.json" ]] || { echo "Не найден стабильный аккаунт ДВИЖа." >&2; exit 1; }
grep -q 'DVIZH_WEEK_EDITOR_V1' "$APP_ROOT/app.js"

mkdir -p "$TMP_DIR"
for file in __init__.py readiness.py training_store.py training_router.py training_scheduler.py main.py keyboards.py training_web_bridge.py patch_training_web.py dvizh-training.service; do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/$file" -o "$TMP_DIR/$file"
done
python3 -m py_compile "$TMP_DIR/readiness.py" "$TMP_DIR/training_store.py" "$TMP_DIR/training_web_bridge.py" "$TMP_DIR/patch_training_web.py"
/opt/dvizh-telegram/.venv/bin/python -m py_compile "$TMP_DIR/training_router.py" "$TMP_DIR/training_scheduler.py" "$TMP_DIR/main.py" "$TMP_DIR/keyboards.py"
python3 "$TMP_DIR/patch_training_web.py" --root "$APP_ROOT" --check

echo "[1/7] Делаю резервные копии интерфейса, Telegram-модулей и базы..."
install -d -m 0700 "$BACKUP_DIR/static" "$BACKUP_DIR/telegram"
for name in index.html app.js styles.css sw.js; do cp -a "$APP_ROOT/$name" "$BACKUP_DIR/static/$name"; done
for name in main.py keyboards.py readiness.py training_store.py training_router.py training_scheduler.py; do [[ -f "$TG_DIR/$name" ]] && cp -a "$TG_DIR/$name" "$BACKUP_DIR/telegram/$name"; done
[[ -f "$SERVICE_FILE" ]] && cp -a "$SERVICE_FILE" "$BACKUP_DIR/dvizh-training.service"
python3 - "$DATA_DIR/telegram.db" "$BACKUP_DIR/telegram.db" <<'PY'
import sqlite3,sys
source,target=sys.argv[1:]
with sqlite3.connect(source) as src, sqlite3.connect(target) as dst: src.backup(dst)
with sqlite3.connect(target) as db: result=db.execute('PRAGMA integrity_check').fetchone()[0]
if result!='ok': raise SystemExit('backup integrity='+result)
print('backup integrity=ok')
PY
chmod 0600 "$BACKUP_DIR/telegram.db"

echo "[2/7] Добавляю таблицы плана, готовности и тренировочной нагрузки..."
install -d -m 0755 /opt/dvizh-training "$WEB_MODULE_DIR"
for name in __init__.py readiness.py training_store.py; do install -m 0644 -o root -g root "$TMP_DIR/$name" "$WEB_MODULE_DIR/$name"; done
PYTHONPATH=/opt/dvizh-training python3 - "$DATA_DIR/telegram.db" <<'PY'
import sys
from dvizh_training.training_store import TrainingStore
store=TrainingStore(sys.argv[1])
with store.conn() as db:
    expected={'training_profiles','training_plan_slots','training_readiness','training_sessions','training_notifications','training_web_commands'}
    actual={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing=expected-actual
    if missing: raise SystemExit('missing training tables: '+','.join(sorted(missing)))
    result=db.execute('PRAGMA integrity_check').fetchone()[0]
    if result!='ok': raise SystemExit('telegram.db integrity='+result)
print('training schema=ok')
PY

echo "[3/7] Обновляю Telegram: готовность, план 4× и журнал тренировок..."
systemctl stop dvizh-telegram.service
for name in readiness.py training_store.py training_router.py training_scheduler.py main.py keyboards.py; do install -m 0644 -o root -g root "$TMP_DIR/$name" "$TG_DIR/$name"; done
/opt/dvizh-telegram/.venv/bin/python -m compileall -q "$TG_DIR"
systemctl start dvizh-telegram.service
systemctl is-active --quiet dvizh-telegram.service

echo "[4/7] Добавляю экран «Тренировки» в веб-ДВИЖ..."
python3 "$TMP_DIR/patch_training_web.py" --root "$APP_ROOT"
python3 "$TMP_DIR/patch_training_web.py" --root "$APP_ROOT" --check

echo "[5/7] Запускаю синхронизацию тренировок с единым аккаунтом..."
install -m 0644 -o root -g root "$TMP_DIR/__init__.py" "$WEB_MODULE_DIR/__init__.py"
install -m 0755 -o root -g root "$TMP_DIR/training_web_bridge.py" "$WEB_MODULE_DIR/training_web_bridge.py"
printf '%s\n' "$VERSION" > /opt/dvizh-training/VERSION
chmod 0644 /opt/dvizh-training/VERSION
install -m 0644 -o root -g root "$TMP_DIR/dvizh-training.service" "$SERVICE_FILE"
systemctl daemon-reload
rm -f "$STATUS_FILE"
systemctl enable --now dvizh-training.service >/dev/null
systemctl is-active --quiet dvizh-training.service

TRAINING_OK=0
for _ in $(seq 1 60); do
  if [[ -f "$STATUS_FILE" ]] && python3 - "$STATUS_FILE" <<'PY' >/dev/null 2>&1
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
raise SystemExit(0 if p.get('ok') else 1)
PY
  then TRAINING_OK=1; break; fi
  sleep 1
done
if [[ "$TRAINING_OK" -ne 1 ]]; then
  echo "Тренировочный мост не вышел в состояние ok." >&2
  [[ -f "$STATUS_FILE" ]] && cat "$STATUS_FILE" >&2 || true
  journalctl -u dvizh-training.service -n 40 --no-pager >&2 || true
  exit 1
fi
cat "$STATUS_FILE"

echo "[6/7] Проверяю интерфейс и базы..."
grep -q 'DVIZH_TRAINING_VIEW_V1' "$APP_ROOT/index.html"
grep -q 'DVIZH_TRAINING_WEB_V1' "$APP_ROOT/app.js"
grep -q 'DVIZH_TRAINING_WEB_V1' "$APP_ROOT/styles.css"
grep -q 'dvizh-training-web-v1' "$APP_ROOT/sw.js"
python3 - "$DATA_DIR/telegram.db" "$DATA_DIR/dvizh.db" "$DATA_DIR/auth.db" <<'PY'
import sqlite3,sys
for path in sys.argv[1:]:
    with sqlite3.connect(path) as db: result=db.execute('PRAGMA integrity_check').fetchone()[0]
    print(path.split('/')[-1]+' integrity='+result)
    if result!='ok': raise SystemExit(1)
PY
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
curl -fsS --max-time 8 http://127.0.0.1:8002/health >/dev/null

echo "[7/7] Проверяю все службы..."
for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service dvizh-web-editor.service dvizh-training.service; do
  printf '%s: ' "$unit"; systemctl is-active "$unit"
done

cat > /usr/local/sbin/dvizh-training-info <<'INFO'
#!/usr/bin/env bash
set -u
printf 'dvizh-training: '; systemctl is-active dvizh-training.service 2>/dev/null || true
[[ -f /var/lib/dvizh/training-status.json ]] && cat /var/lib/dvizh/training-status.json
INFO
chmod 0755 /usr/local/sbin/dvizh-training-info

SUCCESS=1
trap - ERR INT TERM
cleanup

echo
echo "DVIZH training readiness $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Telegram: /menu → 🏋️ Тренировки. Веб: полностью закрой ДВИЖ и открой снова → Тренировки."
