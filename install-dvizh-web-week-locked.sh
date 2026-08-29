#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_REF="02ae8915b13be3958e645020d13a4b69fd5c555f"
INSTALLER_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${RELEASE_REF}/install-dvizh-web-week.sh"

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$INSTALLER_URL" \
  | sed "s#BRANCH=\"codex/dvizh-weekly-schedule-v1-2026-08-29\"#BRANCH=\"${RELEASE_REF}\"#" \
  | sudo bash
