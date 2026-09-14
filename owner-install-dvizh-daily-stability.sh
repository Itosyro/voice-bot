#!/usr/bin/env bash
set -Eeuo pipefail

REPO="Itosyro/voice-bot"
SOURCE_BRANCH="chatgpt/dvizh-daily-stability-2026-09-14"
SOURCE_BASE="946419c5b41f29c84b4a4597ee86f8e44b7092a8"
RELEASE_BRANCH="hermes/dev/owner-daily-stability-20260914"
RELEASE_NAME="20260914-daily-stability-1"
GATE="/usr/local/sbin/dvizhrelease"
EXPECTED_GATE_VERSION="2026.09.10-dvizh-release-gate.2.2.1-state-root"
APP_ROOT="/opt/dvizh/static"
HTTP_BASE="http://127.0.0.1:8000"

log(){ printf '[DVIZH] %s\n' "$*"; }
die(){ printf '[DVIZH] ERROR: %s\n' "$*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"; }
for x in git gh curl python3 sha256sum stat cmp grep sudo systemctl mktemp mkdir chmod rm awk date sleep; do need "$x"; done
[[ ${EUID:-$(id -u)} -ne 0 ]] || die "Run as the normal DVIZH owner user, not via sudo bash."
[[ -r /dev/tty && -w /dev/tty ]] || die "Interactive /dev/tty is required for exact owner approval."
[[ -x "$GATE" && ! -L "$GATE" ]] || die "Installed release gate is missing or unsafe: $GATE"

umask 077
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

declare -A BEFORE=(
  [sync.js]="04e10a67cb566180ec3590dae4b73dc19f3bb2083fca6ec7002e987a3bb63a71"
  [app.js]="c6882d8821515f0046742e99cce10ed9b8115fabd4c7cd0a06c830a25a6366bf"
  [ai-home-v2.js]="3ae439ba11611bd5ec5ea0c61e81245e9032fba36396c4ffeeaebc871c5fb186"
  [index.html]="973bd18e8086cad28d889a10768e94d8b85ca086c4a0cbac4887ef6a9f8f2ebc"
  [manual.html]="8bfc125485dab2e6134ca5154991bad7869d3f9d3503dae4449f8bec55599797"
)
declare -A AFTER=(
  [sync.js]="58991ea1a0d95facbe21402792e7607d6c4ff55603234b808f646cd8b5f5c12e"
  [app.js]="41cd3d0683eabdf649c47878ad214408af1acb9c93352fe1c12302adc248b84e"
  [ai-home-v2.js]="b8538939f48be484d21eaa56c991fc237b20188f917eed3c65ae07cb25baaf76"
  [index.html]="41bc4d1509c5818675d488164f01e35bf8dcdb35c15d660c38fde72f7a77ee02"
  [manual.html]="9a0847bc1e9b0bcd2c775974c94994d8c49979fb5316ce6372e408c283fee514"
)
declare -A PRESERVED=(
  [styles.css]="4fc9de09753daffb3dcacba770684b7f6a152c23a9956fb85a797beba068c8c5"
  [ai-home-v2.css]="a43b073c4788e1ba93240fb46bc726b1e07edfdbe653183e0a115a01ffdb42fb"
  [boot.js]="1c766410e239a8092de001d6450da6fabcdd552a91f7de593abb0d626fbb0500"
  [sw.js]="7065b95ceac21bf528eeef9635a0b67141fac2e5135dc51e9aaf3c0c085fe86d"
)
sha(){ sha256sum "$1" | awk '{print $1}'; }
health_ok(){
  curl -fsS --connect-timeout 5 --max-time 15 -H 'Cache-Control: no-cache' "${HTTP_BASE}/api/health" |
  python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("ok") is True and d.get("app")=="dvizh" else 1)'
}
services_ok(){
  for svc in dvizh.service dvizh-ai-home.service dvizh-ai-approval.service; do
    systemctl is-active --quiet "$svc" || return 1
  done
}
check_preserved(){
  for name in "${!PRESERVED[@]}"; do
    local p="$APP_ROOT/$name"
    [[ -f "$p" && ! -L "$p" && "$(sha "$p")" == "${PRESERVED[$name]}" ]] || return 1
  done
}
set_state=""
for name in "${!BEFORE[@]}"; do
  p="$APP_ROOT/$name"
  [[ -f "$p" && ! -L "$p" ]] || die "Unsafe or missing live file: $p"
  meta="$(stat -c '%h:%u:%g:%a' "$p")"
  [[ "$meta" == "1:0:0:644" ]] || die "Unexpected ownership/mode for $name: $meta"
  actual="$(sha "$p")"
  state="unknown"
  [[ "$actual" == "${BEFORE[$name]}" ]] && state="before"
  [[ "$actual" == "${AFTER[$name]}" ]] && state="after"
  [[ "$state" != unknown ]] || die "Live $name is neither the approved preflight bytes nor the approved release bytes."
  if [[ -z "$set_state" ]]; then set_state="$state"; elif [[ "$set_state" != "$state" ]]; then die "Mixed partial frontend detected; stop for recovery instead of overwriting."; fi
