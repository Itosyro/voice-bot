#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.08.29-bridge.1"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/codex/dvizh-integration-transport-2026-08-29/dvizh-integration-v1"
APP_DIR="/opt/dvizh-integration"
TG_DIR="/opt/dvizh-telegram/telegram_bot"
ENV_DIR="/etc/dvizh"
DATA_DIR="/var/lib/dvizh"
BACKUPS_DIR="$DATA_DIR/backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$BACKUPS_DIR/integration-$STAMP"
TMP_DIR="$(mktemp -d /tmp/dvizh-integration.XXXXXX)"
LOCK_FILE="/run/lock/dvizh-integration.lock"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Другая установка ДВИЖа уже выполняется." >&2
  exit 1
fi

cleanup() {
  rm -rf "$TMP_DIR"
}

rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then
    cleanup
    return 0
  fi
  echo
  echo "Ошибка на этапе интеграции. Возвращаю Telegram-модуль к предыдущей версии..." >&2
  if [[ -d "$BACKUP_DIR/runtime" ]]; then
    for name in bot.py db.py main.py keyboards.py settings_router.py; do
      if [[ -f "$BACKUP_DIR/runtime/$name" ]]; then
        install -m 0644 "$BACKUP_DIR/runtime/$name" "$TG_DIR/$name"
      elif [[ "$name" == "settings_router.py" ]]; then
        rm -f "$TG_DIR/$name"
      fi
    done
  fi
  systemctl disable --now dvizh-bridge.service >/dev/null 2>&1 || true
  if [[ -f "$BACKUP_DIR/dvizh-bridge.service" ]]; then
    install -m 0644 "$BACKUP_DIR/dvizh-bridge.service" /etc/systemd/system/dvizh-bridge.service
  else
    rm -f /etc/systemd/system/dvizh-bridge.service
  fi
  systemctl daemon-reload || true
  systemctl restart dvizh-telegram.service || true
  cleanup
  exit "$code"
}
trap rollback ERR INT TERM
trap cleanup EXIT

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Не найден обязательный файл: $1" >&2
    exit 1
  fi
}

download() {
  local relative="$1"
  local output="$2"
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
    "$BASE_URL/$relative" -o "$output"
}

echo "[1/8] Проверяю работающий ДВИЖ..."
require_file /opt/dvizh/server.py
require_file "$DATA_DIR/dvizh.db"
require_file "$DATA_DIR/telegram.db"
require_file "$TG_DIR/bot.py"
require_file "$TG_DIR/db.py"
require_file "$TG_DIR/main.py"
require_file "$TG_DIR/keyboards.py"
systemctl is-active --quiet dvizh.service
systemctl is-active --quiet dvizh-telegram.service
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
id dvizh >/dev/null
install -d -m 0750 -o dvizh -g dvizh "$DATA_DIR" "$BACKUPS_DIR"

echo "[2/8] Скачиваю подписанную по версии сборку интеграции..."
mkdir -p "$TMP_DIR/telegram_patch" "$TMP_DIR/systemd"
download bridge.py "$TMP_DIR/bridge.py"
download runtime_patch.py "$TMP_DIR/runtime_patch.py"
download bridge.env.example "$TMP_DIR/bridge.env.example"
download telegram_patch/main.py "$TMP_DIR/telegram_patch/main.py"
download telegram_patch/keyboards.py "$TMP_DIR/telegram_patch/keyboards.py"
download telegram_patch/settings_router.py "$TMP_DIR/telegram_patch/settings_router.py"
download systemd/dvizh-bridge.service "$TMP_DIR/systemd/dvizh-bridge.service"
python3 -m py_compile "$TMP_DIR/bridge.py" "$TMP_DIR/runtime_patch.py"
"/opt/dvizh-telegram/.venv/bin/python" -m py_compile \
  "$TMP_DIR/telegram_patch/main.py" \
  "$TMP_DIR/telegram_patch/keyboards.py" \
  "$TMP_DIR/telegram_patch/settings_router.py"

echo "[3/8] Делаю согласованные резервные копии обеих баз..."
install -d -m 0700 -o root -g root "$BACKUP_DIR" "$BACKUP_DIR/runtime"
python3 - "$DATA_DIR/dvizh.db" "$BACKUP_DIR/dvizh.db" "$DATA_DIR/telegram.db" "$BACKUP_DIR/telegram.db" <<'PY'
import sqlite3
import sys
from pathlib import Path

pairs = [(Path(sys.argv[1]), Path(sys.argv[2])), (Path(sys.argv[3]), Path(sys.argv[4]))]
for source, target in pairs:
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as check:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"Backup integrity failed for {source}: {result}")
    target.chmod(0o600)
    print(f"backup ok: {source.name}")
PY
for name in bot.py db.py main.py keyboards.py settings_router.py; do
  [[ -f "$TG_DIR/$name" ]] && cp -a "$TG_DIR/$name" "$BACKUP_DIR/runtime/$name"
