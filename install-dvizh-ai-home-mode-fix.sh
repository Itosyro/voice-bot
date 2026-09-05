#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-mode-fix.1"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 1
fi

APP_ROOT=""
if [[ -f /opt/dvizh/static/index.html ]]; then APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then APP_ROOT="/opt/dvizh"
else echo "Не найден веб-интерфейс ДВИЖа." >&2; exit 1
fi

APP="$APP_ROOT/app.js"
SW="$APP_ROOT/sw.js"
[[ -f "$APP" && -f "$SW" ]] || { echo "Не найдены app.js/sw.js" >&2; exit 1; }
grep -q 'const DVIZH_AI_HOME_V1 = true;' "$APP" || { echo "AI Home v1 не найден." >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="/var/lib/dvizh/backups/ai-home-mode-fix-$STAMP"
install -d -o root -g root -m 0700 "$BACKUP_DIR"
cp -a "$APP" "$BACKUP_DIR/app.js"
cp -a "$SW" "$BACKUP_DIR/sw.js"

python3 - "$APP" "$SW" <<'PY'
from pathlib import Path
import re,sys
app=Path(sys.argv[1]); sw=Path(sys.argv[2])
text=app.read_text(encoding='utf-8')
old="""  function aiHomeEnsureRoot() {\n    const home = document.getElementById('view-home');\n    if (!home) return null;\n    home.classList.add('ai-home-mode');\n    let root = document.getElementById('aiHomeShell');\n"""
new="""  function aiHomeEnsureRoot() {\n    const home = document.getElementById('view-home');\n    if (!home) return null;\n    let root = document.getElementById('aiHomeShell');\n"""
if old in text:
    text=text.replace(old,new,1)
elif "home.classList.add('ai-home-mode');\n    let root = document.getElementById('aiHomeShell');" in text:
    text=text.replace("home.classList.add('ai-home-mode');\n    let root = document.getElementById('aiHomeShell');","let root = document.getElementById('aiHomeShell');",1)
elif 'DVIZH_AI_HOME_MODE_STABLE_V1' not in text:
    raise SystemExit('Не найден ожидаемый aiHomeEnsureRoot anchor')

boot_old="""  function aiHomeBoot() {\n    aiHomeEnsureRoot();\n    aiHomeEnsureManualBack();\n"""
boot_new="""  function aiHomeBoot() {\n    const home = document.getElementById('view-home');\n    if (home) home.classList.add('ai-home-mode');\n    aiHomeEnsureRoot();\n    aiHomeEnsureManualBack();\n"""
if boot_old in text:
    text=text.replace(boot_old,boot_new,1)
elif 'DVIZH_AI_HOME_MODE_STABLE_V1' not in text:
    raise SystemExit('Не найден ожидаемый aiHomeBoot anchor')

if 'DVIZH_AI_HOME_MODE_STABLE_V1' not in text:
    text=text.replace('  const DVIZH_AI_HOME_V1 = true;','  const DVIZH_AI_HOME_V1 = true;\n  const DVIZH_AI_HOME_MODE_STABLE_V1 = true;',1)
app.write_text(text,encoding='utf-8')

s=sw.read_text(encoding='utf-8')
s2,n=re.subn(r"(const\\s+CACHE\\s*=\\s*['\"])([^'\"]+)(['\"])",r"\\1dvizh-ai-home-mode-stable-v1\\3",s,count=1)
if n != 1:
    raise SystemExit('service worker cache anchor not found')
sw.write_text(s2,encoding='utf-8')
PY

if command -v node >/dev/null 2>&1; then node --check "$APP" >/dev/null; fi
grep -q 'DVIZH_AI_HOME_MODE_STABLE_V1' "$APP"
grep -q 'dvizh-ai-home-mode-stable-v1' "$SW"

# Backend services are intentionally untouched; verify only that they remain healthy.
systemctl is-active --quiet dvizh.service
systemctl is-active --quiet dvizh-ai-home.service
systemctl is-active --quiet dvizh-ai-approval.service

echo "DVIZH AI Home mode stability fix installed: $VERSION"
echo "Backup: $BACKUP_DIR"
echo "Полностью закрой ДВИЖ и открой снова, чтобы браузер взял новый service worker."
