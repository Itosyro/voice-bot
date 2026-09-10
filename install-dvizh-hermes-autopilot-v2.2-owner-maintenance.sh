#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.10-dvizh-owner-maintenance-v2.2.2-local-preserve"
REPO="Itosyro/voice-bot"
PAYLOAD_REF="57a2975bcfc47583e1f87250aca8eccddcfc9ebc"
TARGET_USER="${DVIZH_OWNER_USER:-exedev}"

BASE_GATE_BLOB="b25a42654300f0e5595763a8b8753188039e34e3"
TARGET_GATE_BLOB="cf6ec6e4915739fe0b7d2c609b41b4eb7c27d844"
BASE_SKILL_BLOB="626a3c29cfd4f77f2612c92f2b4ff20780f473ce"
TARGET_SKILL_BLOB="3a68c550a328ec05a13ec86f1ad44aa4724c4fe1"
# Exact locally installed skill observed by the owner on 2026-09-10.
# It contains valuable Manual/Quiet-Signal/owner-handoff guidance and must be preserved.
LOCAL_PRESERVE_SKILL_BLOB="082a6ce569a0c0c5bd34d00b8d1957a6d7bca233"

GATE="/usr/local/sbin/dvizhrelease"
V22_MARKER="## Owner-delivered v2.2 privileged contract"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

git_blob_sha1() {
  python3 - "$1" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = p.read_bytes()
h = hashlib.sha1()
h.update(f"blob {len(data)}\0".encode())
h.update(data)
print(h.hexdigest())
PY
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "run this installer with sudo/root"
command -v python3 >/dev/null || fail "python3 is required"
command -v curl >/dev/null || fail "curl is required"
id "$TARGET_USER" >/dev/null 2>&1 || fail "target user does not exist: $TARGET_USER"

TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || fail "cannot resolve home for $TARGET_USER"
SKILL="$TARGET_HOME/.hermes/skills/dvizh/dvizh-dev/SKILL.md"

[[ -f "$GATE" && ! -L "$GATE" ]] || fail "installed release gate is missing or is a symlink"
CURRENT_GATE_BLOB="$(git_blob_sha1 "$GATE")"
case "$CURRENT_GATE_BLOB" in
  "$BASE_GATE_BLOB"|"$TARGET_GATE_BLOB") ;;
  *) fail "installed dvizhrelease is not the known v2.1/v2.2 payload ($CURRENT_GATE_BLOB)" ;;
esac

[[ -f "$SKILL" && ! -L "$SKILL" ]] || fail "installed dvizh-dev skill is missing, not regular, or is a symlink"
CURRENT_SKILL_BLOB="$(git_blob_sha1 "$SKILL")"
SKILL_ALREADY_V22=0
if grep -Fq "$V22_MARKER" "$SKILL" \
  && grep -Fq '/usr/local/libexec/dvizh-context' "$SKILL" \
  && grep -Fq '/usr/local/libexec/dvizh-proposals' "$SKILL" \
  && grep -Fq '/opt/dvizh-ai-approval/proposal_bridge.py' "$SKILL" \
  && grep -Fq "--approval 'APPROVE <proposal-id> <token>'" "$SKILL"; then
  SKILL_ALREADY_V22=1
fi

case "$CURRENT_SKILL_BLOB" in
  "$BASE_SKILL_BLOB"|"$TARGET_SKILL_BLOB"|"$LOCAL_PRESERVE_SKILL_BLOB") ;;
  *)
    if [[ "$CURRENT_GATE_BLOB" == "$TARGET_GATE_BLOB" && "$SKILL_ALREADY_V22" == 1 ]]; then
      # Idempotent re-run after this local-preserving installer. The root gate remains
      # the security boundary; the user-owned skill is accepted only when every v2.2
      # instruction marker is still present.
      :
    else
      fail "installed dvizh-dev skill is not a recognized safe source for merge ($CURRENT_SKILL_BLOB)"
    fi
    ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RAW="https://raw.githubusercontent.com/$REPO/$PAYLOAD_REF"

curl -fsSL "$RAW/hermes-dev-v2/dvizhrelease.py" -o "$TMP/dvizhrelease"
curl -fsSL "$RAW/hermes-dev-v2/skill/SKILL.md" -o "$TMP/upstream-SKILL.md"

