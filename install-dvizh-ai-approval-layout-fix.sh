#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-approval-layout-fix.1"
MARKER='DVIZH_AI_APPROVAL_HIDDEN_FIX_V1'

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 2
fi

APP_ROOT=""
if [[ -f /opt/dvizh/static/styles.css ]]; then APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/styles.css ]]; then APP_ROOT="/opt/dvizh"
else echo "Не найден веб-интерфейс ДВИЖа." >&2; exit 1
fi

for name in styles.css sw.js; do
  [[ -f "$APP_ROOT/$name" ]] || { echo "Не найден $APP_ROOT/$name" >&2; exit 1; }
done

grep -q 'DVIZH_AI_APPROVAL_UI_V1' "$APP_ROOT/styles.css" || {
  echo "Сначала должен быть установлен DVIZH AI approval." >&2
  exit 1
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/lib/dvizh/backups/ai-approval-layout-fix-$STAMP"
install -d -m 0700 -o root -g root "$BACKUP_DIR"
cp -a "$APP_ROOT/styles.css" "$BACKUP_DIR/styles.css"
cp -a "$APP_ROOT/sw.js" "$BACKUP_DIR/sw.js"

rollback() {
  local rc=$?
  echo "Ошибка. Возвращаю прежние файлы интерфейса..." >&2
  cp -a "$BACKUP_DIR/styles.css" "$APP_ROOT/styles.css" || true
  cp -a "$BACKUP_DIR/sw.js" "$APP_ROOT/sw.js" || true
  exit "$rc"
}
trap rollback ERR INT TERM

if ! grep -q "$MARKER" "$APP_ROOT/styles.css"; then
  cat >> "$APP_ROOT/styles.css" <<'CSS'

/* DVIZH_AI_APPROVAL_HIDDEN_FIX_V1
   The proposal panel is dynamically recreated by the app. Author CSS with
   display:grid overrides the browser's [hidden] rule, so an empty grey panel
   could briefly take up space and make the page jump. */
.ai-proposal-panel[hidden] { display: none !important; }
CSS
fi

python3 - "$APP_ROOT/sw.js" <<'PY'
from pathlib import Path
import re, sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
new='dvizh-ai-approval-v1-layoutfix-20260905'
if new not in s:
    s2,n=re.subn(r"(const\s+CACHE\s*=\s*['\"])([^'\"]+)(['\"])", rf"\1{new}\3", s, count=1)
    if n != 1:
        raise SystemExit('service worker cache anchor not found')
    p.write_text(s2, encoding='utf-8')
PY

grep -q "$MARKER" "$APP_ROOT/styles.css"
grep -q 'dvizh-ai-approval-v1-layoutfix-20260905' "$APP_ROOT/sw.js"

for unit in dvizh.service dvizh-auth.service dvizh-telegram.service dvizh-bridge.service dvizh-web-week.service dvizh-web-editor.service dvizh-training.service dvizh-jump.service dvizh-social.service dvizh-ai-approval.service; do
  systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
done
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null

trap - ERR INT TERM
printf '%s\n' "DVIZH AI approval layout fix $VERSION installed."
printf '%s\n' "Backup: $BACKUP_DIR"
printf '%s\n' "Полностью закрой ДВИЖ и открой снова, чтобы обновился service worker."
