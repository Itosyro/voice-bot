#!/usr/bin/env bash
set -Eeuo pipefail

REPO='Itosyro/voice-bot'
SRC_BRANCH='chatgpt/dvizh-daily-stability-2026-09-14'
SRC_BASE='946419c5b41f29c84b4a4597ee86f8e44b7092a8'
REL_BRANCH='hermes/dev/owner-daily-stability-20260914'
GATE='/usr/local/sbin/dvizhrelease'
GATE_VERSION='2026.09.10-dvizh-release-gate.2.2.1-state-root'
ROOT='/opt/dvizh/static'
HTTP='http://127.0.0.1:8000'

log(){ printf '[DVIZH] %s\n' "$*"; }
fail(){ printf '[DVIZH] ERROR: %s\n' "$*" >&2; exit 1; }
for c in git gh curl python3 sha256sum stat cmp sudo systemctl mktemp awk sleep date; do command -v "$c" >/dev/null || fail "Нет команды: $c"; done
[[ ${EUID:-$(id -u)} -ne 0 ]] || fail 'Запускай обычным пользователем exedev, не через sudo bash.'
[[ -r /dev/tty && -w /dev/tty ]] || fail 'Нужен интерактивный терминал.'
[[ -x "$GATE" && ! -L "$GATE" ]] || fail 'Защитный release gate не найден.'
umask 077
TMP=$(mktemp -d); trap 'rm -rf -- "$TMP"' EXIT
sha(){ sha256sum "$1" | awk '{print $1}'; }

declare -A BEFORE=(
 [sync.js]=04e10a67cb566180ec3590dae4b73dc19f3bb2083fca6ec7002e987a3bb63a71
 [app.js]=c6882d8821515f0046742e99cce10ed9b8115fabd4c7cd0a06c830a25a6366bf
 [ai-home-v2.js]=3ae439ba11611bd5ec5ea0c61e81245e9032fba36396c4ffeeaebc871c5fb186
 [index.html]=973bd18e8086cad28d889a10768e94d8b85ca086c4a0cbac4887ef6a9f8f2ebc
 [manual.html]=8bfc125485dab2e6134ca5154991bad7869d3f9d3503dae4449f8bec55599797
)
declare -A AFTER=(
 [sync.js]=58991ea1a0d95facbe21402792e7607d6c4ff55603234b808f646cd8b5f5c12e
 [app.js]=41cd3d0683eabdf649c47878ad214408af1acb9c93352fe1c12302adc248b84e
 [ai-home-v2.js]=b8538939f48be484d21eaa56c991fc237b20188f917eed3c65ae07cb25baaf76
 [index.html]=41bc4d1509c5818675d488164f01e35bf8dcdb35c15d660c38fde72f7a77ee02
 [manual.html]=9a0847bc1e9b0bcd2c775974c94994d8c49979fb5316ce6372e408c283fee514
)
declare -A KEEP=(
 [styles.css]=4fc9de09753daffb3dcacba770684b7f6a152c23a9956fb85a797beba068c8c5
 [ai-home-v2.css]=a43b073c4788e1ba93240fb46bc726b1e07edfdbe653183e0a115a01ffdb42fb
 [boot.js]=1c766410e239a8092de001d6450da6fabcdd552a91f7de593abb0d626fbb0500
 [sw.js]=7065b95ceac21bf528eeef9635a0b67141fac2e5135dc51e9aaf3c0c085fe86d
)
health(){ curl -fsS --connect-timeout 5 --max-time 15 "$HTTP/api/health" | python3 -c 'import json,sys;d=json.load(sys.stdin);raise SystemExit(0 if d.get("ok") is True and d.get("app")=="dvizh" else 1)'; }
services(){ for s in dvizh.service dvizh-ai-home.service dvizh-ai-approval.service; do systemctl is-active --quiet "$s" || return 1; done; }
keep(){ for n in "${!KEEP[@]}"; do [[ -f "$ROOT/$n" && ! -L "$ROOT/$n" && "$(sha "$ROOT/$n")" == "${KEEP[$n]}" ]] || return 1; done; }

state=''
for n in "${!BEFORE[@]}"; do
 p="$ROOT/$n"; [[ -f "$p" && ! -L "$p" ]] || fail "Нет безопасного $p"
 [[ "$(stat -c '%h:%u:%g:%a' "$p")" == '1:0:0:644' ]] || fail "Неожиданные права $n"
 h=$(sha "$p"); x=unknown; [[ "$h" == "${BEFORE[$n]}" ]] && x=before; [[ "$h" == "${AFTER[$n]}" ]] && x=after
 [[ "$x" != unknown ]] || fail "$n не совпадает ни с preflight, ни с release."
 [[ -z "$state" || "$state" == "$x" ]] || fail 'Обнаружена частично установленная версия; ничего не меняю.'
 state=$x
done
keep || fail 'Изменился защищённый static-файл.'
health || fail '/api/health не прошёл.'
services || fail 'Не все сервисы DVIZH active.'
[[ "$state" != after ]] || { log 'Обновление уже установлено и проверено.'; exit 0; }
log 'Production точно совпадает с проверенным baseline.'

