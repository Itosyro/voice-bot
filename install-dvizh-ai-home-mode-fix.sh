#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-mode-fix.3"
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
grep -q 'DVIZH_AI_HOME_V1' "$APP" || { echo "AI Home v1 не найден." >&2; exit 1; }

if [[ -z "$TEST_ROOT" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_DIR="/var/lib/dvizh/backups/ai-home-mode-fix-$STAMP"
  install -d -o root -g root -m 0700 "$BACKUP_DIR"
else
  BACKUP_DIR="$APP_ROOT/.mode-fix-backup"
  mkdir -p "$BACKUP_DIR"
fi
cp -a "$APP" "$BACKUP_DIR/app.js"
cp -a "$SW" "$BACKUP_DIR/sw.js"
[[ -f "$INDEX" ]] && cp -a "$INDEX" "$BACKUP_DIR/index.html"

python3 - "$APP" "$SW" "$INDEX" <<'PY'
from pathlib import Path
import re,sys

app=Path(sys.argv[1]); sw=Path(sys.argv[2]); index=Path(sys.argv[3])
text=app.read_text(encoding='utf-8')
marker='DVIZH_AI_HOME_MODE_STABLE_V1'

if marker not in text:
    # Remove the forced mode switch specifically from aiHomeEnsureRoot().
    start=text.find('function aiHomeEnsureRoot()')
    if start < 0:
        raise SystemExit('Не найден aiHomeEnsureRoot')
    root_anchor="let root = document.getElementById('aiHomeShell');"
    root_pos=text.find(root_anchor,start)
    if root_pos < 0:
        raise SystemExit('Не найден aiHomeShell anchor')
    mode="home.classList.add('ai-home-mode');"
    mode_pos=text.find(mode,start,root_pos)
    if mode_pos < 0:
        raise SystemExit('Не найден принудительный ai-home-mode в aiHomeEnsureRoot')
    line_start=text.rfind('\n',start,mode_pos)+1
    line_end=text.find('\n',mode_pos)
    if line_end < 0:
        line_end=mode_pos+len(mode)
    else:
        line_end+=1
    text=text[:line_start]+text[line_end:]

    # Enable AI Home once on boot instead of on every periodic render.
    boot=text.find('function aiHomeBoot()')
    if boot < 0:
        raise SystemExit('Не найден aiHomeBoot')
    next_func=text.find('\n  function ',boot+1)
    boot_end=next_func if next_func >= 0 else min(len(text),boot+1200)
    boot_block=text[boot:boot_end]
    if mode not in boot_block:
        brace=text.find('{',boot)
        if brace < 0 or brace >= boot_end:
            raise SystemExit('Не найдено тело aiHomeBoot')
        line_start=text.rfind('\n',0,boot)+1
        indent=text[line_start:boot]
        body_indent=indent+'  '
        injection=("\n"+body_indent+"const home = document.getElementById('view-home');"
                   "\n"+body_indent+"if (home) home.classList.add('ai-home-mode');")
        text=text[:brace+1]+injection+text[brace+1:]

    # Add a stable marker next to the AI Home feature marker regardless of indentation.
    m=re.search(r'(?m)^(\s*)const\s+DVIZH_AI_HOME_V1\s*=\s*true;\s*$',text)
    if not m:
        raise SystemExit('Не найден DVIZH_AI_HOME_V1 marker')
    indent=m.group(1)
    text=text[:m.end()]+f"\n{indent}const {marker} = true;"+text[m.end():]

app.write_text(text,encoding='utf-8')

# Cache-agnostic refresh: do not parse/rewrite CACHE/CACHE_NAME because earlier
# DVIZH modules may have changed that declaration. Changing SW bytes triggers
# an update check; the versioned app.js URL prevents reuse of the old bundle.
s=sw.read_text(encoding='utf-8')
sw_marker='// DVIZH_AI_HOME_MODE_STABLE_SW_V3'
if sw_marker not in s:
    sw.write_text(s.rstrip()+"\n"+sw_marker+"\n",encoding='utf-8')

if index.is_file():
    html=index.read_text(encoding='utf-8')
    pattern=r"(src=[\"'](?:\./|/)?app\.js)(?:\?[^\"']*)?([\"'])"
    html2,n=re.subn(pattern,r"\1?v=dvizh-ai-home-mode-stable-v3\2",html,count=1)
    if n:
        index.write_text(html2,encoding='utf-8')
PY

if command -v node >/dev/null 2>&1; then node --check "$APP" >/dev/null; fi
grep -q 'DVIZH_AI_HOME_MODE_STABLE_V1' "$APP"
grep -q 'DVIZH_AI_HOME_MODE_STABLE_SW_V3' "$SW"

if [[ -z "$TEST_ROOT" ]]; then
  systemctl is-active --quiet dvizh.service
  systemctl is-active --quiet dvizh-ai-home.service
  systemctl is-active --quiet dvizh-ai-approval.service
fi

echo "DVIZH AI Home mode stability fix installed: $VERSION"
echo "Backup: $BACKUP_DIR"
echo "Полностью закрой ДВИЖ и открой снова, чтобы браузер взял обновлённый JS."
