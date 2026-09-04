#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_REF="3ee7958d23a75ae1e77eb22f53b2cc0f76efe6a0"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${SOURCE_REF}/minimal-ui-v1"
PATCH_SHA256="4a476c8d2d465ee6b8c1fac218d4447db6aeba4c59fac3abde193ca5ae1adb2d"
INSTALL_SHA256="85f646727678e80ba396b4dc3a4b9e40cb7d9d151aeb81ee09763bad98ed8bf1"
TMP_DIR="$(mktemp -d /tmp/dvizh-minimal-ui-bootstrap.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/patch_minimal_ui.py" -o "$TMP_DIR/patch_minimal_ui.py"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/install.sh" -o "$TMP_DIR/install.sh"

echo "$PATCH_SHA256  $TMP_DIR/patch_minimal_ui.py" | sha256sum -c -
echo "$INSTALL_SHA256  $TMP_DIR/install.sh" | sha256sum -c -
chmod +x "$TMP_DIR/install.sh" "$TMP_DIR/patch_minimal_ui.py"

exec sudo -n env DVIZH_MINIMAL_UI_PAYLOAD_DIR="$TMP_DIR" bash "$TMP_DIR/install.sh"