gh auth status -h github.com >/dev/null 2>&1 || fail 'gh не авторизован в GitHub. Production не изменён.'
ver=$(python3 - "$GATE" <<'PY'
import ast,pathlib,sys
try:t=ast.parse(pathlib.Path(sys.argv[1]).read_text())
except Exception: print(''); raise SystemExit
for n in t.body:
 if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='VERSION' for x in n.targets) and isinstance(n.value,ast.Constant): print(n.value.value); break
PY
)
[[ "$ver" == "$GATE_VERSION" ]] || fail "Release gate изменился: ${ver:-unknown}."
sudo "$GATE" doctor >"$TMP/doctor.json" || fail 'release gate doctor не прошёл.'
python3 - "$TMP/doctor.json" <<'PY' || fail 'release gate doctor вернул ok!=true.'
import json,sys
raise SystemExit(0 if json.load(open(sys.argv[1])).get('ok') is True else 1)
PY

log 'Собираю exact candidate из GitHub и повторяю ключевые тесты...'
R="$TMP/repo"
git clone -q --no-tags --single-branch --branch "$SRC_BRANCH" "https://github.com/$REPO.git" "$R"
head=$(git -C "$R" rev-parse HEAD); parent=$(git -C "$R" rev-parse HEAD^ 2>/dev/null || true)
D="$R/minimal-ui-v1/health-recovery-v1/daily-stability"; P="$D/release-payload"; M="$D/release-published.json"
verify_payload(){
 [[ -f "$M" ]] || return 1
 for n in sync.js app.js ai-home-v2.js index.html manual.html; do [[ -f "$P/$n" && "$(sha "$P/$n")" == "${AFTER[$n]}" ]] || return 1; done
 python3 - "$M" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); exp={'sync.js':('/opt/dvizh/static/sync.js','/sync.js'),'app.js':('/opt/dvizh/static/app.js','/app.js'),'ai-home-v2.js':('/opt/dvizh/static/ai-home-v2.js','/ai-home-v2.js'),'index.html':('/opt/dvizh/static/index.html','/'),'manual.html':('/opt/dvizh/static/manual.html','/manual.html')}
if x.get('schema')!=1 or x.get('name')!='20260914-daily-stability-1' or x.get('restarts')!=[] or len(x.get('operations',[]))!=5: raise SystemExit(1)
for r in x['operations']:
 n=r.get('source','').split('/')[-1]
 if n not in exp or (r.get('target'),r.get('http_path'))!=exp[n]: raise SystemExit(1)
