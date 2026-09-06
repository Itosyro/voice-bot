#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-manual-jump-diagnostic.1"
TEST_ROOT="${DVIZH_MANUAL_DIAG_ROOT:-}"

for tool in python3 sha256sum grep find cmp; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/app.js ]]; then
  APP_ROOT=/opt/dvizh/static
elif [[ -f /opt/dvizh/app.js ]]; then
  APP_ROOT=/opt/dvizh
else
  echo "Не найден live app.js ДВИЖа." >&2
  exit 1
fi
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"
APP="$APP_ROOT/app.js"
MANUAL="$APP_ROOT/manual.html"
INDEX="$APP_ROOT/index.html"
CSS="$APP_ROOT/styles.css"
SW="$APP_ROOT/sw.js"

for f in "$APP" "$MANUAL" "$INDEX" "$CSS" "$SW"; do
  [[ -f "$f" && ! -L "$f" ]] || { echo "Нет безопасного обычного файла: $f" >&2; exit 1; }
done

snapshot() {
  for name in index.html manual.html app.js styles.css sw.js ai-home-v2.js ai-home-v2.css ai-home-v2-preview.html; do
    if [[ -f "$APP_ROOT/$name" && ! -L "$APP_ROOT/$name" ]]; then
      sha256sum "$APP_ROOT/$name"
    fi
  done | sort
}
BEFORE="$(snapshot)"

echo "=== DVIZH manual mode jump diagnostic ==="
echo "version=$VERSION"
echo "app_root=$APP_ROOT"
echo
echo "--- live file identity ---"
for f in "$MANUAL" "$APP" "$CSS" "$SW"; do
  printf '%s  bytes=%s  sha256=%s\n' "$(basename "$f")" "$(wc -c < "$f")" "$(sha256sum "$f" | awk '{print $1}')"
done

echo
echo "--- manual document asset references ---"
python3 - "$MANUAL" <<'PY'
from pathlib import Path
import re, sys
text=Path(sys.argv[1]).read_text(encoding='utf-8',errors='replace')
for m in re.finditer(r'(?i)(?:src|href)\s*=\s*["\']([^"\']+)["\']', text):
    value=m.group(1)
    if any(x in value for x in ('app.js','styles.css','sw.js','boot.js','sync.js')):
        print(value)
PY

echo
echo "--- app.js periodic / render / navigation signals ---"
python3 - "$APP" <<'PY'
from pathlib import Path
import re, sys
p=Path(sys.argv[1]); lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
patterns=[
 ('timer', re.compile(r'\b(setInterval|setTimeout|requestAnimationFrame)\s*\(')),
 ('state/network', re.compile(r'(?i)(/api/state|fetch\s*\(|XMLHttpRequest|revision|sync)')),
 ('render', re.compile(r'(?i)(\brender\w*\s*\(|innerHTML\s*=|outerHTML\s*=|replaceChildren\s*\(|insertAdjacentHTML\s*\()')),
 ('scroll/focus', re.compile(r'(?i)(scrollTo\s*\(|scrollIntoView\s*\(|\.focus\s*\(|visualViewport|window\.innerHeight|window\.innerWidth)')),
 ('lifecycle', re.compile(r'(?i)(visibilitychange|pageshow|pagehide|focus|blur|resize|popstate|hashchange|location\.pathname|location\.href)')),
]
selected=[]
for i,line in enumerate(lines,1):
    kinds=[name for name,rx in patterns if rx.search(line)]
    if kinds:
        selected.append((i,','.join(kinds),line.strip()))
print(f'lines={len(lines)} matches={len(selected)}')
for i,kinds,line in selected[:220]:
    if len(line)>300: line=line[:297]+'...'
    print(f'{i}:{kinds}:{line}')
if len(selected)>220: print(f'... capped; {len(selected)-220} more matches ...')

print('\n--- literal timer delays ---')
text='\n'.join(lines)
for name in ('setInterval','setTimeout'):
    vals=[]
    for m in re.finditer(rf'{name}\s*\([^;]{{0,700}}?,\s*(\d{{2,8}})\s*\)', text, re.S):
        vals.append(m.group(1))
    print(name + '=' + (','.join(vals[:40]) if vals else '<no simple literal delays detected>'))
PY

echo
echo "--- current app.js versus server backups (hash only) ---"
if [[ -z "$TEST_ROOT" && -d /var/lib/dvizh/backups ]]; then
  current_hash="$(sha256sum "$APP" | awk '{print $1}')"
  found=0
  while IFS= read -r candidate; do
    [[ -f "$candidate" && ! -L "$candidate" ]] || continue
    found=$((found+1))
    h="$(sha256sum "$candidate" | awk '{print $1}')"
    relation=DIFFERENT
    [[ "$h" == "$current_hash" ]] && relation=SAME
    printf '%s  %s\n' "$relation" "$candidate"
    [[ $found -ge 40 ]] && break
  done < <(find /var/lib/dvizh/backups -maxdepth 3 -type f -name app.js -print 2>/dev/null | sort -r)
  [[ $found -gt 0 ]] || echo "No backup app.js candidates found within depth 3."
else
  echo "Backup comparison skipped in fixture mode."
fi

echo
echo "--- service worker marker lines ---"
grep -nE 'DVIZH_|addEventListener|caches\.|respondWith|fetch\(' "$SW" | head -80 || true

AFTER="$(snapshot)"
if [[ "$BEFORE" != "$AFTER" ]]; then
  echo "ERROR: files changed during read-only diagnostic." >&2
  exit 90
fi

echo
echo "RESULT: read-only manual diagnostic complete; site files unchanged."
