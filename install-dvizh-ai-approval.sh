#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-approval.1"
PAYLOAD_REF="79c5c40ad1a83fe372459f18389ee2e29ba554f7"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-control-v1"
TMP_DIR="$(mktemp -d /tmp/dvizh-ai-approval.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n bash "$0" "$@"
fi

LOCK_FILE="/run/lock/dvizh-ai-approval-install.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Другая установка AI approval уже выполняется." >&2
  exit 1
fi

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizh_proposal_bridge.py" -o "$TMP_DIR/proposal_bridge.py"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/patch_ai_approval_ui.py" -o "$TMP_DIR/patch_ai_approval_ui.py"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/systemd/dvizh-ai-approval.service" -o "$TMP_DIR/dvizh-ai-approval.service"

python3 -m py_compile "$TMP_DIR/proposal_bridge.py" "$TMP_DIR/patch_ai_approval_ui.py"
grep -q 'VERSION = "2026.09.05-ai-approval.1"' "$TMP_DIR/proposal_bridge.py"
grep -q 'DVIZH_AI_APPROVAL_UI_V1' "$TMP_DIR/patch_ai_approval_ui.py"
grep -q '^User=dvizh$' "$TMP_DIR/dvizh-ai-approval.service"

if [[ "${DVIZH_AI_APPROVAL_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "DVIZH AI approval payload verified from $PAYLOAD_REF."
  exit 0
fi

id dvizh >/dev/null 2>&1 || { echo "Не найден системный пользователь dvizh." >&2; exit 1; }
[[ -x /usr/local/bin/dvizhctl ]] || { echo "Сначала установи Hermes control layer." >&2; exit 1; }
[[ "$(/usr/local/bin/dvizhctl version)" == "2026.09.05-hermes-control.5" ]] || {
  echo "Нужен Hermes control 2026.09.05-hermes-control.5." >&2
  exit 1
}
[[ -x /usr/local/libexec/dvizh-proposals ]] || { echo "Не найден proposal helper." >&2; exit 1; }
[[ -d /var/lib/dvizh/hermes-proposals ]] || { echo "Не найдена proposal queue." >&2; exit 1; }

APP_ROOT=""
if [[ -f /opt/dvizh/static/index.html ]]; then APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then APP_ROOT="/opt/dvizh"
else echo "Не найден веб-интерфейс ДВИЖа." >&2; exit 1
fi
for name in app.js styles.css sw.js; do
  [[ -f "$APP_ROOT/$name" ]] || { echo "Не найден $APP_ROOT/$name" >&2; exit 1; }
done

required_units=(
  dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service
  dvizh-web-week.service dvizh-web-editor.service dvizh-training.service
  dvizh-jump.service dvizh-social.service
)
for unit in "${required_units[@]}"; do
  systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
done
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null

python3 "$TMP_DIR/patch_ai_approval_ui.py" --root "$APP_ROOT" --check

DATA_DIR="/var/lib/dvizh"
MODULE_ROOT="/opt/dvizh-ai-approval"
SERVICE_PATH="/etc/systemd/system/dvizh-ai-approval.service"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$DATA_DIR/backups/ai-approval-$STAMP"
SUCCESS=0
HAD_MODULE=0
HAD_SERVICE=0

rollback() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then return 0; fi
  echo "Ошибка. Возвращаю предыдущий AI approval слой..." >&2
  if [[ -d "$BACKUP_DIR/static" ]]; then
    for name in app.js styles.css sw.js; do
      [[ -f "$BACKUP_DIR/static/$name" ]] && cp -a "$BACKUP_DIR/static/$name" "$APP_ROOT/$name" || true
    done
  fi
  if [[ "$HAD_MODULE" -eq 1 && -d "$BACKUP_DIR/module" ]]; then
    rm -rf "$MODULE_ROOT" || true
    cp -a "$BACKUP_DIR/module" "$MODULE_ROOT" || true
  elif [[ "$HAD_MODULE" -eq 0 ]]; then
    rm -rf "$MODULE_ROOT" || true
  fi
  if [[ "$HAD_SERVICE" -eq 1 && -f "$BACKUP_DIR/dvizh-ai-approval.service" ]]; then
    cp -a "$BACKUP_DIR/dvizh-ai-approval.service" "$SERVICE_PATH" || true
    systemctl daemon-reload || true
    systemctl restart dvizh-ai-approval.service || true
  else
    systemctl disable --now dvizh-ai-approval.service >/dev/null 2>&1 || true
    rm -f "$SERVICE_PATH" || true
    systemctl daemon-reload || true
  fi
  exit "$code"
}
trap rollback ERR INT TERM

install -d -m 0700 -o root -g root "$BACKUP_DIR" "$BACKUP_DIR/static"
for name in app.js styles.css sw.js; do cp -a "$APP_ROOT/$name" "$BACKUP_DIR/static/$name"; done
if [[ -d "$MODULE_ROOT" ]]; then
  HAD_MODULE=1
  cp -a "$MODULE_ROOT" "$BACKUP_DIR/module"
fi
if [[ -f "$SERVICE_PATH" ]]; then
  HAD_SERVICE=1
  cp -a "$SERVICE_PATH" "$BACKUP_DIR/dvizh-ai-approval.service"
fi

printf '[1/5] Добавляю минимальные карточки подтверждения...\n'
python3 "$TMP_DIR/patch_ai_approval_ui.py" --root "$APP_ROOT"
python3 "$TMP_DIR/patch_ai_approval_ui.py" --root "$APP_ROOT" --check
grep -q 'DVIZH_AI_APPROVAL_UI_V1' "$APP_ROOT/app.js"
grep -q 'DVIZH_AI_APPROVAL_UI_V1' "$APP_ROOT/styles.css"
grep -q 'dvizh-ai-approval-v1' "$APP_ROOT/sw.js"
if command -v node >/dev/null 2>&1; then node --check "$APP_ROOT/app.js" >/dev/null; fi

printf '[2/5] Устанавливаю серверный approval bridge...\n'
install -d -m 0755 -o root -g root "$MODULE_ROOT"
install -m 0755 -o root -g root "$TMP_DIR/proposal_bridge.py" "$MODULE_ROOT/proposal_bridge.py"
install -m 0644 -o root -g root "$TMP_DIR/patch_ai_approval_ui.py" "$MODULE_ROOT/patch_ai_approval_ui.py"
printf '%s\n' "$VERSION" > "$MODULE_ROOT/VERSION"
chmod 0644 "$MODULE_ROOT/VERSION"
install -m 0644 -o root -g root "$TMP_DIR/dvizh-ai-approval.service" "$SERVICE_PATH"

printf '[3/5] Запускаю отдельную службу подтверждений...\n'
systemctl daemon-reload
systemctl enable dvizh-ai-approval.service >/dev/null
systemctl restart dvizh-ai-approval.service

for _ in $(seq 1 30); do
  if systemctl is-active --quiet dvizh-ai-approval.service && [[ -f "$DATA_DIR/ai-approval-status.json" ]]; then
    if python3 - "$DATA_DIR/ai-approval-status.json" <<'PY' >/dev/null 2>&1
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
raise SystemExit(0 if p.get('ok') else 1)
PY
    then break; fi
  fi
  sleep 1
done
systemctl is-active --quiet dvizh-ai-approval.service
python3 - "$DATA_DIR/ai-approval-status.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print('approval bridge:', 'ok' if p.get('ok') else 'error')
print('pending proposals:', p.get('pending', 0))
if not p.get('ok'):
    raise SystemExit(p.get('error') or 'approval bridge not ready')
PY

printf '[4/5] Проверяю, что proposal всё ещё требует подтверждения...\n'
/usr/local/bin/dvizhctl proposals pending >/dev/null
if /usr/local/bin/dvizhctl approve test >/tmp/dvizh-ai-approve.out 2>/tmp/dvizh-ai-approve.err; then
  echo "Опасная команда approve неожиданно доступна через Hermes." >&2
  exit 1
fi
grep -q 'not available' /tmp/dvizh-ai-approve.err

printf '[5/5] Проверяю ДВИЖ целиком...\n'
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
for unit in "${required_units[@]}"; do
  printf '%s: ' "$unit"; systemctl is-active "$unit"
done
printf 'dvizh-ai-approval.service: '; systemctl is-active dvizh-ai-approval.service

SUCCESS=1
trap - ERR INT TERM

echo
echo "DVIZH AI approval $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Hermes по-прежнему только создаёт proposal."
echo "Применить или отклонить его теперь можно только кнопкой в авторизованном веб-ДВИЖе."
echo "Полностью закрой ДВИЖ и открой снова, чтобы обновился service worker."
