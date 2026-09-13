#!/usr/bin/env bash
set -Eeuo pipefail

REPO="Itosyro/voice-bot"
CANDIDATE_BRANCH="hermes/dev/20260909-115201-e37585-health-and-recovery-v1-architecture"
CANDIDATE_COMMIT="9d492693de2c7cf66350293afcf42b74edeebaef"
MANIFEST_REL="minimal-ui-v1/health-recovery-v1/manifests/health-recovery-ai-home.json"
MANIFEST_BLOB="22f58974dd00a99b7978ea565616abe312b4946e"
SOURCE_REL="ai-home-v2/ai_home_bridge.py"
SOURCE_BLOB="efec756cfceb2f2754775c901d7080ce2db3182d"
OLD_SOURCE_BLOB="bddfacd6956c02f492b2897d0c4ccede67e3c3ee"
TARGET="/opt/dvizh-ai-home/ai_home_bridge.py"
SERVICE="dvizh-ai-home.service"
GATE="/usr/local/sbin/dvizhrelease"
HEALTH_CI_RUN="34486484252"
GATE_CI_RUN="34486484258"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/${CANDIDATE_COMMIT}"
API_BASE="https://api.github.com/repos/${REPO}"

log() { printf '[DVIZH] %s\n' "$*"; }
die() { printf '[DVIZH] ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"; }

need curl
need python3
need sudo
need cmp
need systemctl

if [[ ${EUID} -eq 0 ]]; then
  die "Run this installer as the normal DVIZH server user, not through 'sudo bash'. The script will request sudo only for the protected release gate."
fi

[[ -x "$GATE" ]] || die "release gate not installed at $GATE"
[[ -r /dev/tty && -w /dev/tty ]] || die "interactive terminal /dev/tty is required for owner approval"

umask 077
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

manifest="$TMP/manifest.json"
source_file="$TMP/ai_home_bridge.py"

log "Checking exact GitHub candidate..."
encoded_branch="$(python3 - "$CANDIDATE_BRANCH" <<'PY'
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
)"
remote_sha="$(curl -fsSL --retry 3 --connect-timeout 10 "${API_BASE}/branches/${encoded_branch}" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("commit") or {}).get("sha") or "")')"
[[ "$remote_sha" == "$CANDIDATE_COMMIT" ]] || die "candidate branch HEAD changed: expected $CANDIDATE_COMMIT, got ${remote_sha:-<empty>}"

check_run() {
  local run_id="$1"
  local payload head conclusion
  payload="$(curl -fsSL --retry 3 --connect-timeout 10 "${API_BASE}/actions/runs/${run_id}")"
  head="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("head_sha") or "")' <<<"$payload")"
  conclusion="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("conclusion") or "")' <<<"$payload")"
  [[ "$head" == "$CANDIDATE_COMMIT" ]] || die "CI run ${run_id} belongs to unexpected head ${head:-<empty>}"
  [[ "$conclusion" == "success" ]] || die "CI run ${run_id} is not successful: ${conclusion:-<empty>}"
}
check_run "$HEALTH_CI_RUN"
check_run "$GATE_CI_RUN"

log "Checking immutable manifest and payload..."
curl -fsSL --retry 3 --connect-timeout 10 "${RAW_BASE}/${MANIFEST_REL}" -o "$manifest"
curl -fsSL --retry 3 --connect-timeout 10 "${RAW_BASE}/${SOURCE_REL}" -o "$source_file"

git_blob() {
  python3 - "$1" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = p.read_bytes()
print(hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest())
PY
}

[[ "$(git_blob "$manifest")" == "$MANIFEST_BLOB" ]] || die "manifest blob mismatch"
[[ "$(git_blob "$source_file")" == "$SOURCE_BLOB" ]] || die "AI Home payload blob mismatch"

python3 - "$manifest" "$SOURCE_REL" "$TARGET" "$SERVICE" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
source, target, service = sys.argv[2:]
d = json.loads(p.read_text(encoding="utf-8"))
ops = d.get("operations")
if d.get("schema") != 1 or not isinstance(ops, list) or len(ops) != 1:
    raise SystemExit("unexpected release manifest shape")
op = ops[0]
if op.get("source") != source or op.get("target") != target:
    raise SystemExit("unexpected release manifest operation")
if d.get("restarts") != [service]:
    raise SystemExit("unexpected release manifest restart set")
PY

if [[ ! -f "$TARGET" || -L "$TARGET" ]]; then
  die "live AI Home bridge is missing or not a regular file: $TARGET"
