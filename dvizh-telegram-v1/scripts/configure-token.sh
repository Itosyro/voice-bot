#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE=/etc/dvizh/telegram.env
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Не найден $ENV_FILE. Сначала установи Telegram-модуль." >&2
  exit 1
fi

read -r -s -p "Вставь Telegram token от BotFather: " token
echo
if [[ ! "$token" =~ ^[0-9]{5,}:[A-Za-z0-9_-]{20,}$ ]]; then
  echo "Похоже, формат token неверный. Ничего не изменено." >&2
  exit 1
fi

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
found=0
while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" == TELEGRAM_BOT_TOKEN=* ]]; then
    printf 'TELEGRAM_BOT_TOKEN=%s\n' "$token" >> "$tmp"
    found=1
  else
    printf '%s\n' "$line" >> "$tmp"
  fi
done < "$ENV_FILE"
if [[ "$found" -eq 0 ]]; then
  printf 'TELEGRAM_BOT_TOKEN=%s\n' "$token" >> "$tmp"
fi
install -m 0600 -o root -g root "$tmp" "$ENV_FILE"
unset token
systemctl enable --now dvizh-telegram.service
sleep 1
systemctl --no-pager --full status dvizh-telegram.service | sed -n '1,14p'
echo
echo "Token сохранён только на сервере. В чат его отправлять не нужно."
