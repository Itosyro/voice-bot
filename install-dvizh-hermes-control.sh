#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-hermes-control.4"
PAYLOAD_REF="8ad08d5ba1465690344fc549d0b726cf1f1e476d"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-control-v1"
TMP_DIR="$(mktemp -d /tmp/dvizh-hermes-control.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizhctl" -o "$TMP_DIR/dvizhctl"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizh_context.py" -o "$TMP_DIR/dvizh-context"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizh_proposals.py" -o "$TMP_DIR/dvizh-proposals"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/skill/SKILL.md" -o "$TMP_DIR/SKILL.md"

bash -n "$TMP_DIR/dvizhctl"
python3 -m py_compile "$TMP_DIR/dvizh-context" "$TMP_DIR/dvizh-proposals"
grep -q 'VERSION="2026.09.05-hermes-control.4"' "$TMP_DIR/dvizhctl"
grep -q 'VERSION = "2026.09.05-hermes-context.1"' "$TMP_DIR/dvizh-context"
grep -q 'VERSION = "2026.09.05-hermes-proposals.1"' "$TMP_DIR/dvizh-proposals"
grep -q '^name: dvizh-server$' "$TMP_DIR/SKILL.md"
grep -q 'dvizhctl context today' "$TMP_DIR/SKILL.md"
grep -q 'dvizhctl propose' "$TMP_DIR/SKILL.md"
grep -q 'Proposals must be approved inside DVIZH UI' "$TMP_DIR/dvizhctl"

