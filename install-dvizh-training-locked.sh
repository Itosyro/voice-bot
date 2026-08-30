#!/usr/bin/env bash
set -Eeuo pipefail

PINNED_REF="2dfa291fa15d7983b63ee4002ee4aecf4e5e5d92"
URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PINNED_REF}/install-dvizh-training.sh"
TMP="$(mktemp /tmp/dvizh-training-installer.XXXXXX)"
trap 'rm -f "$TMP"' EXIT

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$URL" -o "$TMP"
grep -q '^BRANCH="codex/dvizh-training-readiness-v1-2026-08-30"$' "$TMP"
sed -i "s|^BRANCH=.*$|BRANCH=\"${PINNED_REF}\"|" "$TMP"
bash -n "$TMP"
exec sudo -n bash "$TMP"
