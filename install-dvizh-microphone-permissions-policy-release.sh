#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-microphone-permissions-policy-release.2"
PAYLOAD_REF="8ab401631a8217efc5df5375c7266b8d2a300adf"
PAYLOAD_BLOB="cbc2dcfee9f24b2635ce10808250292b22a23db7"
PAYLOAD_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/install-dvizh-microphone-permissions-policy-fix.sh"
TARGET="/opt/dvizh/server.py"
SERVICE="dvizh.service"
BACKUP_ROOT="/var/lib/dvizh/backups"
PROBE_URL="http://127.0.0.1:8000/ai-home-v2-voice-preview.html"
EXPECTED_POLICY="Permissions-Policy: camera=(), microphone=(self), geolocation=(), payment=()"
READY_ATTEMPTS=30

[[ $# -eq 0 ]] || { echo "Этот установщик не принимает аргументы." >&2; exit 1; }
[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Для установки нужен root." >&2; exit 1; }
for tool in curl python3 systemctl mktemp cp install grep chmod chown tr sleep; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done
[[ -f "$TARGET" && ! -L "$TARGET" ]] || { echo "Небезопасный или отсутствующий $TARGET" >&2; exit 1; }
systemctl is-active --quiet "$SERVICE" || { echo "$SERVICE не active; ничего не изменено." >&2; exit 1; }
systemctl cat "$SERVICE" 2>/dev/null | grep -Fq "$TARGET" || {
  echo "$SERVICE не ссылается на $TARGET; ничего не изменено." >&2
  exit 1
}

wait_for_http() {
  local attempt
  for ((attempt=1; attempt<=READY_ATTEMPTS; attempt++)); do
    if curl --fail --silent --output /dev/null --max-time 2 "$PROBE_URL" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_policy() {
  local attempt headers
  for ((attempt=1; attempt<=READY_ATTEMPTS; attempt++)); do
    if headers="$(curl --fail --silent --dump-header - --output /dev/null --max-time 2 "$PROBE_URL" 2>/dev/null | tr -d '\r')"; then
      if grep -Fqi "$EXPECTED_POLICY" <<<"$headers" && ! grep -Eqi '^Permissions-Policy:.*microphone=\(\)' <<<"$headers"; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

TMP_DIR="$(mktemp -d /tmp/dvizh-microphone-policy-release.XXXXXX)"
BACKUP_DIR=""
PATCHED=0
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ $rc -ne 0 && "$PATCHED" == 1 && -n "$BACKUP_DIR" && -f "$BACKUP_DIR/server.py" ]]; then
    echo "Ошибка после изменения: возвращаю backup server.py." >&2
    cp -a -- "$BACKUP_DIR/server.py" "$TARGET" || true
    if systemctl restart "$SERVICE"; then
      wait_for_http || echo "Предупреждение: после rollback $SERVICE не ответил на $PROBE_URL за ${READY_ATTEMPTS}с." >&2
    fi
  fi
  rm -rf -- "$TMP_DIR"
  exit "$rc"
}
trap cleanup EXIT INT TERM

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$PAYLOAD_URL" -o "$TMP_DIR/payload.sh"
ACTUAL_BLOB="$(python3 - "$TMP_DIR/payload.sh" <<'PY'
from pathlib import Path
import hashlib, sys
p = Path(sys.argv[1]); data = p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)"
[[ "$ACTUAL_BLOB" == "$PAYLOAD_BLOB" ]] || { echo "Immutable payload mismatch: $ACTUAL_BLOB" >&2; exit 1; }
bash -n "$TMP_DIR/payload.sh"

install -d -m 0700 "$BACKUP_ROOT"
BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/microphone-policy.XXXXXX")"
chmod 0700 "$BACKUP_DIR"
cp -a -- "$TARGET" "$BACKUP_DIR/server.py"

bash "$TMP_DIR/payload.sh"
PATCHED=1
chown --reference="$BACKUP_DIR/server.py" "$TARGET"
chmod --reference="$BACKUP_DIR/server.py" "$TARGET"
python3 -m py_compile "$TARGET"

echo "Перезапускаю только $SERVICE, чтобы новый security header вступил в силу."
systemctl restart "$SERVICE"
systemctl is-active --quiet "$SERVICE" || { echo "$SERVICE не поднялся после рестарта." >&2; exit 1; }
echo "Жду готовности DVIZH на 127.0.0.1:8000 (до ${READY_ATTEMPTS}с)."
wait_for_policy || {
  echo "За ${READY_ATTEMPTS}с не получен ожидаемый microphone=(self) header; выполняется rollback." >&2
  exit 1
}

PATCHED=0
trap - EXIT INT TERM
rm -rf -- "$TMP_DIR"

echo "Установлен $VERSION"
echo "Payload: $PAYLOAD_REF ($PAYLOAD_BLOB)"
echo "Service: $SERVICE active"
echo "Verified: $EXPECTED_POLICY"
echo "Backup: $BACKUP_DIR"
echo "Изменён только $TARGET; app.js, manual.html, sync.js, sw.js, БД и state не изменялись."
