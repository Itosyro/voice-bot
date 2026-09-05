#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-mode-fix.2"
TEST_ROOT="${DVIZH_AI_HOME_MODE_FIX_ROOT:-}"

if [[ -z "$TEST_ROOT" && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через: curl ... | sudo bash" >&2
  exit 1
fi

if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT="/opt/dvizh/static"
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT="/opt/dvizh"
else
  echo "Не найден веб-интерфейс ДВИЖа." >&2
  exit 1
fi

APP="$APP_ROOT/app.js"
SW="$APP_ROOT/sw.js"
INDEX="$APP_ROOT/index.html"
[[ -f "$APP" && -f "$SW" ]] || { echo "Не найдены app.js/sw.js" >&2; exit 1; }
grep -q 'const DVIZH_AI_HOME_V1 = true;' "$APP" || { echo "AI Home v1 не найден." >&2; exit 1; }

if [[ -z "$TEST_ROOT" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_DIR="/var/lib/dvizh/backups/ai-home-mode-fix-$STAMP"
  install -d -o root -g root -m 0700 "$BACKUP_DIR"
  cp -a "$APP" "$BACKUP_DIR/app.js"
  cp -a "$SW" "$BACKUP_DIR/sw.js"
  [[ -f "$INDEX" ]] && cp -a "$INDEX" "$BACKUP_DIR/index.html"
else
  BACKUP_DIR="$APP_ROOT/.mode-fix-backup"
  mkdir -p "$BACKUP_DIR"
  cp -a "$APP" "$BACKUP_DIR/app.js"
  cp -a "$SW" "$BACKUP_DIR/sw.js"
  [[ -f "$INDEX" ]] && cp -a "$INDEX" "$BACKUP_DIR/index.html"
fi

python3 - "$APP" "$SW" "$INDEX" <<'PY'
from pathlib import Path
import re,sys

app=Path(sys.argv[1]); sw=Path(sys.argv[2]); index=Path(sys.argv[3])
text=app.read_text(encoding='utf-8')

# The bug: aiHomeRender() calls aiHomeEnsureRoot() on a timer, and
# aiHomeEnsureRoot() used to force ai-home-mode every time. Remove that side
# effect. Mode changes must happen only on boot or explicit user actions.
old="""  function aiHomeEnsureRoot() {\n    const home = document.getElementById('view-home');\n    if (!home) return null;\n    home.classList.add('ai-home-mode');\n    let root = document.getElementById('aiHomeShell');\n"""
new="""  function aiHomeEnsureRoot() {\n    const home = document.getElementById('view-home');\n    if (!home) return null;\n    let root = document.getElementById('aiHomeShell');\n"""
if old in text:
    text=text.replace(old,new,1)
else:
    loose="home.classList.add('ai-home-mode');\n    let root = document.getElementById('aiHomeShell');"
    if loose in text:
        text=text.replace(loose,"let root = document.getElementById('aiHomeShell');",1)
    elif 'DVIZH_AI_HOME_MODE_STABLE_V1' not in text:
        raise SystemExit('Не найден ожидаемый aiHomeEnsureRoot anchor')

boot_old="""  function aiHomeBoot() {\n    aiHomeEnsureRoot();\n    aiHomeEnsureManualBack();\n"""
boot_new="""  function aiHomeBoot() {\n    const home = document.getElementById('view-home');\n    if (home) home.classList.add('ai-home-mode');\n    aiHomeEnsureRoot();\n    aiHomeEnsureManualBack();\n"""
if boot_old in text:
    text=text.replace(boot_old,boot_new,1)
elif "function aiHomeBoot()" in text and "DVIZH_AI_HOME_MODE_STABLE_V1" not in text:
    raise SystemExit('Не найден ожидаемый aiHomeBoot anchor')

if 'DVIZH_AI_HOME_MODE_STABLE_V1' not in text:
    text=text.replace(
        '  const DVIZH_AI_HOME_V1 = true;',
        '  const DVIZH_AI_HOME_V1 = true;\n  const DVIZH_AI_HOME_MODE_STABLE_V1 = true;',
        1,
    )
app.write_text(text,encoding='utf-8')

# Do not depend on the service worker's cache-variable name. Previous modules
# may have already rewritten it. A byte-level SW change is enough to trigger
# an update check, and the versioned app.js URL below avoids the old cached JS.
s=sw.read_text(encoding='utf-8')
marker='// DVIZH_AI_HOME_MODE_STABLE_SW_V2'
if marker not in s:
    sw.write_text(s.rstrip()+"\n"+marker+"\n",encoding='utf-8')

# Cache-bust app.js if the static HTML has a direct app.js script reference.
# This is deliberately optional: some deployed variants inject the bundle in
# another way, while the SW byte change above remains safe for all variants.
if index.is_file():
    html=index.read_text(encoding='utf-8')
    pattern=r"(src=[\"'](?:\./|/)?app\.js)(?:\?[^\"']*)?([\"'])"
    html2,n=re.subn(pattern, r"\1?v=dvizh-ai-home-mode-stable-v2\2", html, count=1)
    if n:
        index.write_text(html2,encoding='utf-8')
PY

if command -v node >/dev/null 2>&1; then node --check "$APP" >/dev/null; fi
grep -q 'DVIZH_AI_HOME_MODE_STABLE_V1' "$APP"
grep -q 'DVIZH_AI_HOME_MODE_STABLE_SW_V2' "$SW"

if [[ -z "$TEST_ROOT" ]]; then
  # Backend services are intentionally untouched; verify only that they remain healthy.
  systemctl is-active --quiet dvizh.service
  systemctl is-active --quiet dvizh-ai-home.service
  systemctl is-active --quiet dvizh-ai-approval.service
fi

echo "DVIZH AI Home mode stability fix installed: $VERSION"
echo "Backup: $BACKUP_DIR"
echo "Полностью закрой ДВИЖ и открой снова, чтобы браузер взял обновлённый JS."