if [[ "${DVIZH_HERMES_CONTROL_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "DVIZH Hermes control payload verified from $PAYLOAD_REF."
  exit 0
fi

if [[ "$(id -u)" -eq 0 ]]; then
  TARGET_USER="${SUDO_USER:-exedev}"
else
  TARGET_USER="$(id -un)"
fi
[[ "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Unexpected target user" >&2; exit 1; }
id "$TARGET_USER" >/dev/null 2>&1 || { echo "Target user not found: $TARGET_USER" >&2; exit 1; }
id dvizh >/dev/null 2>&1 || { echo "Required service user 'dvizh' not found" >&2; exit 1; }
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || { echo "Cannot resolve home for $TARGET_USER" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$TARGET_HOME/.hermes/backups/dvizh-control-$STAMP"
SKILL_DIR="$TARGET_HOME/.hermes/skills/dvizh/dvizh-server"
CONTEXT_PATH="/usr/local/libexec/dvizh-context"
PROPOSAL_PATH="/usr/local/libexec/dvizh-proposals"
PROPOSAL_DIR="/var/lib/dvizh/hermes-proposals"
SUDOERS_PATH="/etc/sudoers.d/dvizh-hermes-context"
HAD_CTL=0
HAD_CONTEXT=0
HAD_PROPOSAL=0
HAD_SKILL=0
HAD_SUDOERS=0
INSTALLED=0

root_run() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

mkdir_as_user() {
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then mkdir -p "$1"; else sudo -n -u "$TARGET_USER" mkdir -p "$1"; fi
}

copy_as_user() {
  local src="$1" dst="$2"
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then cp "$src" "$dst"; else sudo -n -u "$TARGET_USER" cp "$src" "$dst"; fi
}

remove_as_user() {
  local path="$1"
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then rm -rf "$path"; else sudo -n -u "$TARGET_USER" rm -rf "$path"; fi
}

backup_root_file_for_user() {
  local src="$1" dst="$2" mode="${3:-0600}"
  root_run cp "$src" "$dst"
  root_run chown "$TARGET_USER:$TARGET_GROUP" "$dst"
  root_run chmod "$mode" "$dst"
}

rollback() {
  local rc=$?
  if [[ "$INSTALLED" == "1" ]]; then
    echo "Ошибка. Возвращаю предыдущий Hermes control layer..." >&2
    if [[ "$HAD_CTL" == "1" && -f "$BACKUP_DIR/dvizhctl" ]]; then root_run install -o root -g root -m 0755 "$BACKUP_DIR/dvizhctl" /usr/local/bin/dvizhctl || true; else root_run rm -f /usr/local/bin/dvizhctl || true; fi
    if [[ "$HAD_CONTEXT" == "1" && -f "$BACKUP_DIR/dvizh-context" ]]; then root_run install -o root -g root -m 0755 "$BACKUP_DIR/dvizh-context" "$CONTEXT_PATH" || true; else root_run rm -f "$CONTEXT_PATH" || true; fi
    if [[ "$HAD_PROPOSAL" == "1" && -f "$BACKUP_DIR/dvizh-proposals" ]]; then root_run install -o root -g root -m 0755 "$BACKUP_DIR/dvizh-proposals" "$PROPOSAL_PATH" || true; else root_run rm -f "$PROPOSAL_PATH" || true; fi
    if [[ "$HAD_SUDOERS" == "1" && -f "$BACKUP_DIR/sudoers" ]]; then root_run install -o root -g root -m 0440 "$BACKUP_DIR/sudoers" "$SUDOERS_PATH" || true; else root_run rm -f "$SUDOERS_PATH" || true; fi
    if [[ "$HAD_SKILL" == "1" && -f "$BACKUP_DIR/SKILL.md" ]]; then mkdir_as_user "$SKILL_DIR" || true; copy_as_user "$BACKUP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md" || true; else remove_as_user "$SKILL_DIR" || true; fi
  fi
  exit "$rc"
}
trap rollback ERR INT TERM

mkdir_as_user "$BACKUP_DIR"
mkdir_as_user "$SKILL_DIR"

if [[ -f /usr/local/bin/dvizhctl ]]; then HAD_CTL=1; root_run cp /usr/local/bin/dvizhctl "$TMP_DIR/dvizhctl.previous"; copy_as_user "$TMP_DIR/dvizhctl.previous" "$BACKUP_DIR/dvizhctl"; fi
if [[ -f "$CONTEXT_PATH" ]]; then HAD_CONTEXT=1; root_run cp "$CONTEXT_PATH" "$TMP_DIR/dvizh-context.previous"; copy_as_user "$TMP_DIR/dvizh-context.previous" "$BACKUP_DIR/dvizh-context"; fi
if [[ -f "$PROPOSAL_PATH" ]]; then HAD_PROPOSAL=1; root_run cp "$PROPOSAL_PATH" "$TMP_DIR/dvizh-proposals.previous"; copy_as_user "$TMP_DIR/dvizh-proposals.previous" "$BACKUP_DIR/dvizh-proposals"; fi
if [[ -f "$SUDOERS_PATH" ]]; then HAD_SUDOERS=1; backup_root_file_for_user "$SUDOERS_PATH" "$BACKUP_DIR/sudoers" 0600; fi
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then HAD_SKILL=1; cp "$SKILL_DIR/SKILL.md" "$TMP_DIR/SKILL.previous.md"; copy_as_user "$TMP_DIR/SKILL.previous.md" "$BACKUP_DIR/SKILL.md"; fi

cat > "$TMP_DIR/sudoers" <<EOF
# Read-only DVIZH context exporter for Hermes. The helper accepts only fixed view names.
$TARGET_USER ALL=(dvizh) NOPASSWD: $CONTEXT_PATH *
EOF
chmod 0440 "$TMP_DIR/sudoers"
if command -v visudo >/dev/null 2>&1; then root_run visudo -cf "$TMP_DIR/sudoers" >/dev/null; fi

INSTALLED=1
root_run install -d -o root -g root -m 0755 /usr/local/libexec
root_run install -o root -g root -m 0755 "$TMP_DIR/dvizhctl" /usr/local/bin/dvizhctl
root_run install -o root -g root -m 0755 "$TMP_DIR/dvizh-context" "$CONTEXT_PATH"
root_run install -o root -g root -m 0755 "$TMP_DIR/dvizh-proposals" "$PROPOSAL_PATH"
root_run install -o root -g root -m 0440 "$TMP_DIR/sudoers" "$SUDOERS_PATH"
# Proposal queue is deliberately separate from production DBs. Hermes can stage proposals;
# the dvizh service account can later expose/resolve them in authenticated UI.
root_run install -d -o "$TARGET_USER" -g dvizh -m 2770 "$PROPOSAL_DIR"
copy_as_user "$TMP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
if [[ "$(id -un)" == "$TARGET_USER" ]]; then chmod 0600 "$SKILL_DIR/SKILL.md"; else sudo -n -u "$TARGET_USER" chmod 0600 "$SKILL_DIR/SKILL.md"; fi

printf '[1/5] Installed dvizhctl\n'
[[ "$(/usr/local/bin/dvizhctl version)" == "$VERSION" ]]
/usr/local/bin/dvizhctl version
printf '[2/5] Installed sanitized read-only context helper\n'
[[ -x "$CONTEXT_PATH" ]]
printf '[3/5] Installed inert proposal queue helper\n'
[[ -x "$PROPOSAL_PATH" ]]
printf '[4/5] Installed Hermes skill: %s\n' "$SKILL_DIR/SKILL.md"
printf '[5/5] Running safe smoke checks...\n'
/usr/local/bin/dvizhctl status || true
/usr/local/bin/dvizhctl context health >/dev/null
/usr/local/bin/dvizhctl proposals pending >/dev/null

INSTALLED=0
trap - ERR INT TERM

cat <<EOF

DVIZH Hermes control $VERSION installed.
Backup: $BACKUP_DIR

Hermes can READ DVIZH context and STAGE inert proposals.
Proposal types: task_create, task_complete, schedule_move, day_plan.
There is intentionally NO apply/approve command here.
No production DVIZH task, schedule, database row, service, or configuration was changed.

In Telegram send: /reset
Then you can test with a harmless proposal request, for example:
  "Используй dvizh-server. Предложи добавить тестовую задачу 'Проверка AI proposal', но ничего не применяй."
EOF