[[ "$(git_blob_sha1 "$TMP/dvizhrelease")" == "$TARGET_GATE_BLOB" ]] || fail "downloaded gate failed immutable blob verification"
[[ "$(git_blob_sha1 "$TMP/upstream-SKILL.md")" == "$TARGET_SKILL_BLOB" ]] || fail "downloaded upstream skill failed immutable blob verification"
python3 -m py_compile "$TMP/dvizhrelease"
grep -Fq 'VERSION = "2026.09.09-dvizh-release-gate.2.2"' "$TMP/dvizhrelease" || fail "unexpected gate version"
for marker in \
  'ai-integration-privileged' \
  '/usr/local/libexec/dvizh-context' \
  '/usr/local/libexec/dvizh-proposals' \
  '/opt/dvizh-ai-approval/proposal_bridge.py'
do
  grep -Fq "$marker" "$TMP/dvizhrelease" || fail "missing v2.2 gate marker: $marker"
done

cat > "$TMP/v22-overlay.md" <<'EOF'

## Owner-delivered v2.2 privileged contract

The installed root release gate supports the separate `ai-integration-privileged`
class for exactly three DVIZH runtime targets. This remains owner-maintenance
control-plane; managed jobs must never edit or push Autopilot's own gate, skill,
installer, sudoers, deploy key, or gate workflows.

For this class every manifest operation must use the exact committed source and
production destination below and must include `sha256`,
`release_class: "ai-integration-privileged"`, `required_owner: "root:root"`,
`required_mode: "0755"`, and the fixed verification value shown here:

- `hermes-control-v1/dvizh_context.py` -> `/usr/local/libexec/dvizh-context` with `verification: "python-syntax"`.
- `hermes-control-v1/dvizh_proposals.py` -> `/usr/local/libexec/dvizh-proposals` with `verification: "python-syntax"`.
- `hermes-control-v1/dvizh_proposal_bridge.py` -> `/opt/dvizh-ai-approval/proposal_bridge.py` with `verification: "python-syntax-service"`.

No wildcard under `/usr/local` or `/opt/dvizh-ai-approval` is allowed. Privileged
operations may not be mixed with ordinary v2.1 operations. The bridge update is
the only one of these three that may require a restart; when updated it must declare
exactly `restarts: ["dvizh-ai-approval.service"]` plus a non-empty `restart_reason`.
The two libexec helpers require no restart.

`ai-integration-privileged` is ALWAYS approval-required, including in auto mode.
After `release-plan` returns `APPROVE <proposal-id> <token>`, stop and wait for a
later authenticated owner Telegram message containing that exact phrase. Seeing the
challenge or the original development request is not approval. For this class pass
the ENTIRE exact later phrase as the single argument:

```bash
dvizhautopilot release-apply <proposal-path> --approval 'APPROVE <proposal-id> <token>'
```

A bare token is invalid for this class. Approval is one-time, digest-bound and
expires after 1800 seconds. Never manufacture, infer, replay or self-approve it.
The root gate independently rechecks immutable source bytes, CI, destination
metadata, backup, health, atomic writes and rollback. A pending interrupted
transaction fails closed and requires separate owner recovery; do not bypass it.
EOF

# Build the skill update append-only. Existing local guidance must remain byte-for-byte
# as the prefix. If v2.2 is already present, keep the file byte-identical.
python3 - "$SKILL" "$TMP/v22-overlay.md" "$TMP/merged-SKILL.md" <<'PY'
from pathlib import Path
import sys
src = Path(sys.argv[1]).read_bytes()
overlay = Path(sys.argv[2]).read_bytes()
marker = b"## Owner-delivered v2.2 privileged contract"
if marker in src:
    out = src
else:
    sep = b"" if src.endswith(b"\n") else b"\n"
    out = src + sep + overlay
Path(sys.argv[3]).write_bytes(out)
if not out.startswith(src):
    raise SystemExit("merge did not preserve installed skill as exact prefix")
PY

for marker in \
  '## Owner-delivered v2.2 privileged contract' \
  '/usr/local/libexec/dvizh-context' \
  '/usr/local/libexec/dvizh-proposals' \
  '/opt/dvizh-ai-approval/proposal_bridge.py' \
  "--approval 'APPROVE <proposal-id> <token>'"
do
  grep -Fq "$marker" "$TMP/merged-SKILL.md" || fail "merged skill missing v2.2 marker: $marker"
done

if [[ "$CURRENT_GATE_BLOB" == "$TARGET_GATE_BLOB" ]]; then
  python3 - "$SKILL" "$TMP/merged-SKILL.md" <<'PY'
from pathlib import Path
import sys
if Path(sys.argv[1]).read_bytes() != Path(sys.argv[2]).read_bytes():
    raise SystemExit(1)
PY
  if [[ $? -eq 0 ]]; then
    echo "DVIZH Autopilot v2.2 gate and local-preserved skill overlay are already installed."
    sudo -u "$TARGET_USER" -H /usr/local/bin/dvizhautopilot doctor
    exit 0
  fi