done
[[ -f /etc/systemd/system/dvizh-bridge.service ]] && cp -a /etc/systemd/system/dvizh-bridge.service "$BACKUP_DIR/dvizh-bridge.service"

echo "[4/8] Устанавливаю мост Telegram ↔ веб-ДВИЖ..."
install -d -m 0755 -o root -g root "$APP_DIR" "$ENV_DIR"
install -m 0755 -o root -g root "$TMP_DIR/bridge.py" "$APP_DIR/bridge.py"
printf '%s\n' "$VERSION" > "$APP_DIR/VERSION"
chmod 0644 "$APP_DIR/VERSION"
if [[ ! -f "$ENV_DIR/bridge.env" ]]; then
  install -m 0640 -o root -g dvizh "$TMP_DIR/bridge.env.example" "$ENV_DIR/bridge.env"
else
  chown root:dvizh "$ENV_DIR/bridge.env"
  chmod 0640 "$ENV_DIR/bridge.env"
fi
install -m 0644 -o root -g root "$TMP_DIR/systemd/dvizh-bridge.service" /etc/systemd/system/dvizh-bridge.service

echo "[5/8] Добавляю настройки и защиту от двойного таймера..."
python3 "$TMP_DIR/runtime_patch.py" --package "$TG_DIR"
install -m 0644 -o root -g root "$TMP_DIR/telegram_patch/main.py" "$TG_DIR/main.py"
install -m 0644 -o root -g root "$TMP_DIR/telegram_patch/keyboards.py" "$TG_DIR/keyboards.py"
install -m 0644 -o root -g root "$TMP_DIR/telegram_patch/settings_router.py" "$TG_DIR/settings_router.py"
"/opt/dvizh-telegram/.venv/bin/python" -m compileall -q "$TG_DIR"

cat > /usr/local/sbin/dvizh-integration-info <<'INFO'
#!/usr/bin/env bash
set -u
echo "DVIZH services:"
systemctl is-active dvizh.service 2>/dev/null || true
systemctl is-active dvizh-telegram.service 2>/dev/null || true
systemctl is-active dvizh-bridge.service 2>/dev/null || true
echo
if [[ -f /var/lib/dvizh/bridge-status.json ]]; then
  cat /var/lib/dvizh/bridge-status.json
else
  echo '{"ok":false,"error":"bridge status not created yet"}'
fi
INFO
chmod 0755 /usr/local/sbin/dvizh-integration-info

echo "[6/8] Перезапускаю только Telegram-модуль и запускаю мост..."
systemctl daemon-reload
systemctl enable dvizh-bridge.service >/dev/null
systemctl restart dvizh-telegram.service
systemctl restart dvizh-bridge.service

for _ in $(seq 1 30); do
  if systemctl is-active --quiet dvizh-telegram.service && systemctl is-active --quiet dvizh-bridge.service; then
    [[ -f "$DATA_DIR/bridge-status.json" ]] && break
  fi
  sleep 1
done
systemctl is-active --quiet dvizh.service
systemctl is-active --quiet dvizh-telegram.service
systemctl is-active --quiet dvizh-bridge.service

echo "[7/8] Проверяю базы, синхронизацию и отсутствие секретов в выводе..."
python3 - "$DATA_DIR/dvizh.db" "$DATA_DIR/telegram.db" <<'PY'
import sqlite3
import sys
for path in sys.argv[1:]:
    with sqlite3.connect(path) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise SystemExit(f"SQLite integrity failed: {path}: {result}")
print("SQLite integrity: ok")
PY
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null

STATUS_OK=0
if [[ -f "$DATA_DIR/bridge-status.json" ]]; then
  if python3 - "$DATA_DIR/bridge-status.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1], encoding='utf-8'))
print("bridge:", "ok" if p.get("ok") else "waiting" if p.get("waiting") else "error")
print("web revision:", p.get("webRevision", "—"))
print("mirrored tasks:", p.get("tasks", 0))
print("mirrored sessions:", p.get("sessions", 0))
print("mirrored proofs:", p.get("proofs", 0))
raise SystemExit(0 if p.get("ok") else 3 if p.get("waiting") else 1)
PY
  then
    STATUS_OK=1
  else
    result=$?
    if [[ "$result" -eq 3 ]]; then
      echo "Мост установлен и ждёт, пока ты один раз откроешь веб-ДВИЖ под своим exe.dev аккаунтом."
    else
      echo "Мост запущен, но первая синхронизация завершилась ошибкой." >&2
      journalctl -u dvizh-bridge.service -n 20 --no-pager >&2 || true
      exit 1
    fi
  fi
fi

echo "[8/8] Готово."
SUCCESS=1
trap - ERR INT TERM
cleanup

echo
echo "DVIZH integration $VERSION installed."
echo "Backup: $BACKUP_DIR"
if [[ "$STATUS_OK" -eq 1 ]]; then
  echo "Telegram и веб-ДВИЖ связаны. В боте нажми /menu → ⚙️ Настройки → Синхронизировать."
else
  echo "Открой https://rikarishi-dvizh.exe.xyz/ один раз, затем в боте отправь /sync."
fi
