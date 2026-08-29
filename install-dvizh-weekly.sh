#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.08.29-weekly.1"
BRANCH="codex/dvizh-weekly-schedule-v1-2026-08-29"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BRANCH}/dvizh-weekly-v1"
TG_DIR="/opt/dvizh-telegram/telegram_bot"
VENV_PY="/opt/dvizh-telegram/.venv/bin/python"
DATA_DIR="/var/lib/dvizh"
DB="$DATA_DIR/telegram.db"
BACKUP_DIR="$DATA_DIR/backups/weekly-$(date -u +%Y%m%dT%H%M%SZ)"
TMP_DIR="$(mktemp -d /tmp/dvizh-weekly.XXXXXX)"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi

cleanup() { rm -rf "$TMP_DIR"; }
rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then cleanup; return 0; fi
  echo "Ошибка. Возвращаю предыдущие файлы Telegram-бота..." >&2
  if [[ -d "$BACKUP_DIR/runtime" ]]; then
    for name in main.py keyboards.py weekly_store.py weekly_router.py weekly_scheduler.py; do
      if [[ -f "$BACKUP_DIR/runtime/$name" ]]; then
        install -m 0644 "$BACKUP_DIR/runtime/$name" "$TG_DIR/$name"
      else
        rm -f "$TG_DIR/$name"
      fi
    done
  fi
  systemctl restart dvizh-telegram.service >/dev/null 2>&1 || true
  cleanup
  exit "$code"
}
trap rollback ERR INT TERM
trap cleanup EXIT

for required in "$TG_DIR/main.py" "$TG_DIR/keyboards.py" "$DB" "$VENV_PY"; do
  [[ -e "$required" ]] || { echo "Не найден обязательный файл: $required" >&2; exit 1; }
done
systemctl is-active --quiet dvizh-telegram.service

mkdir -p "$TMP_DIR"
for file in weekly_store.py weekly_router.py weekly_scheduler.py main.py keyboards.py; do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
    "$BASE_URL/$file" -o "$TMP_DIR/$file"
done
"$VENV_PY" -m py_compile "$TMP_DIR"/*.py

echo "[1/5] Делаю резервную копию Telegram-базы и текущих модулей..."
install -d -m 0700 "$BACKUP_DIR/runtime"
python3 - "$DB" "$BACKUP_DIR/telegram.db" <<'PY'
import sqlite3, sys
source, target = sys.argv[1], sys.argv[2]
with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
    src.backup(dst)
    result = dst.execute('PRAGMA integrity_check').fetchone()[0]
if result != 'ok':
    raise SystemExit(f'backup integrity={result}')
print('backup integrity=ok')
PY
chmod 0600 "$BACKUP_DIR/telegram.db"
for name in main.py keyboards.py weekly_store.py weekly_router.py weekly_scheduler.py; do
  [[ -f "$TG_DIR/$name" ]] && cp -a "$TG_DIR/$name" "$BACKUP_DIR/runtime/$name"
done

echo "[2/5] Устанавливаю недельный график..."
for file in weekly_store.py weekly_router.py weekly_scheduler.py main.py keyboards.py; do
  install -m 0644 -o root -g root "$TMP_DIR/$file" "$TG_DIR/$file"
done
"$VENV_PY" -m compileall -q "$TG_DIR"

echo "[3/5] Создаю таблицы расписания без изменения существующих задач..."
PYTHONPATH=/opt/dvizh-telegram "$VENV_PY" - <<'PY'
from telegram_bot.weekly_store import WeeklyStore
store = WeeklyStore('/var/lib/dvizh/telegram.db')
with store.conn() as db:
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'schedule_items' in tables
    assert 'schedule_occurrences' in tables
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print('weekly schema=ok')
PY

echo "[4/5] Перезапускаю только Telegram-бот..."
systemctl restart dvizh-telegram.service
for _ in $(seq 1 30); do
  systemctl is-active --quiet dvizh-telegram.service && break
  sleep 1
done
systemctl is-active --quiet dvizh-telegram.service
sleep 2
if journalctl -u dvizh-telegram.service --since '-10 seconds' --no-pager | grep -Eiq 'Traceback|ImportError|ModuleNotFoundError|SyntaxError'; then
  journalctl -u dvizh-telegram.service --since '-15 seconds' --no-pager >&2 || true
  exit 1
fi

echo "[5/5] Проверяю остальные службы ДВИЖа..."
systemctl is-active --quiet dvizh.service
systemctl is-active --quiet dvizh-auth.service
systemctl is-active --quiet dvizh-bridge.service
python3 - "$DB" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    print('telegram.db integrity=' + db.execute('PRAGMA integrity_check').fetchone()[0])
    print('schedule_items=' + str(db.execute('SELECT COUNT(*) FROM schedule_items').fetchone()[0]))
    print('schedule_occurrences=' + str(db.execute('SELECT COUNT(*) FROM schedule_occurrences').fetchone()[0]))
PY

cat > /usr/local/sbin/dvizh-weekly-info <<'INFO'
#!/usr/bin/env bash
set -u
printf 'dvizh-telegram: '; systemctl is-active dvizh-telegram.service 2>/dev/null || true
python3 - <<'PY'
import sqlite3
with sqlite3.connect('/var/lib/dvizh/telegram.db') as db:
    print('integrity:', db.execute('PRAGMA integrity_check').fetchone()[0])
    print('schedule items:', db.execute('SELECT COUNT(*) FROM schedule_items').fetchone()[0])
    print('schedule occurrences:', db.execute('SELECT COUNT(*) FROM schedule_occurrences').fetchone()[0])
PY
INFO
chmod 0755 /usr/local/sbin/dvizh-weekly-info

printf '%s\n' "$VERSION" > /opt/dvizh-telegram/WEEKLY_VERSION
chmod 0644 /opt/dvizh-telegram/WEEKLY_VERSION
SUCCESS=1
trap - ERR INT TERM
cleanup

echo
echo "DVIZH weekly schedule $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Открой Telegram → /menu. Появятся 🗓 Неделя, ➕ Событие и 🗂 Расписание."
