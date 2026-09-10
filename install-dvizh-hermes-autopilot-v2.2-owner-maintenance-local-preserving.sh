#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.10-dvizh-owner-maintenance-v2.2.2-wrapper.1"
REPO="Itosyro/voice-bot"
SOURCE_COMMIT="e197c5eff9bb2a8342478ac3f854e02bc9106b9d"
SOURCE_BLOB="51dc92d42180c2b3cdba1220fb9fbb62f4a07103"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

git_blob_sha1() {
  python3 - "$1" <<'PY'
import hashlib, pathlib, sys
p=pathlib.Path(sys.argv[1]); d=p.read_bytes()
h=hashlib.sha1(); h.update(f"blob {len(d)}\0".encode()); h.update(d)
print(h.hexdigest())
PY
}

command -v curl >/dev/null || fail "curl is required"
command -v python3 >/dev/null || fail "python3 is required"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
curl -fsSL "https://raw.githubusercontent.com/$REPO/$SOURCE_COMMIT/install-dvizh-hermes-autopilot-v2.2-owner-maintenance.sh" -o "$TMP"
[[ "$(git_blob_sha1 "$TMP")" == "$SOURCE_BLOB" ]] || fail "pinned compatibility installer blob mismatch"
python3 - "$TMP" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text(encoding='utf-8')
old='  grep -Fq "--approval \'APPROVE <proposal-id> <token>\'" "$p" || return 1'
new='  grep -Fq -- "--approval \'APPROVE <proposal-id> <token>\'" "$p" || return 1'
if s.count(old) != 1:
    raise SystemExit('expected exactly one compatibility grep site')
p.write_text(s.replace(old,new), encoding='utf-8')
PY
bash -n "$TMP"
bash "$TMP"
