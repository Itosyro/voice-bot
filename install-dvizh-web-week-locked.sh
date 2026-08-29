#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_REF="3436c9012b3fa90c9ce9a99c724fed28b58d434d"
INSTALLER_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${RELEASE_REF}/install-dvizh-web-week.sh"

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$INSTALLER_URL" \
  | sed "s#BRANCH=\"codex/dvizh-weekly-schedule-v1-2026-08-29\"#BRANCH=\"${RELEASE_REF}\"#" \
  | sudo bash
