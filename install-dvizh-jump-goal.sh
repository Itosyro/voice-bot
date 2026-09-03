#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_REF="1b27507c72d85b7534a004f4d88d859ad30764f3"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${RELEASE_REF}/jump-goal-release"
RELEASE_SHA256="d1c26b523e56093fb710d2ab31036c65a78ed870e509f7f451f85848daba51db"
TMP_DIR="$(mktemp -d /tmp/dvizh-jump-bootstrap.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

for part in \
  part-00.b64 part-01.b64 part-02.b64 part-03.b64 part-04.b64 \
  part-05.b64 part-06.b64 part-07.b64 part-08.b64 part-09.b64
do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
    "$BASE_URL/$part" -o "$TMP_DIR/$part"
done

cat "$TMP_DIR"/part-*.b64 | base64 --decode > "$TMP_DIR/release.tar.gz"
echo "$RELEASE_SHA256  $TMP_DIR/release.tar.gz" | sha256sum -c -
tar -xzf "$TMP_DIR/release.tar.gz" -C "$TMP_DIR"

BUILD_DIR="$TMP_DIR/dvizh-jump-build"
test -s "$BUILD_DIR/install.sh"
chmod +x "$BUILD_DIR/install.sh"

exec sudo -n env DVIZH_JUMP_PAYLOAD_DIR="$BUILD_DIR" bash "$BUILD_DIR/install.sh"