fi
live_blob="$(git_blob "$TARGET")"
if [[ "$live_blob" == "$SOURCE_BLOB" ]]; then
  log "AI Home health bridge is already installed; verifying service and health only."
  systemctl is-active --quiet "$SERVICE" || die "$SERVICE is not active"
  curl -fsS --connect-timeout 5 --max-time 15 -H 'Cache-Control: no-cache' http://127.0.0.1:8000/api/ai-home/health >/dev/null || die "read-only /api/ai-home/health check failed"
  log "OK: exact bridge is already live and health check passes."
  exit 0
fi
[[ "$live_blob" == "$OLD_SOURCE_BLOB" ]] || die "live AI Home bridge has unexpected bytes; refusing to overwrite (blob $live_blob)"

log "Checking installed release gate..."
doctor_json="$(sudo "$GATE" doctor)"
python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("ok") is True else 1)' <<<"$doctor_json" || die "release gate doctor is not OK"

STATE_DIR="$HOME/.hermes/dev/dvizh/state/autopilot"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
PROPOSAL_ID="release-chatgpt-health-ai-home-${CANDIDATE_COMMIT:0:10}"
PROPOSAL="$STATE_DIR/${PROPOSAL_ID}.json"

python3 - "$PROPOSAL" "$PROPOSAL_ID" "$CANDIDATE_BRANCH" "$CANDIDATE_COMMIT" "$MANIFEST_REL" "$MANIFEST_BLOB" <<'PY'
import datetime, json, os, pathlib, sys
path, proposal_id, branch, commit, manifest, manifest_blob = sys.argv[1:]
payload = {
    "schema": 1,
    "id": proposal_id,
    "job_id": "chatgpt-dvizh-health-ai-home-finalize-20260913",
    "mode": "safe",
    "repo": "Itosyro/voice-bot",
    "branch": branch,
    "commit": commit,
    "manifest": manifest,
    "manifest_blob": manifest_blob,
    "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
p = pathlib.Path(path)
tmp = p.with_suffix(".tmp")
tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
os.replace(tmp, p)
PY

log "Planning protected release..."
plan_json="$(sudo "$GATE" plan "$PROPOSAL")"
printf '%s\n' "$plan_json"

readarray -t approval_fields < <(python3 -c 'import json,sys; d=json.load(sys.stdin); print("1" if d.get("ok") is True else "0"); print("1" if d.get("approval_required") is True else "0"); print(d.get("approval_phrase") or ""); print(d.get("approval_token") or "")' <<<"$plan_json")
[[ "${approval_fields[0]:-0}" == "1" ]] || die "release plan was rejected"
approval_required="${approval_fields[1]:-0}"
approval_phrase="${approval_fields[2]:-}"
approval_token="${approval_fields[3]:-}"

if [[ "$approval_required" == "1" ]]; then
  [[ -n "$approval_phrase" && -n "$approval_token" ]] || die "gate requires approval but did not provide the expected approval challenge"
  printf '\nЗащищённая установка готова. Чтобы подтвердить ИМЕННО этот release, введи фразу ниже:\n\n  %s\n\n> ' "$approval_phrase" > /dev/tty
  IFS= read -r entered </dev/tty
  [[ "$entered" == "$approval_phrase" ]] || die "approval phrase did not match; nothing was installed"
  log "Applying exact approved release..."
  apply_json="$(sudo "$GATE" apply "$PROPOSAL" --approval "$approval_token")"
else
  log "Gate reports that no additional approval is required; applying exact planned release..."
  apply_json="$(sudo "$GATE" apply "$PROPOSAL")"
fi
printf '%s\n' "$apply_json"
python3 -c 'import json,sys; d=json.load(sys.stdin); raise SystemExit(0 if d.get("ok") is True else 1)' <<<"$apply_json" || die "release gate apply did not return ok=true"

log "Verifying installed bytes and read-only health..."
cmp -s "$source_file" "$TARGET" || die "installed AI Home bridge does not match immutable candidate bytes"
grep -Fq 'Здоровье и восстановление v1:' "$TARGET" || die "health/recovery prompt marker missing after install"
systemctl is-active --quiet "$SERVICE" || die "$SERVICE is not active after release"
curl -fsS --connect-timeout 5 --max-time 15 -H 'Cache-Control: no-cache' http://127.0.0.1:8000/api/ai-home/health >/dev/null || die "read-only /api/ai-home/health check failed after release"

log "SUCCESS: Health/Recovery bridge is live in AI Home."
log "Candidate: $CANDIDATE_COMMIT"
log "No real user data or proposal was created by this verification."
