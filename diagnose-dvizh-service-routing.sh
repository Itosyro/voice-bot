#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-dvizh-service-routing-diagnostic.2"

for tool in systemctl readlink find grep sha256sum python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

APP_ROOT=""
if [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT=/opt/dvizh/static
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT=/opt/dvizh
fi

snapshot_site() {
  [[ -n "$APP_ROOT" ]] || return 0
  for name in index.html manual.html app.js styles.css sw.js ai-home-v2-preview.html ai-home-v2.js ai-home-v2.css; do
    if [[ -f "$APP_ROOT/$name" && ! -L "$APP_ROOT/$name" ]]; then
      sha256sum "$APP_ROOT/$name"
    fi
  done | sort
}

BEFORE="$(snapshot_site)"

echo "=== DVIZH service routing diagnostic ==="
echo "version=$VERSION"
echo "app_root=${APP_ROOT:-unknown}"
echo
echo "--- dvizh.service metadata (read only; ExecStart intentionally omitted) ---"
systemctl show dvizh.service --no-pager \
  -p ActiveState -p SubState -p MainPID -p FragmentPath -p WorkingDirectory

PID="$(systemctl show dvizh.service -p MainPID --value)"
if [[ "$PID" =~ ^[0-9]+$ && "$PID" -gt 0 && -d "/proc/$PID" ]]; then
  echo
  echo "--- running process (environment not read; argv secrets redacted) ---"
  printf 'pid=%s\n' "$PID"
  printf 'exe=%s\n' "$(readlink -f "/proc/$PID/exe" 2>/dev/null || true)"
  printf 'cwd=%s\n' "$(readlink -f "/proc/$PID/cwd" 2>/dev/null || true)"
  python3 - "$PID" <<'PY'
from pathlib import Path
import re, sys
pid = sys.argv[1]
try:
    parts = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
except OSError as exc:
    print('argv=<unreadable: %s>' % exc.__class__.__name__)
    raise SystemExit(0)
parts = [p.decode('utf-8', 'replace') for p in parts if p]
secret_flag = re.compile(r'(?i)(token|secret|password|passwd|api[-_]?key|authorization|cookie|credential)')
out=[]
redact_next=False
for part in parts:
    if redact_next:
        out.append('<redacted>'); redact_next=False; continue
    if part.startswith('-') and secret_flag.search(part):
        if '=' in part:
            out.append(part.split('=',1)[0] + '=<redacted>')
        else:
            out.append(part); redact_next=True
        continue
    if secret_flag.search(part) and '=' in part:
        out.append(part.split('=',1)[0] + '=<redacted>')
    else:
        out.append(part)
print('argv=' + ' '.join(out))
PY
fi

echo
echo "--- probable server source files ---"
WORKDIR="$(systemctl show dvizh.service -p WorkingDirectory --value)"
ROOTS=()
if [[ -n "$WORKDIR" && "$WORKDIR" == /* && -d "$WORKDIR" ]]; then ROOTS+=("$WORKDIR"); fi
if [[ -d /opt/dvizh ]]; then ROOTS+=(/opt/dvizh); fi

if [[ ${#ROOTS[@]} -eq 0 ]]; then
  echo "No readable candidate source root found."
else
  python3 - "${ROOTS[@]}" <<'PY'
from pathlib import Path
import os, sys
roots=[]
seen=set()
for raw in sys.argv[1:]:
    try: p=Path(raw).resolve()
    except OSError: continue
    if p in seen: continue
    seen.add(p); roots.append(p)

skip_parts={'static','node_modules','.git','venv','.venv','__pycache__','backups','backup'}
exts={'.py','.js','.mjs','.cjs','.ts'}
files=[]
for root in roots:
    for base, dirs, names in os.walk(root):
        rel=Path(base).relative_to(root)
        if len(rel.parts) >= 4:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip_parts]
        for name in names:
            p=Path(base)/name
            if p.suffix.lower() not in exts: continue
            try:
                if p.stat().st_size > 1_000_000: continue
            except OSError: continue
            files.append(p)
for p in sorted(set(files)):
    print(p)
PY

  echo
  echo "--- routing-related source lines (secret-shaped values redacted) ---"
  python3 - "${ROOTS[@]}" <<'PY'
from pathlib import Path
import os, re, sys
roots=[]; seen=set()
for raw in sys.argv[1:]:
    try: p=Path(raw).resolve()
    except OSError: continue
    if p in seen: continue
    seen.add(p); roots.append(p)

skip_parts={'static','node_modules','.git','venv','.venv','__pycache__','backups','backup'}
exts={'.py','.js','.mjs','.cjs','.ts'}
route = re.compile(r'(?i)(manual\.html|index\.html|ai-home-v2-preview|StaticFiles|FileResponse|send_file|serveFile|/api/health|@\w+\.(?:get|route)|\bapp\.(?:get|use)\s*\(|\brouter\.(?:get|use)\s*\(|BaseHTTPRequestHandler|SimpleHTTPRequestHandler|path\s*==|pathname|static)')
secret = re.compile(r'(?i)((?:token|secret|password|passwd|api[-_]?key|authorization|cookie|credential)\s*[:=]\s*)([^,;\s]+|["\'][^"\']*["\'])')
count=0
for root in roots:
    for base, dirs, names in os.walk(root):
        rel=Path(base).relative_to(root)
        if len(rel.parts) >= 4:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in skip_parts]
        for name in sorted(names):
            p=Path(base)/name
            if p.suffix.lower() not in exts: continue
            try:
                if p.stat().st_size > 1_000_000: continue
                text=p.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(),1):
                if not route.search(line): continue
                line=secret.sub(r'\1<redacted>', line).strip()
                if len(line)>280: line=line[:277]+'...'
                print(f'{p}:{lineno}:{line}')
                count += 1
                if count >= 250:
                    print('... routing output capped at 250 matches ...')
                    raise SystemExit(0)
if count == 0:
    print('NO_ROUTING_SOURCE_MATCHES')
PY
fi

AFTER="$(snapshot_site)"
if [[ "$BEFORE" != "$AFTER" ]]; then
  echo "ERROR: site-file snapshot changed during a read-only diagnostic." >&2
  exit 90
fi

echo
echo "RESULT: read-only service routing probe complete; site files unchanged."
