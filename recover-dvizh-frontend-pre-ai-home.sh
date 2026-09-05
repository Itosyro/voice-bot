#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-pre-ai-home-recovery.1"
TEST_ROOT="${DVIZH_PRE_AI_RECOVERY_ROOT:-}"
BACKUPS_ROOT="${DVIZH_PRE_AI_BACKUPS_ROOT:-/var/lib/dvizh/backups}"

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

INDEX="$APP_ROOT/index.html"
APP="$APP_ROOT/app.js"
CSS="$APP_ROOT/styles.css"
SW="$APP_ROOT/sw.js"
for f in "$INDEX" "$APP" "$CSS" "$SW"; do
  [[ -f "$f" ]] || { echo "Не найден файл: $f" >&2; exit 1; }
done

SOURCE=""
while IFS= read -r dir; do
  [[ -f "$dir/static/app.js" && -f "$dir/static/styles.css" ]] || continue
  if ! grep -q 'DVIZH_AI_HOME_V1' "$dir/static/app.js"; then
    SOURCE="$dir"
    break
  fi
done < <(find "$BACKUPS_ROOT" -maxdepth 1 -mindepth 1 -type d -name 'ai-home-*' -print 2>/dev/null | sort)

[[ -n "$SOURCE" ]] || {
  echo "Не найден backup фронтенда, созданный до AI Home. Ничего не изменено." >&2
  exit 1
}

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -n "$TEST_ROOT" ]]; then
  CURRENT_BACKUP="$APP_ROOT/.pre-ai-recovery-current"
  mkdir -p "$CURRENT_BACKUP"
else
  CURRENT_BACKUP="$BACKUPS_ROOT/frontend-recovery-pre-ai-$STAMP"
  install -d -o root -g root -m 0700 "$CURRENT_BACKUP"
fi
cp -a "$INDEX" "$CURRENT_BACKUP/index.html"
cp -a "$APP" "$CURRENT_BACKUP/app.js"
cp -a "$CSS" "$CURRENT_BACKUP/styles.css"
cp -a "$SW" "$CURRENT_BACKUP/sw.js"

cp -a "$SOURCE/static/app.js" "$APP"
cp -a "$SOURCE/static/styles.css" "$CSS"

python3 - "$INDEX" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1])
text=p.read_text(encoding='utf-8')
# Remove only the hard-stability early-boot block added after AI Home.
text=re.sub(
    r'\s*<!-- DVIZH_AI_HOME_EARLY_BOOT_V2 -->\s*<script>.*?</script>\s*<style>.*?</style>\s*',
    '\n', text, flags=re.S, count=1,
)
# Force fresh manual-UI assets without depending on old browser caches.
text=re.sub(r'(src=["\'](?:\./|/)?app\.js)(?:\?[^"\']*)?(["\'])',
            r'\1?v=dvizh-pre-ai-recovery-v1\2', text, count=1)
text=re.sub(r'(href=["\'](?:\./|/)?styles\.css)(?:\?[^"\']*)?(["\'])',
            r'\1?v=dvizh-pre-ai-recovery-v1\2', text, count=1)
p.write_text(text,encoding='utf-8')
PY

# Keep the worker deliberately network-only during recovery. This prevents any
# cached AI Home bundle from being served after the rollback.
cat > "$SW" <<'SW'
// DVIZH_PRE_AI_RECOVERY_NETWORK_ONLY_SW_V1
self.addEventListener('install', event => { self.skipWaiting(); });
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(fetch(event.request, {cache: 'no-store'}));
});
SW

if command -v node >/dev/null 2>&1; then
  node --check "$APP" >/dev/null
fi

grep -q 'dvizh-pre-ai-recovery-v1' "$INDEX"
grep -q 'DVIZH_PRE_AI_RECOVERY_NETWORK_ONLY_SW_V1' "$SW"
if grep -q 'DVIZH_AI_HOME_V1' "$APP"; then
  echo "Recovery validation failed: AI Home marker remains in app.js" >&2
  exit 1
fi

if [[ -z "$TEST_ROOT" ]]; then
  systemctl is-active --quiet dvizh.service
  systemctl is-active --quiet dvizh-auth.service
  systemctl is-active --quiet dvizh-ai-approval.service
  curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
fi

echo "DVIZH frontend recovered to pre-AI Home state: $VERSION"
echo "Source backup: $SOURCE"
echo "Current broken frontend backup: $CURRENT_BACKUP"
echo "Databases, tasks, Hermes, proposals and backend services were not modified."
echo "Полностью закрой сайт во всех браузерах и открой снова."
