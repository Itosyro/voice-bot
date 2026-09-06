#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-jump-sync-stability-release.1"
PAYLOAD_REF="a8b2d72ff8d21de1626cebcc5a57b7ced7b0753d"
PAYLOAD_BLOB="c86a6b531681b59018ab53b4536d12794e00fef5"
PAYLOAD_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/install-dvizh-jump-sync-stability-fix.sh"
TARGET="/opt/dvizh-jump/dvizh_jump/jump_web_bridge.py"
BACKUP_ROOT="/var/lib/dvizh/backups"

[[ $# -eq 0 ]] || { echo "Этот установщик не принимает аргументы." >&2; exit 1; }
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Для установки нужен root." >&2; exit 1; }
for tool in curl python3 systemctl mktemp cp mv install grep awk; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done
[[ -f "$TARGET" && ! -L "$TARGET" ]] || { echo "Небезопасный или отсутствующий $TARGET" >&2; exit 1; }

find_jump_service() {
  local unit text
  local -a matches=()
  for unit in dvizh-jump.service dvizh-jump-web.service dvizh-jump-bridge.service; do
    if systemctl cat "$unit" >/dev/null 2>&1; then
      printf '%s\n' "$unit"
      return 0
    fi
  done
  while read -r unit _; do
    [[ "$unit" == dvizh-*.service ]] || continue
    text="$(systemctl cat "$unit" 2>/dev/null || true)"
    if grep -Eq '/opt/dvizh-jump|jump_web_bridge|dvizh_jump' <<<"$text"; then
      matches+=("$unit")
    fi
  done < <(systemctl list-unit-files --type=service --no-legend 2>/dev/null || true)
  if [[ ${#matches[@]} -eq 1 ]]; then
    printf '%s\n' "${matches[0]}"
    return 0
  fi
  if [[ ${#matches[@]} -eq 0 ]]; then
    echo "Не найден systemd-сервис Jump Lab; ничего не изменено." >&2
  else
    echo "Найдено несколько возможных Jump Lab сервисов: ${matches[*]}; ничего не изменено." >&2
  fi
  return 1
}

SERVICE="$(find_jump_service)"
systemctl is-active --quiet "$SERVICE" || { echo "$SERVICE не active; ничего не изменено." >&2; exit 1; }

TMP_DIR="$(mktemp -d /tmp/dvizh-jump-sync-release.XXXXXX)"
BACKUP_DIR=""
PATCHED=0
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ $rc -ne 0 && "$PATCHED" == 1 && -n "$BACKUP_DIR" && -f "$BACKUP_DIR/jump_web_bridge.py" ]]; then
    echo "Ошибка после изменения: возвращаю backup." >&2
    cp -a -- "$BACKUP_DIR/jump_web_bridge.py" "$TARGET" || true
    systemctl restart "$SERVICE" || true
  fi
  rm -rf -- "$TMP_DIR"
  exit "$rc"
}
trap cleanup EXIT INT TERM

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$PAYLOAD_URL" -o "$TMP_DIR/payload.sh"
ACTUAL_BLOB="$(python3 - "$TMP_DIR/payload.sh" <<'PY'
from pathlib import Path
import hashlib, sys
p=Path(sys.argv[1]); data=p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)"
[[ "$ACTUAL_BLOB" == "$PAYLOAD_BLOB" ]] || { echo "Immutable payload mismatch: $ACTUAL_BLOB" >&2; exit 1; }
bash -n "$TMP_DIR/payload.sh"

install -d -m 0700 "$BACKUP_ROOT"
BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/jump-sync-stability.XXXXXX")"
chmod 0700 "$BACKUP_DIR"
cp -a -- "$TARGET" "$BACKUP_DIR/jump_web_bridge.py"

bash "$TMP_DIR/payload.sh"
PATCHED=1
chown --reference="$BACKUP_DIR/jump_web_bridge.py" "$TARGET"
chmod --reference="$BACKUP_DIR/jump_web_bridge.py" "$TARGET"
python3 -m py_compile "$TARGET"

echo "Перезапускаю только $SERVICE, чтобы Python загрузил новый код."
systemctl restart "$SERVICE"
systemctl is-active --quiet "$SERVICE" || { echo "$SERVICE не поднялся после рестарта." >&2; exit 1; }

PATCHED=0
trap - EXIT INT TERM
rm -rf -- "$TMP_DIR"

echo "Установлен $VERSION"
echo "Payload: $PAYLOAD_REF ($PAYLOAD_BLOB)"
echo "Service: $SERVICE active"
echo "Backup: $BACKUP_DIR"
echo "Изменён только jump_web_bridge.py; state, БД, AI Home и manual frontend не изменялись."