PY
}
if [[ "$head" == "$SRC_BASE" ]]; then
 cd "$R"; python3 "$D/build.py"; python3 "$D/build.py" --check
 node --test "$D"/tests/*lifecycle.cjs >/dev/null; python3 "$D/tests/test_contract.py" >/dev/null
 rm -rf "$P"; mkdir -p "$P"; cp "$D"/dist/{sync.js,app.js,ai-home-v2.js,index.html,manual.html} "$P/"
 python3 - "$M" <<'PY'
import json,sys
base='minimal-ui-v1/health-recovery-v1/daily-stability/release-payload/'
rows=[('sync.js','/opt/dvizh/static/sync.js','/sync.js'),('app.js','/opt/dvizh/static/app.js','/app.js'),('ai-home-v2.js','/opt/dvizh/static/ai-home-v2.js','/ai-home-v2.js'),('index.html','/opt/dvizh/static/index.html','/'),('manual.html','/opt/dvizh/static/manual.html','/manual.html')]
x={'schema':1,'name':'20260914-daily-stability-1','operations':[{'source':base+n,'target':t,'http_path':h} for n,t,h in rows],'restarts':[]}
open(sys.argv[1],'w').write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
PY
 verify_payload || fail 'Собранный payload не совпал с exact candidate.'
 git config user.name 'DVIZH Owner Release'; git config user.email 'owner-release@dvizh.invalid'
 git add "$P" "$M"; git diff --cached --check; git commit -q -m 'Publish exact DVIZH daily stability release payload'
 rel=$(git rev-parse HEAD)
 GIT_TERMINAL_PROMPT=0 git -c credential.helper='!gh auth git-credential' push -q origin "HEAD:refs/heads/$SRC_BRANCH" || fail 'Не удалось опубликовать payload; production не менялся.'
elif [[ "$parent" == "$SRC_BASE" ]] && verify_payload; then rel=$head; log "Payload уже опубликован: $rel";
else fail "Ветка candidate неожиданно изменилась: $head"; fi

log "Жду два CI на exact commit $rel..."
dead=$((SECONDS+1200)); ok=0
while ((SECONDS<dead)); do
 gh api "repos/$REPO/actions/runs?head_sha=$rel&per_page=100" >"$TMP/runs.json"
 set +e
 python3 - "$TMP/runs.json" "$rel" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); c=sys.argv[2]; want={'DVIZH daily stability acceptance','DVIZH Health Recovery v1 acceptance'}
a={r.get('name'):r for r in x.get('workflow_runs',[]) if r.get('head_sha')==c and r.get('name') in want}
if any(a.get(n,{}).get('status')=='completed' and a.get(n,{}).get('conclusion') not in (None,'success') for n in want): raise SystemExit(1)
if all(a.get(n,{}).get('status')=='completed' and a.get(n,{}).get('conclusion')=='success' for n in want): raise SystemExit(0)
raise SystemExit(2)
PY
 rc=$?; set -e; [[ $rc == 0 ]] && { ok=1; break; }; [[ $rc == 1 ]] && fail 'Exact-head CI упал; production не менялся.'; sleep 12
done
[[ $ok == 1 ]] || fail 'Таймаут ожидания CI; production не менялся.'
log 'Оба exact-head CI зелёные.'

alias_sha=$(git -C "$R" ls-remote --heads origin "refs/heads/$REL_BRANCH" | awk '{print $1}')
if [[ -z "$alias_sha" ]]; then
 GIT_TERMINAL_PROMPT=0 git -C "$R" -c credential.helper='!gh auth git-credential' push -q origin "$rel:refs/heads/$REL_BRANCH" || fail 'Не удалось создать owner release alias.'
elif [[ "$alias_sha" != "$rel" ]]; then fail 'Owner release alias уже указывает на другой commit; force запрещён.'; fi
blob=$(git -C "$R" hash-object "$M")

S="$HOME/.hermes/dev/dvizh/state/autopilot"; mkdir -p "$S"; chmod 700 "$S"
pid="release-owner-daily-stability-${rel:0:10}"; prop="$S/$pid.json"
python3 - "$prop" "$pid" "$REL_BRANCH" "$rel" "$blob" <<'PY'
import datetime,json,os,sys
p,pid,b,c,blob=sys.argv[1:]; x={'schema':1,'id':pid,'mode':'safe','repo':'Itosyro/voice-bot','branch':b,'commit':c,'manifest':'minimal-ui-v1/health-recovery-v1/daily-stability/release-published.json','manifest_blob':blob,'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
t=p+'.tmp'; open(t,'w').write(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n'); os.chmod(t,0o600); os.replace(t,p)
PY
log 'Release gate строит точный план; production пока не меняется.'
sudo "$GATE" plan "$prop" >"$TMP/plan.json" || fail 'Gate отклонил план.'
mapfile -t a < <(python3 - "$TMP/plan.json" "$rel" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); c=sys.argv[2]
valid=x.get('ok') is True and x.get('approval_required') is True and x.get('risk')=='approval' and x.get('commit')==c and len(x.get('operations',[]))==5 and x.get('restarts')==[]
print(1 if valid else 0); print(x.get('approval_phrase') or ''); print(x.get('approval_token') or '')
PY
)
[[ "${a[0]:-0}" == 1 && -n "${a[1]:-}" && -n "${a[2]:-}" ]] || fail 'Неожиданный gate plan; apply запрещён.'
printf '\nГотово к установке. Изменятся ТОЛЬКО 5 файлов интерфейса, без рестартов.\nВставь ТОЧНО эту фразу:\n\n  %s\n\n> ' "${a[1]}" >/dev/tty
IFS= read -r typed </dev/tty; [[ "$typed" == "${a[1]}" ]] || fail 'Фраза не совпала; ничего не установлено.'
log 'Применяю через root-owned release gate...'
sudo "$GATE" apply "$prop" --approval "${a[2]}" >"$TMP/apply.json" || fail 'Apply завершился ошибкой; gate выполняет rollback. Не повторяй команду до проверки вывода.'
cat "$TMP/apply.json"
backup=$(python3 - "$TMP/apply.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]));
if x.get('ok') is not True or x.get('status')!='deployed': raise SystemExit(1)
print(x.get('backup') or '')
PY
) || fail 'Gate не подтвердил deployed.'
[[ -n "$backup" ]] || fail 'Gate не вернул backup path.'

for n in "${!AFTER[@]}"; do [[ "$(sha "$ROOT/$n")" == "${AFTER[$n]}" && "$(stat -c '%h:%u:%g:%a' "$ROOT/$n")" == '1:0:0:644' ]] || fail "Post-check $n не прошёл"; done
keep || fail 'Protected static post-check не прошёл.'
for row in 'sync.js:/sync.js' 'app.js:/app.js' 'ai-home-v2.js:/ai-home-v2.js' 'index.html:/' 'manual.html:/manual.html'; do n=${row%%:*}; path=${row#*:}; curl -fsS --max-time 15 "$HTTP$path?_dvizh=$(date +%s%N)" -o "$TMP/$n"; cmp -s "$P/$n" "$TMP/$n" || fail "HTTP bytes $path не совпали"; done
health || fail 'Post-check /api/health не прошёл.'; services || fail 'Post-check services не прошёл.'
log 'SUCCESS: daily stability установлена и проверена.'
log "Exact release commit: $rel"
log "Backup: $backup"
log 'Изменены только sync.js, app.js, ai-home-v2.js, index.html, manual.html. Личные данные не читались; синтетические записи не создавались; рестартов не было.'
