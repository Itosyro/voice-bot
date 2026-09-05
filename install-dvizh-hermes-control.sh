#!/usr/bin/env bash
set -Eeuo pipefail

PAYLOAD_REF="0347bc9c54053bf9cee74d247d63d3b90a5c2b88"
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
grep -q '^name: dvizh-server$' "$TMP_DIR/SKILL.md"
grep -q 'read-only' "$TMP_DIR/SKILL.md"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$TARGET_HOME/.hermes/backups/dvizh-control-$STAMP"
SKILL_DIR="$TARGET_HOME/.hermes/skills/dvizh/dvizh-server"

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

mkdir_as_user "$BACKUP_DIR"
mkdir_as_user "$SKILL_DIR"

if [[ -f /usr/local/bin/dvizhctl ]]; then
  cp /usr/local/bin/dvizhctl "$TMP_DIR/dvizhctl.previous"
  copy_as_user "$TMP_DIR/dvizhctl.previous" "$BACKUP_DIR/dvizhctl"
fi
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
  cp "$SKILL_DIR/SKILL.md" "$TMP_DIR/SKILL.previous.md"
  copy_as_user "$TMP_DIR/SKILL.previous.md" "$BACKUP_DIR/SKILL.md"
fi

if [[ "$(id -u)" -eq 0 ]]; then
  install -o root -g root -m 0755 "$TMP_DIR/dvizhctl" /usr/local/bin/dvizhctl
else
  sudo -n install -o root -g root -m 0755 "$TMP_DIR/dvizhctl" /usr/local/bin/dvizhctl
fi
copy_as_user "$TMP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"

printf '[1/3] Installed read-only dvizhctl\n'
/usr/local/bin/dvizhctl version
printf '[2/3] Installed Hermes skill: %s\n' "$SKILL_DIR/SKILL.md"
printf '[3/3] Running read-only status check...\n'
/usr/local/bin/dvizhctl status || true

cat <<EOF

DVIZH Hermes control 2026.09.05-hermes-control.1 installed.
Backup: $BACKUP_DIR

No DVIZH service, database, or configuration was changed.
In Telegram send: /reset
Then ask: "Используй skill dvizh-server и проверь ДВИЖ. Ничего не меняй."
EOF
