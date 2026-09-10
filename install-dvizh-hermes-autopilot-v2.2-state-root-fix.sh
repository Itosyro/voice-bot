#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.10-dvizh-owner-v2.2-state-root-fix.1"
REPO="Itosyro/voice-bot"
PAYLOAD_REF="57a2975bcfc47583e1f87250aca8eccddcfc9ebc"
SOURCE_GATE_BLOB="cf6ec6e4915739fe0b7d2c609b41b4eb7c27d844"
SOURCE_VERSION='VERSION = "2026.09.09-dvizh-release-gate.2.2"'
TARGET_VERSION='VERSION = "2026.09.10-dvizh-release-gate.2.2.1-state-root"'
OLD_BACKUP='/var/lib/dvizh/backups'
OLD_APPROVAL='/var/lib/dvizh/autopilot-approvals'
NEW_ROOT='/var/lib/dvizh-release-gate'
NEW_BACKUP='/var/lib/dvizh-release-gate/backups'
NEW_APPROVAL='/var/lib/dvizh-release-gate/approvals'
GATE='/usr/local/sbin/dvizhrelease'
TARGET_USER="${DVIZH_OWNER_USER:-exedev}"

fail(){ printf 'ERROR: %s\n' "$*" >&2; exit 1; }

git_blob_sha1(){
  python3 - "$1" <<'PY'
import hashlib,pathlib,sys
p=pathlib.Path(sys.argv[1]); d=p.read_bytes()
h=hashlib.sha1(); h.update(f"blob {len(d)}\0".encode()); h.update(d)
print(h.hexdigest())
PY
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "run with sudo/root"
command -v python3 >/dev/null || fail "python3 required"
command -v curl >/dev/null || fail "curl required"
id "$TARGET_USER" >/dev/null 2>&1 || fail "target user missing: $TARGET_USER"
[[ -f "$GATE" && ! -L "$GATE" ]] || fail "installed gate missing or symlink"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
RAW="https://raw.githubusercontent.com/$REPO/$PAYLOAD_REF"
curl -fsSL "$RAW/hermes-dev-v2/dvizhrelease.py" -o "$TMP/source.py"
[[ "$(git_blob_sha1 "$TMP/source.py")" == "$SOURCE_GATE_BLOB" ]] || fail "immutable source gate mismatch"

python3 - "$TMP/source.py" "$TMP/target.py" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text(encoding='utf-8')
repls={
'VERSION = "2026.09.09-dvizh-release-gate.2.2"':'VERSION = "2026.09.10-dvizh-release-gate.2.2.1-state-root"',
'BACKUP_ROOT = Path(os.environ.get("DVIZH_RELEASE_BACKUP_ROOT", "/var/lib/dvizh/backups"))':'BACKUP_ROOT = Path(os.environ.get("DVIZH_RELEASE_BACKUP_ROOT", "/var/lib/dvizh-release-gate/backups"))',
'APPROVAL_ROOT = Path(os.environ.get("DVIZH_RELEASE_APPROVAL_ROOT", "/var/lib/dvizh/autopilot-approvals"))':'APPROVAL_ROOT = Path(os.environ.get("DVIZH_RELEASE_APPROVAL_ROOT", "/var/lib/dvizh-release-gate/approvals"))',
'BACKUP_ROOT != Path("/var/lib/dvizh/backups")':'BACKUP_ROOT != Path("/var/lib/dvizh-release-gate/backups")',
'APPROVAL_ROOT != Path("/var/lib/dvizh/autopilot-approvals")':'APPROVAL_ROOT != Path("/var/lib/dvizh-release-gate/approvals")',
}
for old,new in repls.items():
    n=src.count(old)
    if n != 1:
        raise SystemExit(f"expected exactly one match for {old!r}, got {n}")
    src=src.replace(old,new)
Path(sys.argv[2]).write_text(src,encoding='utf-8')
PY
python3 -m py_compile "$TMP/target.py"
grep -Fq "$TARGET_VERSION" "$TMP/target.py"
grep -Fq "$NEW_BACKUP" "$TMP/target.py"
grep -Fq "$NEW_APPROVAL" "$TMP/target.py"
TARGET_BLOB="$(git_blob_sha1 "$TMP/target.py")"
CURRENT_BLOB="$(git_blob_sha1 "$GATE")"

case "$CURRENT_BLOB" in
  "$SOURCE_GATE_BLOB"|"$TARGET_BLOB") ;;
  *) fail "installed gate is neither exact v2.2 nor this state-root fix ($CURRENT_BLOB)" ;;
