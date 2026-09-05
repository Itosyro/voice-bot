#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-hermes-control.3"
PAYLOAD_REF="5bd42e52603a1200b42f598381af4346465d98a1"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-control-v1"
TMP_DIR="$(mktemp -d /tmp/dvizh-hermes-control.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizhctl" -o "$TMP_DIR/dvizhctl"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizh_context.py" -o "$TMP_DIR/dvizh-context"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/skill/SKILL.md" -o "$TMP_DIR/SKILL.md"

bash -n "$TMP_DIR/dvizhctl"
python3 -m py_compile "$TMP_DIR/dvizh-context"
grep -q 'VERSION="2026.09.05-hermes-control.3"' "$TMP_DIR/dvizhctl"
grep -q 'VERSION = "2026.09.05-hermes-context.1"' "$TMP_DIR/dvizh-context"
grep -q '^name: dvizh-server$' "$TMP_DIR/SKILL.md"
grep -q 'dvizhctl context today' "$TMP_DIR/SKILL.md"
grep -q 'read-only' "$TMP_DIR/SKILL.md"

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
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || { echo "Cannot resolve home for $TARGET_USER" >&2; exit 1; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$TARGET_HOME/.hermes/backups/dvizh-control-$STAMP"
SKILL_DIR="$TARGET_HOME/.hermes/skills/dvizh/dvizh-server"
HELPER_PATH="/usr/local/libexec/dvizh-context"
SUDOERS_PATH="/etc/sudoers.d/dvizh-hermes-context"
HAD_CTL=0
HAD_HELPER=0
HAD_SKILL=0
HAD_SUDOERS=0
INSTALLED=0

root_run() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

mkdir_as_user() {
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then
    mkdir -p "$1"
  else
    sudo -n -u "$TARGET_USER" mkdir -p "$1"
  fi
}

copy_as_user() {
  local src="$1" dst="$2"
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then
    cp "$src" "$dst"
  else
    sudo -n -u "$TARGET_USER" cp "$src" "$dst"
  fi
}

remove_as_user() {
  local path="$1"
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then
    rm -rf "$path"
  else
    sudo -n -u "$TARGET_USER" rm -rf "$path"
  fi
}

rollback() {
  local rc=$?
  if [[ "$INSTALLED" == "1" ]]; then
    echo "Ошибка. Возвращаю предыдущий Hermes control layer..." >&2
    if [[ "$HAD_CTL" == "1" && -f "$BACKUP_DIR/dvizhctl" ]]; then
      root_run install -o root -g root -m 0755 "$BACKUP_DIR/dvizhctl" /usr/local/bin/dvizhctl || true
    else
      root_run rm -f /usr/local/bin/dvizhctl || true
    fi
    if [[ "$HAD_HELPER" == "1" && -f "$BACKUP_DIR/dvizh-context" ]]; then
      root_run install -o root -g root -m 0755 "$BACKUP_DIR/dvizh-context" "$HELPER_PATH" || true
    else
      root_run rm -f "$HELPER_PATH" || true
    fi
    if [[ "$HAD_SUDOERS" == "1" && -f "$BACKUP_DIR/sudoers" ]]; then
      root_run install -o root -g root -m 0440 "$BACKUP_DIR/sudoers" "$SUDOERS_PATH" || true
    else
      root_run rm -f "$SUDOERS_PATH" || true
    fi
    if [[ "$HAD_SKILL" == "1" && -f "$BACKUP_DIR/SKILL.md" ]]; then
      mkdir_as_user "$SKILL_DIR" || true
      copy_as_user "$BACKUP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md" || true
    else
      remove_as_user "$SKILL_DIR" || true
    fi
  fi
  exit "$rc"
}
trap rollback ERR INT TERM

mkdir_as_user "$BACKUP_DIR"
mkdir_as_user "$SKILL_DIR"

if [[ -f /usr/local/bin/dvizhctl ]]; then
  HAD_CTL=1
  root_run cp /usr/local/bin/dvizhctl "$TMP_DIR/dvizhctl.previous"
  copy_as_user "$TMP_DIR/dvizhctl.previous" "$BACKUP_DIR/dvizhctl"
fi
if [[ -f "$HELPER_PATH" ]]; then
  HAD_HELPER=1
  root_run cp "$HELPER_PATH" "$TMP_DIR/dvizh-context.previous"
  copy_as_user "$TMP_DIR/dvizh-context.previous" "$BACKUP_DIR/dvizh-context"
fi
if [[ -f "$SUDOERS_PATH" ]]; then
  HAD_SUDOERS=1
  root_run cp "$SUDOERS_PATH" "$TMP_DIR/sudoers.previous"
  copy_as_user "$TMP_DIR/sudoers.previous" "$BACKUP_DIR/sudoers"
fi
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
  HAD_SKILL=1
  cp "$SKILL_DIR/SKILL.md" "$TMP_DIR/SKILL.previous.md"
  copy_as_user "$TMP_DIR/SKILL.previous.md" "$BACKUP_DIR/SKILL.md"
fi

cat > "$TMP_DIR/sudoers" <<EOF
# Read-only DVIZH context exporter for Hermes. The helper accepts only fixed view names.
$TARGET_USER ALL=(dvizh) NOPASSWD: $HELPER_PATH *
EOF
chmod 0440 "$TMP_DIR/sudoers"
if command -v visudo >/dev/null 2>&1; then
  root_run visudo -cf "$TMP_DIR/sudoers" >/dev/null
fi

INSTALLED=1
root_run install -d -o root -g root -m 0755 /usr/local/libexec
root_run install -o root -g root -m 0755 "$TMP_DIR/dvizhctl" /usr/local/bin/dvizhctl
root_run install -o root -g root -m 0755 "$TMP_DIR/dvizh-context" "$HELPER_PATH"
root_run install -o root -g root -m 0440 "$TMP_DIR/sudoers" "$SUDOERS_PATH"
copy_as_user "$TMP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
if [[ "$(id -un)" == "$TARGET_USER" ]]; then chmod 0600 "$SKILL_DIR/SKILL.md"; else sudo -n -u "$TARGET_USER" chmod 0600 "$SKILL_DIR/SKILL.md"; fi

printf '[1/4] Installed read-only dvizhctl\n'
[[ "$(/usr/local/bin/dvizhctl version)" == "$VERSION" ]]
/usr/local/bin/dvizhctl version
printf '[2/4] Installed sanitized data-context helper\n'
[[ -x "$HELPER_PATH" ]]
printf '[3/4] Installed Hermes skill: %s\n' "$SKILL_DIR/SKILL.md"
printf '[4/4] Running read-only status/context smoke checks...\n'
/usr/local/bin/dvizhctl status || true
/usr/local/bin/dvizhctl context health >/dev/null

INSTALLED=0
trap - ERR INT TERM

cat <<EOF

DVIZH Hermes control $VERSION installed.
Backup: $BACKUP_DIR

Hermes can now READ DVIZH context through:
  dvizhctl context today
  dvizhctl context week
  dvizhctl context training
  dvizhctl context jump
  dvizhctl context social

No DVIZH task, schedule, database row, service, or configuration was changed.
In Telegram send: /reset
Then ask: "Используй skill dvizh-server. Прочитай dvizhctl context today и коротко скажи, что у меня сегодня. Ничего не меняй."
EOF
