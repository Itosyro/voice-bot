#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home.1"
PAYLOAD_REF="5409dab2316d15007f686cbef69f47d964b7ce50"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-control-v1"
TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/dvizh_ai_home_bridge.py" -o "$TMP_DIR/ai_home_bridge.py"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/patch_ai_home_ui.py" -o "$TMP_DIR/patch_ai_home_ui.py"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/systemd/dvizh-ai-home.service" -o "$TMP_DIR/dvizh-ai-home.service"
python3 -m py_compile "$TMP_DIR/ai_home_bridge.py" "$TMP_DIR/patch_ai_home_ui.py"
grep -q 'VERSION = "2026.09.05-ai-home.1"' "$TMP_DIR/ai_home_bridge.py"
grep -q 'DVIZH_AI_HOME_V1' "$TMP_DIR/patch_ai_home_ui.py"
grep -q '^User=dvizh$' "$TMP_DIR/dvizh-ai-home.service"
grep -q 'NoNewPrivileges=true' "$TMP_DIR/dvizh-ai-home.service"

if [[ "${DVIZH_AI_HOME_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "DVIZH AI Home payload verified from $PAYLOAD_REF."
  exit 0
fi

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти установщик через: curl ... | sudo bash" >&2
  exit 1
fi

HERMES_USER="${DVIZH_HERMES_USER:-exedev}"
id "$HERMES_USER" >/dev/null 2>&1 || { echo "Не найден пользователь Hermes: $HERMES_USER" >&2; exit 1; }
id dvizh >/dev/null 2>&1 || { echo "Не найден системный пользователь dvizh" >&2; exit 1; }
HERMES_HOME="$(getent passwd "$HERMES_USER" | cut -d: -f6)"
HERMES_UID="$(id -u "$HERMES_USER")"
HERMES_ENV="$HERMES_HOME/.hermes/.env"
[[ -d "$HERMES_HOME/.hermes" ]] || { echo "Hermes не установлен для $HERMES_USER" >&2; exit 1; }
install -o "$HERMES_USER" -g "$(id -gn "$HERMES_USER")" -m 0600 /dev/null "$HERMES_ENV" 2>/dev/null || true

LOCK_FILE="/run/lock/dvizh-ai-home-install.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "Другая установка AI Home уже выполняется." >&2; exit 1; }

APP_ROOT=""
if [[ -f /opt/dvizh/static/index.html ]]; then APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then APP_ROOT="/opt/dvizh"
else echo "Не найден веб-интерфейс ДВИЖа." >&2; exit 1
fi
for name in app.js styles.css sw.js; do [[ -f "$APP_ROOT/$name" ]] || { echo "Не найден $APP_ROOT/$name" >&2; exit 1; }; done

required_units=(dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service dvizh-web-editor.service dvizh-training.service dvizh-jump.service dvizh-social.service dvizh-ai-approval.service)
for unit in "${required_units[@]}"; do systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }; done
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
python3 "$TMP_DIR/patch_ai_home_ui.py" --root "$APP_ROOT" --check

DATA_DIR="/var/lib/dvizh"
MODULE_ROOT="/opt/dvizh-ai-home"
ENV_DIR="/etc/dvizh"
AI_ENV="$ENV_DIR/ai-home.env"
SERVICE_PATH="/etc/systemd/system/dvizh-ai-home.service"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$DATA_DIR/backups/ai-home-$STAMP"
SUCCESS=0
HAD_MODULE=0; HAD_SERVICE=0; HAD_AI_ENV=0; HAD_HERMES_ENV=0

restart_hermes() {
  sudo -n -u "$HERMES_USER" env XDG_RUNTIME_DIR="/run/user/$HERMES_UID" systemctl --user restart hermes-gateway.service
}

rollback() {
  local code=$?
  [[ "$SUCCESS" -eq 1 ]] && return 0
  echo "Ошибка. Возвращаю предыдущую конфигурацию AI Home..." >&2
  if [[ -d "$BACKUP_DIR/static" ]]; then
    for name in app.js styles.css sw.js; do [[ -f "$BACKUP_DIR/static/$name" ]] && cp -a "$BACKUP_DIR/static/$name" "$APP_ROOT/$name" || true; done
  fi
  if [[ "$HAD_MODULE" -eq 1 && -d "$BACKUP_DIR/module" ]]; then rm -rf "$MODULE_ROOT"; cp -a "$BACKUP_DIR/module" "$MODULE_ROOT"; else rm -rf "$MODULE_ROOT"; fi
  if [[ "$HAD_SERVICE" -eq 1 && -f "$BACKUP_DIR/dvizh-ai-home.service" ]]; then cp -a "$BACKUP_DIR/dvizh-ai-home.service" "$SERVICE_PATH"; else rm -f "$SERVICE_PATH"; fi
  if [[ "$HAD_AI_ENV" -eq 1 && -f "$BACKUP_DIR/ai-home.env" ]]; then cp -a "$BACKUP_DIR/ai-home.env" "$AI_ENV"; else rm -f "$AI_ENV"; fi
  if [[ "$HAD_HERMES_ENV" -eq 1 && -f "$BACKUP_DIR/hermes.env" ]]; then cp -a "$BACKUP_DIR/hermes.env" "$HERMES_ENV"; chown "$HERMES_USER:$(id -gn "$HERMES_USER")" "$HERMES_ENV"; chmod 0600 "$HERMES_ENV"; fi
  systemctl daemon-reload || true
  if [[ "$HAD_SERVICE" -eq 1 ]]; then systemctl restart dvizh-ai-home.service || true; else systemctl disable --now dvizh-ai-home.service >/dev/null 2>&1 || true; fi
  restart_hermes || true
  exit "$code"
}
trap rollback ERR INT TERM

install -d -o root -g root -m 0700 "$BACKUP_DIR" "$BACKUP_DIR/static"
for name in app.js styles.css sw.js; do cp -a "$APP_ROOT/$name" "$BACKUP_DIR/static/$name"; done
if [[ -d "$MODULE_ROOT" ]]; then HAD_MODULE=1; cp -a "$MODULE_ROOT" "$BACKUP_DIR/module"; fi
if [[ -f "$SERVICE_PATH" ]]; then HAD_SERVICE=1; cp -a "$SERVICE_PATH" "$BACKUP_DIR/dvizh-ai-home.service"; fi
if [[ -f "$AI_ENV" ]]; then HAD_AI_ENV=1; cp -a "$AI_ENV" "$BACKUP_DIR/ai-home.env"; fi
if [[ -f "$HERMES_ENV" ]]; then HAD_HERMES_ENV=1; cp -a "$HERMES_ENV" "$BACKUP_DIR/hermes.env"; chmod 0600 "$BACKUP_DIR/hermes.env"; fi

printf '[1/6] Включаю локальный Hermes API без публикации наружу...\n'
python3 - "$HERMES_ENV" "$TMP_DIR/hermes-key" <<'PY'
import os,secrets,sys
from pathlib import Path
path=Path(sys.argv[1]); keyfile=Path(sys.argv[2])
lines=path.read_text(encoding='utf-8').splitlines() if path.exists() else []
values={}
for raw in lines:
    line=raw.strip()
    if line and not line.startswith('#') and '=' in line:
        k,v=line.split('=',1); values[k.strip()]=v.strip().strip('"\'')
key=values.get('API_SERVER_KEY') or secrets.token_urlsafe(48)
updates={'API_SERVER_ENABLED':'true','API_SERVER_HOST':'127.0.0.1','API_SERVER_PORT':'8642','API_SERVER_KEY':key}
out=[]; seen=set()
for raw in lines:
    if '=' in raw and not raw.lstrip().startswith('#'):
        k=raw.split('=',1)[0].strip()
        if k in updates:
            if k not in seen: out.append(f'{k}={updates[k]}'); seen.add(k)
            continue
    out.append(raw)
for k,v in updates.items():
    if k not in seen: out.append(f'{k}={v}')
path.write_text('\n'.join(out).rstrip()+'\n',encoding='utf-8')
os.chmod(path,0o600)
keyfile.write_text(key,encoding='utf-8'); os.chmod(keyfile,0o600)
PY
chown "$HERMES_USER:$(id -gn "$HERMES_USER")" "$HERMES_ENV"
restart_hermes

HERMES_KEY="$(cat "$TMP_DIR/hermes-key")"
for _ in $(seq 1 40); do
  code="$(curl -sS -o /dev/null --max-time 3 -w '%{http_code}' -H "Authorization: Bearer $HERMES_KEY" http://127.0.0.1:8642/v1/models 2>/dev/null || true)"
  [[ "$code" == "200" ]] && break
  sleep 1
done
[[ "${code:-000}" == "200" ]] || { echo "Hermes API не поднялся на 127.0.0.1:8642" >&2; exit 1; }

printf '[2/6] Устанавливаю защищённый серверный мост AI Home...\n'
install -d -o root -g root -m 0755 "$MODULE_ROOT" "$ENV_DIR"
install -m 0755 -o root -g root "$TMP_DIR/ai_home_bridge.py" "$MODULE_ROOT/ai_home_bridge.py"
install -m 0644 -o root -g root "$TMP_DIR/patch_ai_home_ui.py" "$MODULE_ROOT/patch_ai_home_ui.py"
printf '%s\n' "$VERSION" > "$MODULE_ROOT/VERSION"
cat > "$TMP_DIR/ai-home.env" <<EOF
HERMES_API_URL=http://127.0.0.1:8642/v1
HERMES_API_KEY=$HERMES_KEY
HERMES_API_MODEL=hermes-agent
DVIZH_WEB_API=http://127.0.0.1:8000
DVIZH_AI_HOME_INTERVAL=2
DVIZH_AI_HOME_HERMES_TIMEOUT=180
EOF
install -m 0640 -o root -g dvizh "$TMP_DIR/ai-home.env" "$AI_ENV"
install -m 0644 -o root -g root "$TMP_DIR/dvizh-ai-home.service" "$SERVICE_PATH"
unset HERMES_KEY

printf '[3/6] Ставлю минималистичную AI Home...\n'
python3 "$TMP_DIR/patch_ai_home_ui.py" --root "$APP_ROOT"
python3 "$TMP_DIR/patch_ai_home_ui.py" --root "$APP_ROOT" --check
grep -q 'DVIZH_AI_HOME_V1' "$APP_ROOT/app.js"
grep -q 'DVIZH_AI_HOME_V1' "$APP_ROOT/styles.css"
grep -q 'dvizh-ai-home-v1' "$APP_ROOT/sw.js"
if command -v node >/dev/null 2>&1; then node --check "$APP_ROOT/app.js" >/dev/null; fi

printf '[4/6] Запускаю AI Home bridge...\n'
systemctl daemon-reload
systemctl enable dvizh-ai-home.service >/dev/null
systemctl restart dvizh-ai-home.service
for _ in $(seq 1 30); do
  if systemctl is-active --quiet dvizh-ai-home.service && [[ -f "$DATA_DIR/ai-home-status.json" ]]; then
    break
  fi
  sleep 1
done
systemctl is-active --quiet dvizh-ai-home.service

printf '[5/6] Проверяю Hermes и ДВИЖ...\n'
python3 - "$DATA_DIR/ai-home-status.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1],encoding='utf-8'))
print('AI Home bridge:', 'ok' if p.get('ok') else 'waiting')
print('model:', p.get('model','—'))
if not p.get('ok') and 'identity' not in str(p.get('error','')).lower():
    raise SystemExit(p.get('error') or 'AI Home not ready')
PY
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null

printf '[6/6] Проверяю службы...\n'
for unit in "${required_units[@]}"; do printf '%s: ' "$unit"; systemctl is-active "$unit"; done
printf 'dvizh-ai-home.service: '; systemctl is-active dvizh-ai-home.service

SUCCESS=1
trap - ERR INT TERM

echo
echo "DVIZH AI Home $VERSION installed."
echo "Backup: $BACKUP_DIR"
echo "Hermes API слушает только 127.0.0.1:8642; ключ не передаётся в браузер."
echo "Полностью закрой ДВИЖ и открой снова. Главная станет AI Home."
echo "Старую главную можно открыть кнопкой «Ручной режим»."
