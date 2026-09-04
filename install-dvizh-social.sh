#!/usr/bin/env bash
set -Eeuo pipefail

# Immutable, fully reconstructed Social Hub release.
ARCHIVE_REF="03529ca8606df63132f212cdfe4eb2f1c25a875f"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${ARCHIVE_REF}/social-release-v2"
RELEASE_SHA256="709137e20a89b3e157f5a51964d93e48ee01001b4faf66a38dde7397fce8c64b"
TMP_DIR="$(mktemp -d /tmp/dvizh-social-bootstrap.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

for part in \
  part-00.b64 part-01.b64 part-02.b64 part-03.b64 \
  part-04.b64 part-05.b64 part-06.b64
do
  curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
    "$BASE_URL/$part" -o "$TMP_DIR/$part"
done

cat \
  "$TMP_DIR/part-00.b64" "$TMP_DIR/part-01.b64" "$TMP_DIR/part-02.b64" \
  "$TMP_DIR/part-03.b64" "$TMP_DIR/part-04.b64" "$TMP_DIR/part-05.b64" \
  "$TMP_DIR/part-06.b64" \
  | base64 --decode > "$TMP_DIR/release.tar.gz"

echo "$RELEASE_SHA256  $TMP_DIR/release.tar.gz" | sha256sum -c -
tar -xzf "$TMP_DIR/release.tar.gz" -C "$TMP_DIR"

BUILD_DIR="$TMP_DIR/dvizh-social-build"
test -s "$BUILD_DIR/install.sh"
chmod +x "$BUILD_DIR/install.sh"

if [[ "${DVIZH_SOCIAL_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "DVIZH Social Hub release verified: $RELEASE_SHA256"
  find "$BUILD_DIR" -type f -printf '%P\n' | sort
  exit 0
fi

exec sudo -n env DVIZH_SOCIAL_PAYLOAD_DIR="$BUILD_DIR" bash "$BUILD_DIR/install.sh"