done
check_preserved || die "A protected static file changed; refusing release."
health_ok || die "Application /api/health JSON contract is not healthy."
services_ok || die "One or more required DVIZH services are inactive."
if [[ "$set_state" == after ]]; then
  log "Daily stability release is already installed. Live bytes, protected files, services and /api/health are OK."
  exit 0
fi

log "Preflight matches the exact tested baseline. Checking owner GitHub access..."
gh auth status -h github.com >/dev/null 2>&1 || die "GitHub CLI is not authenticated for the owner session; no server files were changed."

log "Checking installed protected release-gate contract..."
gate_version="$(python3 - "$GATE" <<'PY'
import ast,pathlib,sys
try: tree=ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
except Exception: print(''); raise SystemExit
for n in tree.body:
    if isinstance(n,(ast.Assign,ast.AnnAssign)):
        ts=n.targets if isinstance(n,ast.Assign) else [n.target]
        if any(isinstance(t,ast.Name) and t.id=='VERSION' for t in ts):
            v=n.value
            if isinstance(v,ast.Constant) and isinstance(v.value,str): print(v.value); break
PY
)"
[[ "$gate_version" == "$EXPECTED_GATE_VERSION" ]] || die "Release gate version changed: ${gate_version:-unknown}; rerun read-only preflight first."
doctor_json="$(sudo "$GATE" doctor)" || die "release gate doctor failed"
python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("ok") is True else 1)' <<<"$doctor_json" || die "release gate doctor returned ok!=true"

log "Preparing the exact previously-tested candidate in a temporary checkout..."
repo="$TMP/repo"
GIT_TERMINAL_PROMPT=0 git clone --quiet --no-tags --single-branch --branch "$SOURCE_BRANCH" "https://github.com/${REPO}.git" "$repo"
remote_head="$(git -C "$repo" rev-parse HEAD)"
base_parent="$(git -C "$repo" rev-parse HEAD^ 2>/dev/null || true)"
payload_dir="$repo/minimal-ui-v1/health-recovery-v1/daily-stability/release-payload"
manifest="$repo/minimal-ui-v1/health-recovery-v1/daily-stability/release-published.json"

verify_release_files(){
  [[ -f "$manifest" ]] || return 1
  for name in sync.js app.js ai-home-v2.js index.html manual.html; do
    [[ -f "$payload_dir/$name" && "$(sha "$payload_dir/$name")" == "${AFTER[$name]}" ]] || return 1
  done
  [[ "$(sha "$manifest")" == "701f018e128e38e3eb71a2c72e548ceffed66b18ebb30696b1122f01590f747c" ]] || return 1
}

