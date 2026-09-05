#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-hermes-control.2"
PAYLOAD_REF="238dfa6ae50f773acb453c6f68656ca6d58b4278"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-control-v1"
TMP_DIR="$(mktemp -d /tmp/dvizh-hermes-control.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ "$(id -u)" -eq 0 ]]; then
  TARGET_USER="${SUDO_USER:-exedev}"
else
  TARGET_USER="$(id -un)"
fi
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || { echo "Cannot resolve home for $TARGET_USER" >&2; exit 1; }

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizhctl" -o "$TMP_DIR/dvizhctl"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/skill/SKILL.md" -o "$TMP_DIR/SKILL.md"

bash -n "$TMP_DIR/dvizhctl"
grep -q 'VERSION="2026.09.05-hermes-control.2"' "$TMP_DIR/dvizhctl"
grep -q '^name: dvizh-server$' "$TMP_DIR/SKILL.md"
grep -q 'read-only' "$TMP_DIR/SKILL.md"
grep -q 'redacts common token/key/password patterns' "$TMP_DIR/SKILL.md"

if [[ "${DVIZH_HERMES_CONTROL_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "DVIZH Hermes control payload verified from $PAYLOAD_REF."
  exit 0
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$TARGET_HOME/.hermes/backups/dvizh-control-$STAMP"
SKILL_DIR="$TARGET_HOME/.hermes/skills/dvizh/dvizh-server"
HAD_CTL=0
HAD_SKILL=0
INSTALLED=0

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
      if [[ "$(id -u)" -eq 0 ]]; then
        install -o root -g root -m 0755 "$BACKUP_DIR/dvizhctl" /usr/local/bin/dvizhctl || true
      else
        sudo -n install -o root -g root -m 0755 "$BACKUP_DIR/dvizhctl" /usr/local/bin/dvizhctl || true
      fi
    else
      if [[ "$(id -u)" -eq 0 ]]; then rm -f /usr/local/bin/dvizhctl || true; else sudo -n rm -f /usr/local/bin/dvizhctl || true; fi
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
  cp /usr/local/bin/dvizhctl "$TMP_DIR/dvizhctl.previous"
  copy_as_user "$TMP_DIR/dvizhctl.previous" "$BACKUP_DIR/dvizhctl"
fi
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
  HAD_SKILL=1
  cp "$SKILL_DIR/SKILL.md" "$TMP_DIR/SKILL.previous.md"
  copy_as_user "$TMP_DIR/SKILL.previous.md" "$BACKUP_DIR/SKILL.md"
fi

INSTALLED=1
if [[ "$(id -u)" -eq 0 ]]; then
  install -o root -g root -m 0755 "$TMP_DIR/dvizhctl" /usr/local/bin/dvizhctl
else
  sudo -n install -o root -g root -m 0755 "$TMP_DIR/dvizhctl" /usr/local/bin/dvizhctl
fi
copy_as_user "$TMP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
chmod 0600 "$SKILL_DIR/SKILL.md" 2>/dev/null || true

printf '[1/3] Installed read-only dvizhctl\n'
[[ "$(/usr/local/bin/dvizhctl version)" == "$VERSION" ]]
/usr/local/bin/dvizhctl version
printf '[2/3] Installed Hermes skill: %s\n' "$SKILL_DIR/SKILL.md"
printf '[3/3] Running read-only status check...\n'
/usr/local/bin/dvizhctl status || true

# A new Telegram message creates/refreshes the skill index, so no DVIZH service
# needs restarting. We intentionally do not restart the Hermes gateway here.
INSTALLED=0
trap - ERR INT TERM

cat <<EOF

DVIZH Hermes control $VERSION installed.
Backup: $BACKUP_DIR

No DVIZH service, database, or configuration was changed.
In Telegram send: /reset
Then ask: "Используй skill dvizh-server и проверь ДВИЖ. Ничего не меняй."
EOF
