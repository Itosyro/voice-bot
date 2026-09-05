#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home.1-stable"
BASE_INSTALL_REF="75eed71ddebab416ce3ba52440b4d476fcbb73a1"
BASE_INSTALL_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BASE_INSTALL_REF}/install-dvizh-ai-home.sh"
TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-release.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 1
fi

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_INSTALL_URL" -o "$TMP_DIR/install.sh"
bash -n "$TMP_DIR/install.sh"
bash "$TMP_DIR/install.sh"

APP_ROOT=""
if [[ -f /opt/dvizh/static/styles.css ]]; then APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/styles.css ]]; then APP_ROOT="/opt/dvizh"
else echo "Не найден веб-интерфейс ДВИЖа после установки." >&2; exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/lib/dvizh/backups/ai-home-stability-$STAMP"
install -d -o root -g root -m 0700 "$BACKUP_DIR"
cp -a "$APP_ROOT/styles.css" "$BACKUP_DIR/styles.css"
cp -a "$APP_ROOT/sw.js" "$BACKUP_DIR/sw.js"
SUCCESS=0
rollback() {
  local rc=$?
  if [[ "$SUCCESS" -eq 0 ]]; then
    cp -a "$BACKUP_DIR/styles.css" "$APP_ROOT/styles.css" || true
    cp -a "$BACKUP_DIR/sw.js" "$APP_ROOT/sw.js" || true
  fi
  exit "$rc"
}
trap rollback ERR INT TERM

if ! grep -q 'DVIZH_AI_HOME_HIDDEN_PROPOSAL_FIX' "$APP_ROOT/styles.css"; then
  cat >> "$APP_ROOT/styles.css" <<'CSS'

/* DVIZH_AI_HOME_HIDDEN_PROPOSAL_FIX */
#aiProposalPanel[hidden],
.ai-proposal-panel[hidden] {
  display: none !important;
}
CSS
fi

python3 - "$APP_ROOT/sw.js" <<'PY'
import re,sys
from pathlib import Path
p=Path(sys.argv[1]); text=p.read_text(encoding='utf-8')
text,n=re.subn(r"(const\s+CACHE\s*=\s*['\"])([^'\"]+)(['\"])",r"\1dvizh-ai-home-v1-stable\3",text,count=1)
if n != 1: raise SystemExit('service worker cache anchor not found')
p.write_text(text,encoding='utf-8')
PY

grep -q 'DVIZH_AI_HOME_V1' "$APP_ROOT/styles.css"
grep -q 'DVIZH_AI_HOME_HIDDEN_PROPOSAL_FIX' "$APP_ROOT/styles.css"
grep -q 'dvizh-ai-home-v1-stable' "$APP_ROOT/sw.js"
if command -v node >/dev/null 2>&1; then node --check "$APP_ROOT/app.js" >/dev/null; fi
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
systemctl is-active --quiet dvizh-ai-home.service
systemctl is-active --quiet dvizh-ai-approval.service

SUCCESS=1
trap - ERR INT TERM

echo
echo "DVIZH AI Home stable release installed: $VERSION"
echo "Stability backup: $BACKUP_DIR"
echo "Полностью закрой ДВИЖ и открой заново."