if [[ "$remote_head" == "$SOURCE_BASE" ]]; then
  cd "$repo"
  python3 minimal-ui-v1/health-recovery-v1/daily-stability/build.py
  python3 minimal-ui-v1/health-recovery-v1/daily-stability/build.py --check
  node --test minimal-ui-v1/health-recovery-v1/daily-stability/tests/*lifecycle.cjs >/dev/null
  python3 minimal-ui-v1/health-recovery-v1/daily-stability/tests/test_contract.py >/dev/null
  rm -rf "$payload_dir" && mkdir -p "$payload_dir"
  cp minimal-ui-v1/health-recovery-v1/daily-stability/dist/{sync.js,app.js,ai-home-v2.js,index.html,manual.html} "$payload_dir/"
  cat > "$manifest" <<'JSON'
{
  "schema": 1,
  "name": "20260914-daily-stability-1",
  "operations": [
    {"source":"minimal-ui-v1/health-recovery-v1/daily-stability/release-payload/sync.js","target":"/opt/dvizh/static/sync.js","http_path":"/sync.js"},
    {"source":"minimal-ui-v1/health-recovery-v1/daily-stability/release-payload/app.js","target":"/opt/dvizh/static/app.js","http_path":"/app.js"},
    {"source":"minimal-ui-v1/health-recovery-v1/daily-stability/release-payload/ai-home-v2.js","target":"/opt/dvizh/static/ai-home-v2.js","http_path":"/ai-home-v2.js"},
    {"source":"minimal-ui-v1/health-recovery-v1/daily-stability/release-payload/index.html","target":"/opt/dvizh/static/index.html","http_path":"/"},
    {"source":"minimal-ui-v1/health-recovery-v1/daily-stability/release-payload/manual.html","target":"/opt/dvizh/static/manual.html","http_path":"/manual.html"}
  ],
  "restarts": []
}
JSON
  verify_release_files || die "Local rebuilt payload does not match the exact tested hashes."
  git config user.name 'DVIZH Owner Release'
  git config user.email 'owner-release@dvizh.invalid'
  git add minimal-ui-v1/health-recovery-v1/daily-stability/release-payload minimal-ui-v1/health-recovery-v1/daily-stability/release-published.json
  git diff --cached --check
  git commit --quiet -m 'Publish exact DVIZH daily stability release payload'
  release_commit="$(git rev-parse HEAD)"
  log "Publishing only the new immutable payload commit to the existing ChatGPT candidate branch..."
  gh auth setup-git >/dev/null 2>&1 || die "Could not configure GitHub CLI credentials; production was not changed."
  GIT_TERMINAL_PROMPT=0 git push --quiet origin "HEAD:refs/heads/${SOURCE_BRANCH}" || die "GitHub push failed; production was not changed."
elif [[ "$base_parent" == "$SOURCE_BASE" ]] && verify_release_files; then
  release_commit="$remote_head"
  log "Exact release payload is already published at $release_commit; reusing it."
else
  die "Candidate branch moved to an unexpected commit ($remote_head); refusing to overwrite or force-push."
fi

log "Waiting for both required GitHub CI workflows on exact release commit $release_commit..."
deadline=$((SECONDS + 1200))
while (( SECONDS < deadline )); do
  gh api -H 'Accept: application/vnd.github+json' "repos/${REPO}/actions/runs?head_sha=${release_commit}&per_page=100" > "$TMP/runs.json"
  set +e
  python3 - "$TMP/runs.json" "$release_commit" <<'PY'
import json,pathlib,sys
d=json.loads(pathlib.Path(sys.argv[1]).read_text()); commit=sys.argv[2]
want={"DVIZH daily stability acceptance","DVIZH Health Recovery v1 acceptance"}
rows=[r for r in d.get('workflow_runs',[]) if r.get('name') in want and r.get('head_sha')==commit]
by={r.get('name'):r for r in rows}
if any(by.get(n,{}).get('conclusion') not in (None,'success') and by.get(n,{}).get('status')=='completed' for n in want): raise SystemExit(1)
if all(by.get(n,{}).get('status')=='completed' and by.get(n,{}).get('conclusion')=='success' for n in want): raise SystemExit(0)
raise SystemExit(2)
PY
  ci_rc=$?
  set -e
  [[ $ci_rc -eq 0 ]] && break
  [[ $ci_rc -eq 1 ]] && die "A required exact-head CI workflow failed; production was not changed."
  sleep 12
done
(( SECONDS < deadline )) || die "Timed out waiting for exact-head CI; production was not changed."
log "Both required exact-head CI workflows are green."

existing_alias="$(git -C "$repo" ls-remote --heads origin "refs/heads/${RELEASE_BRANCH}" | awk '{print $1}')"
if [[ -z "$existing_alias" ]]; then
  log "Creating owner release alias required by the installed gate contract..."
  gh auth setup-git >/dev/null 2>&1 || die "Could not configure GitHub CLI credentials."
  GIT_TERMINAL_PROMPT=0 git -C "$repo" push --quiet origin "${release_commit}:refs/heads/${RELEASE_BRANCH}" || die "Could not create owner release alias; production was not changed."
elif [[ "$existing_alias" != "$release_commit" ]]; then
  die "Owner release alias already points elsewhere ($existing_alias); refusing force update."
fi

manifest_blob="$(git -C "$repo" hash-object "$manifest")"
[[ "$manifest_blob" == "4eda150d29572603c67cabf93c0fc5e2f7561b0d" ]] || die "Manifest Git blob mismatch after publication."

STATE_DIR="$HOME/.hermes/dev/dvizh/state/autopilot"
mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"
PROPOSAL_ID="release-owner-daily-stability-${release_commit:0:10}"
PROPOSAL="$STATE_DIR/${PROPOSAL_ID}.json"
python3 - "$PROPOSAL" "$PROPOSAL_ID" "$RELEASE_BRANCH" "$release_commit" "$manifest_blob" <<'PY'
import datetime,json,os,pathlib,sys
path,pid,branch,commit,manifest_blob=sys.argv[1:]
d={"schema":1,"id":pid,"mode":"safe","repo":"Itosyro/voice-bot","branch":branch,"commit":commit,"manifest":"minimal-ui-v1/health-recovery-v1/daily-stability/release-published.json","manifest_blob":manifest_blob,"created_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
p=pathlib.Path(path); t=p.with_suffix('.tmp'); t.write_text(json.dumps(d,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8'); os.chmod(t,0o600); os.replace(t,p)
PY

log "Planning through the installed root-owned release gate (still no production write)..."
plan_json="$(sudo "$GATE" plan "$PROPOSAL")" || die "Release gate rejected the plan; nothing was installed."
printf '%s\n' "$plan_json" > "$TMP/plan.json"
mapfile -t f < <(python3 - "$TMP/plan.json" <<'PY'
import json,pathlib,sys
d=json.loads(pathlib.Path(sys.argv[1]).read_text())
print('1' if d.get('ok') is True else '0'); print('1' if d.get('approval_required') is True else '0'); print(d.get('risk') or ''); print(d.get('commit') or ''); print(d.get('approval_phrase') or ''); print(d.get('approval_token') or ''); print(len(d.get('operations')) if isinstance(d.get('operations'),list) else -1); print(len(d.get('restarts')) if isinstance(d.get('restarts'),list) else -1)
PY
)
[[ "${f[0]:-0}" == 1 && "${f[1]:-0}" == 1 && "${f[2]:-}" == approval && "${f[3]:-}" == "$release_commit" && "${f[6]:--1}" == 5 && "${f[7]:--1}" == 0 ]] || die "Unexpected gate plan; refusing apply."
approval_phrase="${f[4]:-}"; approval_token="${f[5]:-}"
[[ -n "$approval_phrase" && -n "$approval_token" ]] || die "Gate did not issue an exact approval challenge."

printf '\nВсе проверки зелёные. Изменятся только 5 файлов интерфейса DVIZH; сервисы не перезапускаются.\nВведи ТОЧНО эту фразу для подтверждения:\n\n  %s\n\n> ' "$approval_phrase" > /dev/tty
IFS= read -r entered </dev/tty
[[ "$entered" == "$approval_phrase" ]] || die "Approval phrase did not match; nothing was installed."

log "Applying exact approved release through dvizhrelease..."
apply_json="$(sudo "$GATE" apply "$PROPOSAL" --approval "$approval_token")" || die "Gate apply failed; its rollback contract owns restoration. Do not retry until the error is reviewed."
printf '%s\n' "$apply_json"
printf '%s\n' "$apply_json" > "$TMP/apply.json"
python3 - "$TMP/apply.json" <<'PY' || die "Gate did not report status=deployed."
import json,pathlib,sys
d=json.loads(pathlib.Path(sys.argv[1]).read_text()); raise SystemExit(0 if d.get('ok') is True and d.get('status')=='deployed' else 1)
PY
backup="$(python3 - "$TMP/apply.json" <<'PY'
import json,pathlib,sys
d=json.loads(pathlib.Path(sys.argv[1]).read_text()); print(d.get('backup') or d.get('backup_path') or '')
PY
)"
[[ -n "$backup" ]] || die "Deployment reported success but did not return a real backup path."

log "Verifying exact production bytes and preserved files..."
for name in "${!AFTER[@]}"; do
  p="$APP_ROOT/$name"
  [[ -f "$p" && ! -L "$p" && "$(stat -c '%h:%u:%g:%a' "$p")" == "1:0:0:644" ]] || die "Installed metadata mismatch: $name"
  [[ "$(sha "$p")" == "${AFTER[$name]}" ]] || die "Installed SHA mismatch: $name"
done
check_preserved || die "A protected static file changed unexpectedly."
for row in "sync.js:/sync.js" "app.js:/app.js" "ai-home-v2.js:/ai-home-v2.js" "index.html:/" "manual.html:/manual.html"; do
  name="${row%%:*}"; path="${row#*:}"; sep='?'; [[ "$path" == *\?* ]] && sep='&'
  curl -fsS --connect-timeout 5 --max-time 15 -H 'Cache-Control: no-cache' "${HTTP_BASE}${path}${sep}_dvizh_daily_release=$(date +%s%N)" -o "$TMP/http-$name"
  cmp -s "$payload_dir/$name" "$TMP/http-$name" || die "HTTP byte verification failed: $path"
done
health_ok || die "Application /api/health failed after deployment."
services_ok || die "A required service is inactive after deployment."

log "SUCCESS: DVIZH daily stability release is installed and verified."
log "Exact release commit: $release_commit"
log "Backup: $backup"
log "Changed only: sync.js, app.js, ai-home-v2.js, index.html, manual.html"
log "Preserved: styles.css, ai-home-v2.css, boot.js, sw.js; no service restart; no personal state read; no synthetic records."