esac

# Root-owned sibling; never chown/chmod /var/lib/dvizh itself.
install -d -o root -g root -m 0700 "$NEW_ROOT"
install -d -o root -g root -m 0700 "$NEW_BACKUP" "$NEW_APPROVAL"
[[ "$(stat -c '%U:%G %a' "$NEW_ROOT")" == "root:root 700" ]] || fail "unsafe state root metadata"
[[ "$(stat -c '%U:%G %a' "$NEW_BACKUP")" == "root:root 700" ]] || fail "unsafe backup root metadata"
[[ "$(stat -c '%U:%G %a' "$NEW_APPROVAL")" == "root:root 700" ]] || fail "unsafe approval root metadata"

if [[ "$CURRENT_BLOB" == "$TARGET_BLOB" ]]; then
  echo "State-root fix already installed byte-exact."
  sudo -u "$TARGET_USER" -H /usr/local/bin/dvizhautopilot doctor
  exit 0
fi

BACKUP="$NEW_BACKUP/owner-state-root-fix.$(date -u +%Y%m%d-%H%M%S).$(python3 - <<'PY'
import secrets; print(secrets.token_hex(4))
PY
)"
install -d -o root -g root -m 0700 "$BACKUP"
cp -a "$GATE" "$BACKUP/dvizhrelease.before"
printf '%s\n' "$CURRENT_BLOB" > "$BACKUP/before.git-blob-sha1"
printf '%s\n' "$TARGET_BLOB" > "$BACKUP/target.git-blob-sha1"
printf '%s\n' "$PAYLOAD_REF" > "$BACKUP/source.commit"

APPLIED=0
rollback(){
  set +e
  cp -a "$BACKUP/dvizhrelease.before" "$GATE"
  restored="$(git_blob_sha1 "$GATE" 2>/dev/null)"
  if [[ "$restored" != "$CURRENT_BLOB" ]]; then
    echo "CRITICAL: rollback verification failed; backup=$BACKUP" >&2
    return 1
  fi
  echo "Rollback verified; backup=$BACKUP" >&2
}
on_error(){ rc=$?; [[ "$APPLIED" == 1 ]] && rollback || true; exit "$rc"; }
trap on_error ERR

GTMP="$(dirname "$GATE")/.dvizhrelease.state-root.$$"
install -o root -g root -m 0755 "$TMP/target.py" "$GTMP"
mv -f "$GTMP" "$GATE"
APPLIED=1
[[ "$(git_blob_sha1 "$GATE")" == "$TARGET_BLOB" ]]
[[ "$(stat -c '%U:%G %a' "$GATE")" == "root:root 755" ]]

DOCTOR="$TMP/doctor.json"
sudo -u "$TARGET_USER" -H /usr/local/bin/dvizhautopilot doctor > "$DOCTOR"
grep -Fq '2026.09.10-dvizh-release-gate.2.2.1-state-root' "$DOCTOR"
grep -Fq '"ok": true' "$DOCTOR"
grep -Fq '"private_git_key_visible_to_hermes": false' "$DOCTOR"

APPLIED=0; trap - ERR
printf 'Installed: %s\n' "$VERSION"
printf 'Gate version: 2026.09.10-dvizh-release-gate.2.2.1-state-root\n'
printf 'Control state: %s\n' "$NEW_ROOT"
printf 'Backup: %s\n' "$BACKUP"
printf 'Application state /var/lib/dvizh: unchanged\n'
printf 'Services restarted: none\n'
printf 'Friend project: untouched\n'
cat "$DOCTOR"
