#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR=/opt/dvizh-telegram
ENV_DIR=/etc/dvizh
DATA_DIR=/var/lib/dvizh
SOURCE_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"

if ! id dvizh >/dev/null 2>&1; then
  useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin dvizh
fi
install -d -m 0755 "$APP_DIR" "$ENV_DIR"
install -d -m 0750 -o dvizh -g dvizh "$DATA_DIR"

rm -rf "$APP_DIR/telegram_bot"
cp -a "$SOURCE_DIR/telegram_bot" "$APP_DIR/telegram_bot"
install -m 0644 "$SOURCE_DIR/requirements.txt" "$APP_DIR/requirements.txt"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$ENV_DIR/telegram.env" ]]; then
  install -m 0600 "$SOURCE_DIR/systemd/telegram.env.example" "$ENV_DIR/telegram.env"
  code="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(8))
PY
)"
  sed -i "s/replace-with-random-one-time-code/$code/" "$ENV_DIR/telegram.env"
  echo "Created $ENV_DIR/telegram.env"
  echo "PAIR_CODE=$code"
  echo "Set TELEGRAM_BOT_TOKEN before starting the service."
fi

install -m 0644 "$SOURCE_DIR/systemd/dvizh-telegram.service" /etc/systemd/system/dvizh-telegram.service
install -m 0755 "$SOURCE_DIR/scripts/configure-token.sh" /usr/local/sbin/dvizh-telegram-set-token
systemctl daemon-reload
echo "Unit installed but not started yet."
echo "Set the BotFather token with: sudo dvizh-telegram-set-token"
