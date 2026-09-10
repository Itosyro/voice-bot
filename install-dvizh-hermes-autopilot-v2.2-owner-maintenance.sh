#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.10-dvizh-owner-maintenance-v2.2.1"
REPO="Itosyro/voice-bot"
PAYLOAD_REF="57a2975bcfc47583e1f87250aca8eccddcfc9ebc"
TARGET_USER="${DVIZH_OWNER_USER:-exedev}"

BASE_GATE_BLOB="b25a42654300f0e5595763a8b8753188039e34e3"
TARGET_GATE_BLOB="cf6ec6e4915739fe0b7d2c609b41b4eb7c27d844"
BASE_SKILL_BLOB="626a3c29cfd4f77f2612c92f2b4ff20780f473ce"
TARGET_SKILL_BLOB="3a68c550a328ec05a13ec86f1ad44aa4724c4fe1"

GATE="/usr/local/sbin/dvizhrelease"

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

if [[ -e "$SKILL" ]]; then
  [[ -f "$SKILL" && ! -L "$SKILL" ]] || fail "installed dvizh-dev skill is not a regular file"
  CURRENT_SKILL_BLOB="$(git_blob_sha1 "$SKILL")"
  case "$CURRENT_SKILL_BLOB" in
    "$BASE_SKILL_BLOB"|"$TARGET_SKILL_BLOB") ;;
    *) fail "installed dvizh-dev skill is not the known v2.1/v2.2 payload ($CURRENT_SKILL_BLOB)" ;;
  esac
else
  CURRENT_SKILL_BLOB="missing"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RAW="https://raw.githubusercontent.com/$REPO/$PAYLOAD_REF"

curl -fsSL "$RAW/hermes-dev-v2/dvizhrelease.py" -o "$TMP/dvizhrelease"
curl -fsSL "$RAW/hermes-dev-v2/skill/SKILL.md" -o "$TMP/SKILL.md"

[[ "$(git_blob_sha1 "$TMP/dvizhrelease")" == "$TARGET_GATE_BLOB" ]] || fail "downloaded gate failed immutable blob verification"
[[ "$(git_blob_sha1 "$TMP/SKILL.md")" == "$TARGET_SKILL_BLOB" ]] || fail "downloaded skill failed immutable blob verification"
python3 -m py_compile "$TMP/dvizhrelease"
grep -Fq 'VERSION = "2026.09.09-dvizh-release-gate.2.2"' "$TMP/dvizhrelease" || fail "unexpected gate version"
for marker in \
  'ai-integration-privileged' \
  '/usr/local/libexec/dvizh-context' \
  '/usr/local/libexec/dvizh-proposals' \
  '/opt/dvizh-ai-approval/proposal_bridge.py'
do
  grep -Fq "$marker" "$TMP/dvizhrelease" || fail "missing v2.2 marker: $marker"
done

if [[ "$CURRENT_GATE_BLOB" == "$TARGET_GATE_BLOB" && "$CURRENT_SKILL_BLOB" == "$TARGET_SKILL_BLOB" ]]; then
  echo "DVIZH Autopilot owner maintenance v2.2 is already installed byte-exact."
  sudo -u "$TARGET_USER" -H /usr/local/bin/dvizhautopilot doctor
  exit 0
fi

BACKUP="/var/lib/dvizh/backups/autopilot-owner-v2.2.$(date -u +%Y%m%d-%H%M%S).$(python3 - <<'PY'
import secrets
print(secrets.token_hex(4))
PY
)"
install -d -o root -g root -m 0700 "$BACKUP"
cp -a "$GATE" "$BACKUP/dvizhrelease"
if [[ -f "$SKILL" ]]; then
  cp -a "$SKILL" "$BACKUP/SKILL.md"
fi
printf '%s\n' "$CURRENT_GATE_BLOB" > "$BACKUP/gate.before.git-blob-sha1"
printf '%s\n' "$CURRENT_SKILL_BLOB" > "$BACKUP/skill.before.git-blob-sha1"
printf '%s\n' "$PAYLOAD_REF" > "$BACKUP/payload.commit"

APPLIED=0
rollback() {
  set +e
  echo "Rolling back owner-maintenance v2.2..." >&2
  cp -a "$BACKUP/dvizhrelease" "$GATE"
  if [[ -f "$BACKUP/SKILL.md" ]]; then
    install -d -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 0755 "$(dirname "$SKILL")"
    cp -a "$BACKUP/SKILL.md" "$SKILL"
  elif [[ "$CURRENT_SKILL_BLOB" == "missing" ]]; then
    rm -f "$SKILL"
  fi
  restored_gate="$(git_blob_sha1 "$GATE" 2>/dev/null)"
  restored_skill="missing"
  [[ -f "$SKILL" ]] && restored_skill="$(git_blob_sha1 "$SKILL" 2>/dev/null)"
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

install -d -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 0755 "$(dirname "$SKILL")"
SKILL_TMP="$(dirname "$SKILL")/.SKILL.md.v2.2.$$"
install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m 0644 "$TMP/SKILL.md" "$SKILL_TMP"
mv -f "$SKILL_TMP" "$SKILL"

[[ "$(git_blob_sha1 "$GATE")" == "$TARGET_GATE_BLOB" ]]
[[ "$(git_blob_sha1 "$SKILL")" == "$TARGET_SKILL_BLOB" ]]
[[ "$(stat -c '%U:%G %a' "$GATE")" == "root:root 755" ]]

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
echo "Services restarted: none"
echo "Friend project: untouched by this installer"
cat "$DOCTOR_OUT"
