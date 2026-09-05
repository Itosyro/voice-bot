#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-root-mode-fix.1"
TEST_ROOT="${DVIZH_AI_HOME_ROOT_FIX_ROOT:-}"

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
CSS="$APP_ROOT/styles.css"
SW="$APP_ROOT/sw.js"
INDEX="$APP_ROOT/index.html"
[[ -f "$APP" && -f "$CSS" && -f "$SW" ]] || { echo "Не найдены app.js/styles.css/sw.js" >&2; exit 1; }
grep -q 'DVIZH_AI_HOME_V1' "$APP" || { echo "AI Home v1 не найден." >&2; exit 1; }

if [[ -z "$TEST_ROOT" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_DIR="/var/lib/dvizh/backups/ai-home-root-mode-fix-$STAMP"
  install -d -o root -g root -m 0700 "$BACKUP_DIR"
else
  BACKUP_DIR="$APP_ROOT/.root-mode-fix-backup"
  mkdir -p "$BACKUP_DIR"
fi
cp -a "$APP" "$BACKUP_DIR/app.js"
cp -a "$CSS" "$BACKUP_DIR/styles.css"
cp -a "$SW" "$BACKUP_DIR/sw.js"
[[ -f "$INDEX" ]] && cp -a "$INDEX" "$BACKUP_DIR/index.html"

python3 - "$APP" "$CSS" "$SW" "$INDEX" <<'PY'
from pathlib import Path
import re,sys
app=Path(sys.argv[1]); css=Path(sys.argv[2]); sw=Path(sys.argv[3]); index=Path(sys.argv[4])
text=app.read_text(encoding='utf-8')
marker='DVIZH_AI_HOME_ROOT_STABLE_V1'
if marker not in text:
    anchor='  const DVIZH_AI_HOME_V1 = true;'
    if anchor not in text:
        anchor='const DVIZH_AI_HOME_V1 = true;'
    if anchor not in text:
        raise SystemExit('AI Home marker anchor not found')
    text=text.replace(anchor, anchor+"\n  const DVIZH_AI_HOME_ROOT_STABLE_V1 = true;\n  document.documentElement.classList.add('dvizh-ai-home-active');",1)

    manual="document.getElementById('view-home')?.classList.remove('ai-home-mode');"
    if manual in text:
        text=text.replace(manual,"document.documentElement.classList.remove('dvizh-ai-home-active');\n      "+manual,1)
    else:
        raise SystemExit('manual-mode anchor not found')

    back="document.getElementById('view-home')?.classList.add('ai-home-mode');"
    if back in text:
        text=text.replace(back,"document.documentElement.classList.add('dvizh-ai-home-active');\n      "+back,1)
    else:
        raise SystemExit('AI-home back anchor not found')
app.write_text(text,encoding='utf-8')

c=css.read_text(encoding='utf-8')
css_marker='/* DVIZH_AI_HOME_ROOT_STABLE_V1 */'
if css_marker not in c:
    c += """

/* DVIZH_AI_HOME_ROOT_STABLE_V1 */
html.dvizh-ai-home-active #view-home > :not(#aiHomeShell):not(#aiProposalPanel) { display:none !important; }
html.dvizh-ai-home-active #view-home #aiHomeShell { display:grid !important; }
html:not(.dvizh-ai-home-active) #view-home #aiHomeShell { display:none !important; }
#aiProposalPanel[hidden] { display:none !important; }
"""
css.write_text(c,encoding='utf-8')

s=sw.read_text(encoding='utf-8')
sw_marker='// DVIZH_AI_HOME_ROOT_STABLE_SW_V1'
if sw_marker not in s:
    sw.write_text(s.rstrip()+"\n"+sw_marker+"\n",encoding='utf-8')

if index.is_file():
    html=index.read_text(encoding='utf-8')
    html=re.sub(r"(src=[\"'](?:\./|/)?app\.js)(?:\?[^\"']*)?([\"'])",r"\1?v=dvizh-ai-home-root-stable-v1\2",html,count=1)
    html=re.sub(r"(href=[\"'](?:\./|/)?styles\.css)(?:\?[^\"']*)?([\"'])",r"\1?v=dvizh-ai-home-root-stable-v1\2",html,count=1)
    index.write_text(html,encoding='utf-8')
PY

if command -v node >/dev/null 2>&1; then node --check "$APP" >/dev/null; fi
grep -q 'DVIZH_AI_HOME_ROOT_STABLE_V1' "$APP"
grep -q 'DVIZH_AI_HOME_ROOT_STABLE_V1' "$CSS"
grep -q 'DVIZH_AI_HOME_ROOT_STABLE_SW_V1' "$SW"

if [[ -z "$TEST_ROOT" ]]; then
  systemctl is-active --quiet dvizh.service
  systemctl is-active --quiet dvizh-ai-home.service
  systemctl is-active --quiet dvizh-ai-approval.service
fi

echo "DVIZH AI Home root-mode stability fix installed: $VERSION"
echo "Backup: $BACKUP_DIR"
echo "Полностью закрой ДВИЖ и открой снова."
