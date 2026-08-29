#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="codex/dvizh-auth-gateway-2026-08-29"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${BRANCH}/dvizh-auth-release"
RELEASE_SHA256="1bdc9b0ed9ed7e4f2961d57a437dbdc3fc0424567303cb6760b3d029ca1d1be3"
TMP_DIR="$(mktemp -d /tmp/dvizh-auth-bootstrap.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

for part in part-00.b64 part-01.b64 part-02.b64 part-03.b64; do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
    "$BASE_URL/$part" -o "$TMP_DIR/$part"
done
cat "$TMP_DIR"/part-*.b64 | base64 --decode > "$TMP_DIR/release.tar.gz"
echo "$RELEASE_SHA256  $TMP_DIR/release.tar.gz" | sha256sum -c -
tar -xzf "$TMP_DIR/release.tar.gz" -C "$TMP_DIR"
BUILD_DIR="$TMP_DIR/dvizh-auth-build"
[[ -x "$BUILD_DIR/install.sh" ]] || chmod +x "$BUILD_DIR/install.sh"
DVIZH_AUTH_PAYLOAD_DIR="$BUILD_DIR" exec sudo -n bash "$BUILD_DIR/install.sh"
