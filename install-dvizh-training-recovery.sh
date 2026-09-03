#!/usr/bin/env bash
set -Eeuo pipefail

# Immutable source that already passed the full training CI suite.
SOURCE_REF="2dfa291fa15d7983b63ee4002ee4aecf4e5e5d92"
SOURCE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${SOURCE_REF}/install-dvizh-training.sh"
TMP="$(mktemp /tmp/dvizh-training-recovery.XXXXXX)"
trap 'rm -f "$TMP"' EXIT

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$SOURCE_URL" -o "$TMP"
grep -q '^BRANCH="codex/dvizh-training-readiness-v1-2026-08-30"$' "$TMP"

python3 - "$TMP" "$SOURCE_REF" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1])
source_ref = sys.argv[2]
text = path.read_text(encoding="utf-8")
marker = "# DVIZH_TRAINING_DEPENDENCY_RECOVERY_V2"

if marker not in text:
    preflight_anchor = (
        "for unit in dvizh.service dvizh-auth.service dvizh-telegram.service "
        "dvizh-bridge.service dvizh-web-week.service dvizh-web-editor.service; do\n"
    )
    preflight_insert = (
        f"{marker}\n"
        "# dvizh-web-week and dvizh-web-editor Require=dvizh-telegram. A previous\n"
        "# interrupted install may therefore leave them stopped even after Telegram\n"
        "# has started again. Recover them before the normal preflight checks.\n"
        "systemctl reset-failed dvizh-web-week.service dvizh-web-editor.service >/dev/null 2>&1 || true\n"
        "systemctl start dvizh-web-week.service dvizh-web-editor.service >/dev/null 2>&1 || true\n\n"
    )

    telegram_restart_anchor = (
        "systemctl start dvizh-telegram.service\n"
        "systemctl is-active --quiet dvizh-telegram.service\n"
    )
    telegram_restart_replacement = (
        "systemctl start dvizh-telegram.service\n"
        "systemctl is-active --quiet dvizh-telegram.service\n"
        "# Stopping Telegram also stops both dependent web bridges. Explicitly bring\n"
        "# them back; systemd does not automatically restart Requires= dependents.\n"
        "systemctl reset-failed dvizh-web-week.service dvizh-web-editor.service >/dev/null 2>&1 || true\n"
        "systemctl start dvizh-web-week.service dvizh-web-editor.service\n"
        "systemctl is-active --quiet dvizh-web-week.service\n"
        "systemctl is-active --quiet dvizh-web-editor.service\n"
    )

    rollback_anchor = (
        "  systemctl restart dvizh-telegram.service >/dev/null 2>&1 || true\n"
        "  cleanup\n"
    )
    rollback_replacement = (
        "  systemctl restart dvizh-telegram.service >/dev/null 2>&1 || true\n"
        "  systemctl reset-failed dvizh-web-week.service dvizh-web-editor.service >/dev/null 2>&1 || true\n"
        "  systemctl start dvizh-web-week.service dvizh-web-editor.service >/dev/null 2>&1 || true\n"
        "  cleanup\n"
    )

    replacements = (
        (preflight_anchor, preflight_insert + preflight_anchor, "preflight recovery"),
        (telegram_restart_anchor, telegram_restart_replacement, "post-Telegram recovery"),
        (rollback_anchor, rollback_replacement, "rollback recovery"),
    )
    for old, new, label in replacements:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"{label}: expected one anchor, found {count}")
        text = text.replace(old, new, 1)

text = text.replace(
    'VERSION="2026.08.30-training.1"',
    'VERSION="2026.09.02-training.2"',
    1,
)
text = text.replace(
    'BRANCH="codex/dvizh-training-readiness-v1-2026-08-30"',
    f'BRANCH="{source_ref}"',
    1,
)
path.write_text(text, encoding="utf-8")
PY

bash -n "$TMP"
grep -q 'DVIZH_TRAINING_DEPENDENCY_RECOVERY_V2' "$TMP"
grep -q "^BRANCH=\"${SOURCE_REF}\"$" "$TMP"

# CI can validate the exact generated installer without touching systemd.
if [[ "${DVIZH_TRAINING_PREPARE_ONLY:-0}" == "1" ]]; then
  cat "$TMP"
  exit 0
fi

exec sudo -n bash "$TMP"
