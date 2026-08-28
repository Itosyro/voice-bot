#!/usr/bin/env bash
set -Eeuo pipefail

PAYLOAD_COMMIT="ffe71c3f1305e5517b0cd717401113e2a6055822"
PAYLOAD_URL="https://codeload.github.com/Itosyro/voice-bot/tar.gz/${PAYLOAD_COMMIT}"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти установщик через sudo: curl -fsSL <url> | sudo bash" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[1/6] Проверяю систему..."
if ! command -v curl >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates tar
fi
if ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq python3-venv
fi

echo "[2/6] Скачиваю зафиксированную сборку ДВИЖ Telegram..."
curl --proto '=https' --tlsv1.2 -fsSL --retry 4 --retry-delay 2 "$PAYLOAD_URL" -o "$TMP_DIR/payload.tar.gz"
tar -xzf "$TMP_DIR/payload.tar.gz" -C "$TMP_DIR"
SOURCE_DIR="$(find "$TMP_DIR" -type d -path '*/dvizh-telegram-v1' -print -quit)"
if [[ -z "$SOURCE_DIR" || ! -f "$SOURCE_DIR/telegram_bot/main.py" ]]; then
  echo "Не удалось найти файлы Telegram-модуля в архиве." >&2
  exit 1
fi

echo "[3/6] Проверяю Python-код..."
python3 -m compileall -q "$SOURCE_DIR/telegram_bot"

echo "[4/6] Устанавливаю модуль отдельно от веб-ДВИЖа..."
bash "$SOURCE_DIR/scripts/install.sh" "$SOURCE_DIR"

echo "[5/6] Проверяю установленную сборку и SQLite..."
/opt/dvizh-telegram/.venv/bin/python -m compileall -q /opt/dvizh-telegram/telegram_bot
sudo -u dvizh /opt/dvizh-telegram/.venv/bin/python - <<'PY'
import tempfile
from pathlib import Path
from telegram_bot.db import Database

with tempfile.TemporaryDirectory(dir='/var/lib/dvizh') as tmp:
    db = Database(str(Path(tmp) / 'smoke.db'))
    assert db.authorized_count() == 0
print('Python + SQLite: OK')
PY

PAIR_CODE="$(sed -n 's/^DVIZH_TELEGRAM_PAIR_CODE=//p' /etc/dvizh/telegram.env | head -n1)"
cat >/usr/local/sbin/dvizh-telegram-info <<'SH'
#!/usr/bin/env bash
set -Eeuo pipefail
pair="$(sudo -n sed -n 's/^DVIZH_TELEGRAM_PAIR_CODE=//p' /etc/dvizh/telegram.env | head -n1)"
echo "PAIR_CODE=$pair"
sudo -n systemctl --no-pager --full status dvizh-telegram.service 2>/dev/null | sed -n '1,12p' || true
SH
chmod 0755 /usr/local/sbin/dvizh-telegram-info

echo "[6/6] Готово. Веб-ДВИЖ не перезапускался и его база не менялась."
echo
echo "PAIR_CODE=$PAIR_CODE"
echo
echo "Теперь выполни одну команду и вставь token от BotFather скрытым вводом:"
echo "  sudo dvizh-telegram-set-token"
echo
echo "После запуска бота открой его в Telegram и отправь:"
echo "  /start $PAIR_CODE"
