#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.08.29-webweek.1"
BRANCH="codex/dvizh-web-week-v1-2026-08-29"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BRANCH}/dvizh-web-week-v1"
APP_DIR="/opt/dvizh-auth"
AUTH_MAIN="$APP_DIR/auth_gateway.py"
WEEK_MODULE="$APP_DIR/week_web.py"
DATA_DIR="/var/lib/dvizh"
TG_DB="$DATA_DIR/telegram.db"
BACKUP_DIR="$DATA_DIR/backups/webweek-$(date -u +%Y%m%dT%H%M%SZ)"
TMP_DIR="$(mktemp -d /tmp/dvizh-webweek.XXXXXX)"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  SELF_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BRANCH}/install-dvizh-web-week.sh"
  tmp_self="$(mktemp /tmp/dvizh-webweek-self.XXXXXX.sh)"
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$SELF_URL" -o "$tmp_self"
  chmod 0755 "$tmp_self"
  exec sudo -n bash "$tmp_self" "$@"
fi

cleanup() { rm -rf "$TMP_DIR"; }
rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then cleanup; return 0; fi
  echo "Ошибка. Возвращаю предыдущую auth-gateway сборку..." >&2
  if [[ -f "$BACKUP_DIR/auth_gateway.py" ]]; then
    install -m 0755 -o root -g root "$BACKUP_DIR/auth_gateway.py" "$AUTH_MAIN"
  fi
  if [[ -f "$BACKUP_DIR/week_web.py" ]]; then
    install -m 0644 -o root -g root "$BACKUP_DIR/week_web.py" "$WEEK_MODULE"
  else
    rm -f "$WEEK_MODULE"
  fi
  systemctl restart dvizh-auth.service >/dev/null 2>&1 || true
  cleanup
  exit "$code"
}
trap rollback ERR INT TERM
trap cleanup EXIT

for required in "$AUTH_MAIN" "$TG_DB"; do
  [[ -f "$required" ]] || { echo "Не найден обязательный файл: $required" >&2; exit 1; }
done
systemctl is-active --quiet dvizh.service
systemctl is-active --quiet dvizh-auth.service
systemctl is-active --quiet dvizh-telegram.service

mkdir -p "$TMP_DIR"
for file in week_web.py patch_auth_gateway.py; do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/$file" -o "$TMP_DIR/$file"
done
python3 -m py_compile "$TMP_DIR/week_web.py" "$TMP_DIR/patch_auth_gateway.py"

python3 - "$TG_DB" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    missing={'schedule_items','schedule_occurrences'}-tables
    if missing:
        raise SystemExit('weekly schema missing: '+','.join(sorted(missing)))
    result=db.execute('PRAGMA integrity_check').fetchone()[0]
    if result!='ok': raise SystemExit('telegram.db integrity='+result)
print('weekly schema + telegram.db integrity=ok')
PY

echo "[1/4] Делаю резервную копию auth gateway..."
install -d -m 0700 "$BACKUP_DIR"
cp -a "$AUTH_MAIN" "$BACKUP_DIR/auth_gateway.py"
[[ -f "$WEEK_MODULE" ]] && cp -a "$WEEK_MODULE" "$BACKUP_DIR/week_web.py"
python3 - "$TG_DB" "$BACKUP_DIR/telegram.db" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as src, sqlite3.connect(sys.argv[2]) as dst:
    src.backup(dst)
    result=dst.execute('PRAGMA integrity_check').fetchone()[0]
if result!='ok': raise SystemExit('backup integrity='+result)
print('backup integrity=ok')
PY
chmod 0600 "$BACKUP_DIR/telegram.db"

echo "[2/4] Добавляю веб-неделю к существующему логину ДВИЖа..."
install -m 0644 -o root -g root "$TMP_DIR/week_web.py" "$WEEK_MODULE"
python3 "$TMP_DIR/patch_auth_gateway.py" "$AUTH_MAIN"
python3 -m py_compile "$AUTH_MAIN" "$WEEK_MODULE"
printf '%s\n' "$VERSION" > "$APP_DIR/WEB_WEEK_VERSION"
chmod 0644 "$APP_DIR/WEB_WEEK_VERSION"

echo "[3/4] Перезапускаю только auth gateway..."
systemctl restart dvizh-auth.service
for _ in $(seq 1 30); do
  systemctl is-active --quiet dvizh-auth.service && curl -fsS --max-time 3 http://127.0.0.1:8002/auth/health >/dev/null 2>&1 && break
  sleep 1
done
systemctl is-active --quiet dvizh-auth.service
curl -fsS --max-time 5 http://127.0.0.1:8002/auth/health
printf '\n'
code="$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8002/week)"
[[ "$code" == "303" ]] || { echo "Неожиданный HTTP код /week без сессии: $code" >&2; exit 1; }

echo "[4/4] Проверяю базы и остальные службы..."
systemctl is-active --quiet dvizh.service
systemctl is-active --quiet dvizh-telegram.service
systemctl is-active --quiet dvizh-bridge.service
python3 - "$TG_DB" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    print('telegram.db integrity='+db.execute('PRAGMA integrity_check').fetchone()[0])
    print('schedule_items='+str(db.execute('SELECT COUNT(*) FROM schedule_items').fetchone()[0]))
    print('schedule_occurrences='+str(db.execute('SELECT COUNT(*) FROM schedule_occurrences').fetchone()[0]))
PY

cat > /usr/local/sbin/dvizh-web-week-info <<'INFO'
#!/usr/bin/env bash
set -u
printf 'auth: '; systemctl is-active dvizh-auth.service 2>/dev/null || true
printf 'telegram: '; systemctl is-active dvizh-telegram.service 2>/dev/null || true
printf 'bridge: '; systemctl is-active dvizh-bridge.service 2>/dev/null || true
printf 'version: '; cat /opt/dvizh-auth/WEB_WEEK_VERSION 2>/dev/null || true
python3 - <<'PY'
import sqlite3
with sqlite3.connect('/var/lib/dvizh/telegram.db') as db:
    print('integrity:',db.execute('PRAGMA integrity_check').fetchone()[0])
    print('schedule items:',db.execute('SELECT COUNT(*) FROM schedule_items').fetchone()[0])
    print('schedule occurrences:',db.execute('SELECT COUNT(*) FROM schedule_occurrences').fetchone()[0])
PY
INFO
chmod 0755 /usr/local/sbin/dvizh-web-week-info

SUCCESS=1
trap - ERR INT TERM
cleanup

echo
echo "DVIZH web week $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Открой обычный ДВИЖ и нажми 🗓 Неделя, либо открой /week."
