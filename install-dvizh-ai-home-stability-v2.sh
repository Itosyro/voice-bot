#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-stability-v2.1"
TEST_ROOT="${DVIZH_AI_HOME_STABILITY_V2_ROOT:-}"

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
[[ -f "$APP" && -f "$CSS" && -f "$SW" && -f "$INDEX" ]] || { echo "Не найдены index.html/app.js/styles.css/sw.js" >&2; exit 1; }
grep -q 'DVIZH_AI_HOME_V1' "$APP" || { echo "AI Home v1 не найден." >&2; exit 1; }

if [[ -z "$TEST_ROOT" ]]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  BACKUP_DIR="/var/lib/dvizh/backups/ai-home-stability-v2-$STAMP"
  install -d -o root -g root -m 0700 "$BACKUP_DIR"
else
  BACKUP_DIR="$APP_ROOT/.ai-home-stability-v2-backup"
  mkdir -p "$BACKUP_DIR"
fi
cp -a "$INDEX" "$BACKUP_DIR/index.html"
cp -a "$APP" "$BACKUP_DIR/app.js"
cp -a "$CSS" "$BACKUP_DIR/styles.css"
cp -a "$SW" "$BACKUP_DIR/sw.js"

python3 - "$INDEX" "$APP" "$CSS" "$SW" <<'PY'
from pathlib import Path
import re,sys
index,app,css,sw = map(Path, sys.argv[1:])

html=index.read_text(encoding='utf-8')
js=app.read_text(encoding='utf-8')
style=css.read_text(encoding='utf-8')

EARLY='DVIZH_AI_HOME_EARLY_BOOT_V2'
if EARLY not in html:
    block=r'''<!-- DVIZH_AI_HOME_EARLY_BOOT_V2 -->
<script>
(function(){
  var KEY='dvizh:ai-home:manual:v2';
  function manual(){ try { return localStorage.getItem(KEY)==='1'; } catch(_) { return false; } }
  if (!manual()) document.documentElement.classList.add('dvizh-ai-home-active','dvizh-ai-home-early');
  window.__dvizhAiHomeSetManual=function(on){
    try { localStorage.setItem(KEY,on?'1':'0'); } catch(_) {}
    document.documentElement.classList.toggle('dvizh-ai-home-active',!on);
    document.documentElement.classList.toggle('dvizh-ai-home-early',!on);
  };
  window.addEventListener('load',function(){
    if (!manual()) document.documentElement.classList.add('dvizh-ai-home-active');
    if ('caches' in window) caches.keys().then(function(keys){ return Promise.all(keys.map(function(k){ return caches.delete(k); })); }).catch(function(){});
    if ('serviceWorker' in navigator) navigator.serviceWorker.getRegistration().then(function(r){ if(r) r.update().catch(function(){}); }).catch(function(){});
  },{once:true});
})();
</script>
<style>
html.dvizh-ai-home-active #view-home > :not(#aiHomeShell):not(#aiProposalPanel){display:none!important}
html.dvizh-ai-home-active #view-home #aiHomeShell{display:grid!important}
html:not(.dvizh-ai-home-active) #view-home #aiHomeShell{display:none!important}
html.dvizh-ai-home-early #view-home{min-height:70vh}
html.dvizh-ai-home-early #view-home:not(:has(#aiHomeShell)){visibility:hidden!important}
#aiProposalPanel[hidden]{display:none!important}
</style>
'''
    pos=html.lower().find('</head>')
    if pos < 0:
        raise SystemExit('index.html has no </head>')
    html=html[:pos]+block+html[pos:]

# Force unique URLs so a stale worker/browser cache cannot alternate old/new assets.
html=re.sub(r"(src=[\"'](?:\./|/)?app\.js)(?:\?[^\"']*)?([\"'])",r"\1?v=dvizh-ai-home-stability-v2-1\2",html,count=1)
html=re.sub(r"(href=[\"'](?:\./|/)?styles\.css)(?:\?[^\"']*)?([\"'])",r"\1?v=dvizh-ai-home-stability-v2-1\2",html,count=1)
index.write_text(html,encoding='utf-8')

MARK='DVIZH_AI_HOME_STABILITY_V2'
if MARK not in js:
    anchor='  const DVIZH_AI_HOME_V1 = true;'
    if anchor not in js: anchor='const DVIZH_AI_HOME_V1 = true;'
    if anchor not in js: raise SystemExit('AI Home JS marker missing')
    js=js.replace(anchor,anchor+"\n  const DVIZH_AI_HOME_STABILITY_V2 = true;",1)