fi

BACKUP="/var/lib/dvizh/backups/autopilot-owner-v2.2-local-preserve.$(date -u +%Y%m%d-%H%M%S).$(python3 - <<'PY'
import secrets
print(secrets.token_hex(4))
PY
)"
install -d -o root -g root -m 0700 "$BACKUP"
cp -a "$GATE" "$BACKUP/dvizhrelease"
cp -a "$SKILL" "$BACKUP/SKILL.md"
printf '%s\n' "$CURRENT_GATE_BLOB" > "$BACKUP/gate.before.git-blob-sha1"
printf '%s\n' "$CURRENT_SKILL_BLOB" > "$BACKUP/skill.before.git-blob-sha1"
printf '%s\n' "$PAYLOAD_REF" > "$BACKUP/payload.commit"

APPLIED=0
rollback() {
  set +e
  echo "Rolling back owner-maintenance v2.2 local-preserve..." >&2
  cp -a "$BACKUP/dvizhrelease" "$GATE"
  cp -a "$BACKUP/SKILL.md" "$SKILL"
  restored_gate="$(git_blob_sha1 "$GATE" 2>/dev/null)"
  restored_skill="$(git_blob_sha1 "$SKILL" 2>/dev/null)"
  if [[ "$restored_gate" != "$CURRENT_GATE_BLOB" || "$restored_skill" != "$CURRENT_SKILL_BLOB" ]]; then
    echo "CRITICAL: rollback verification failed. Backup: $BACKUP" >&2
    return 1
  fi
  echo "Rollback verified. Backup: $BACKUP" >&2
  return 0
}

on_error() {
  rc=$?
  if [[ "$APPLIED" == 1 ]]; then
    rollback || true
  fi
  exit "$rc"
}
trap on_error ERR

GATE_TMP="$(dirname "$GATE")/.dvizhrelease.v2.2.$$"
install -o root -g root -m 0755 "$TMP/dvizhrelease" "$GATE_TMP"
mv -f "$GATE_TMP" "$GATE"
APPLIED=1

# Preserve the skill's existing owner/group/mode while replacing it atomically.
SKILL_UID="$(stat -c '%u' "$SKILL")"
SKILL_GID="$(stat -c '%g' "$SKILL")"
SKILL_MODE="$(stat -c '%a' "$SKILL")"
SKILL_TMP="$(dirname "$SKILL")/.SKILL.md.v2.2-preserve.$$"
install -o "$SKILL_UID" -g "$SKILL_GID" -m "$SKILL_MODE" "$TMP/merged-SKILL.md" "$SKILL_TMP"
mv -f "$SKILL_TMP" "$SKILL"

[[ "$(git_blob_sha1 "$GATE")" == "$TARGET_GATE_BLOB" ]]
[[ "$(stat -c '%U:%G %a' "$GATE")" == "root:root 755" ]]

# Strong preservation proof: the installed file must begin with the exact pre-update
# bytes from backup, so every local Manual/Quiet-Signal instruction survives.
python3 - "$BACKUP/SKILL.md" "$SKILL" <<'PY'
from pathlib import Path
import sys
old = Path(sys.argv[1]).read_bytes()
new = Path(sys.argv[2]).read_bytes()
if not new.startswith(old):
    raise SystemExit("local skill content was not preserved byte-for-byte")
PY
for marker in \
  '## Owner-delivered v2.2 privileged contract' \
  '/usr/local/libexec/dvizh-context' \
  '/usr/local/libexec/dvizh-proposals' \
  '/opt/dvizh-ai-approval/proposal_bridge.py' \
  "--approval 'APPROVE <proposal-id> <token>'"
do
  grep -Fq "$marker" "$SKILL"
done

DOCTOR_OUT="$TMP/doctor.json"
sudo -u "$TARGET_USER" -H /usr/local/bin/dvizhautopilot doctor > "$DOCTOR_OUT"
grep -Fq '2026.09.09-dvizh-release-gate.2.2' "$DOCTOR_OUT"
grep -Fq '"private_git_key_visible_to_hermes": false' "$DOCTOR_OUT"
grep -Fq '"authorized": true' "$DOCTOR_OUT"

APPLIED=0
trap - ERR

echo "Installed: $VERSION"
echo "Payload commit: $PAYLOAD_REF"
echo "Backup: $BACKUP"
echo "Skill policy: local content preserved byte-for-byte; v2.2 overlay appended only if missing"
echo "Services restarted: none"
echo "Friend project: untouched by this installer"
cat "$DOCTOR_OUT"