# Persist explicit manual/AI choice on the root element. This survives ordinary re-renders.
manual_anchor="document.documentElement.classList.remove('dvizh-ai-home-active');"
if manual_anchor in js and "__dvizhAiHomeSetManual(true)" not in js:
    js=js.replace(manual_anchor,"if (window.__dvizhAiHomeSetManual) window.__dvizhAiHomeSetManual(true); else document.documentElement.classList.remove('dvizh-ai-home-active');",1)
back_anchor="document.documentElement.classList.add('dvizh-ai-home-active');"
# Replace the first explicit back-to-AI occurrence that appears after the manual handler if possible.
if "__dvizhAiHomeSetManual(false)" not in js:
    idx=js.find(manual_anchor)
    search_from=max(0,idx)
    pos=js.find(back_anchor,search_from)
    if pos >= 0:
        js=js[:pos]+"if (window.__dvizhAiHomeSetManual) window.__dvizhAiHomeSetManual(false); else document.documentElement.classList.add('dvizh-ai-home-active');"+js[pos+len(back_anchor):]

# Reassert root mode if another renderer removes it, but never override explicit manual mode.
if 'DVIZH_AI_HOME_ROOT_GUARD_V2' not in js:
    guard=r'''
  const DVIZH_AI_HOME_ROOT_GUARD_V2 = true;
  function aiHomeRootGuard() {
    let manual=false;
    try { manual=localStorage.getItem('dvizh:ai-home:manual:v2')==='1'; } catch (_) {}
    if (!manual) document.documentElement.classList.add('dvizh-ai-home-active');
  }
  if (typeof MutationObserver !== 'undefined') {
    new MutationObserver(aiHomeRootGuard).observe(document.documentElement,{attributes:true,attributeFilter:['class']});
  }
  window.addEventListener('pageshow',aiHomeRootGuard);
  window.addEventListener('focus',aiHomeRootGuard);
'''
    insert=js.find('  function aiHomeData()')
    if insert < 0: insert=js.find('function aiHomeData()')
    if insert < 0: raise SystemExit('aiHomeData anchor missing')
    js=js[:insert]+guard+'\n'+js[insert:]
app.write_text(js,encoding='utf-8')

if '/* DVIZH_AI_HOME_STABILITY_V2 */' not in style:
    style += r'''

/* DVIZH_AI_HOME_STABILITY_V2 */
html.dvizh-ai-home-active #view-home > :not(#aiHomeShell):not(#aiProposalPanel){display:none!important}
html.dvizh-ai-home-active #view-home #aiHomeShell{display:grid!important}
html:not(.dvizh-ai-home-active) #view-home #aiHomeShell{display:none!important}
#aiProposalPanel[hidden]{display:none!important}
'''
css.write_text(style,encoding='utf-8')

# Replace the worker with a network-only worker. No app shell cache => no old/new UI alternation.
worker=r'''// DVIZH_AI_HOME_NETWORK_ONLY_SW_V2
self.addEventListener('install',event=>{self.skipWaiting();});
self.addEventListener('activate',event=>{event.waitUntil((async()=>{const keys=await caches.keys();await Promise.all(keys.map(k=>caches.delete(k)));await self.clients.claim();})());});
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET') return;
  event.respondWith(fetch(event.request,{cache:'no-store'}));
});
'''
sw.write_text(worker,encoding='utf-8')
PY

if command -v node >/dev/null 2>&1; then node --check "$APP" >/dev/null; fi
grep -q 'DVIZH_AI_HOME_EARLY_BOOT_V2' "$INDEX"
grep -q 'DVIZH_AI_HOME_STABILITY_V2' "$APP"
grep -q 'DVIZH_AI_HOME_ROOT_GUARD_V2' "$APP"
grep -q 'DVIZH_AI_HOME_NETWORK_ONLY_SW_V2' "$SW"
grep -q 'dvizh-ai-home-stability-v2-1' "$INDEX"

if [[ -z "$TEST_ROOT" ]]; then
  systemctl is-active --quiet dvizh.service
  systemctl is-active --quiet dvizh-ai-home.service
  systemctl is-active --quiet dvizh-ai-approval.service
fi

echo "DVIZH AI Home hard stability mode installed: $VERSION"
echo "Backup: $BACKUP_DIR"
echo "Service worker теперь network-only; старые cache storage удаляются на следующей загрузке."
echo "Полностью закрой ДВИЖ, открой снова и подержи экран открытым 60 секунд."
