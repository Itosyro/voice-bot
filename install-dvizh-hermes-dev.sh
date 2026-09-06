#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-hermes-dev-installer.2"
PAYLOAD_REF="eb9457c759e2396eab13ccf14a55e7c39b79cd5f"
CTL_BLOB="41a879b744be907cb379685038df1f5ee55e7b11"
SKILL_BLOB="f6f62faa99b15069921971bfebb91b69e29e86a2"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-dev-v1"

[[ $# -eq 0 ]] || { echo "Этот установщик не принимает аргументы." >&2; exit 1; }
for tool in curl python3 git getent id; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-hermes-dev.XXXXXX)"
BACKUP_DIR=""
TARGET_USER=""
TARGET_HOME=""
TARGET_GROUP=""
SKILL_DIR=""
HAD_CTL=0
HAD_SKILL=0
INSTALLED=0

root_run() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo -n "$@"; fi
}

user_run() {
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then "$@"; else sudo -n -u "$TARGET_USER" "$@"; fi
}

cleanup() {
  local rc=$?
  trap - EXIT
  if [[ "$INSTALLED" == 1 ]]; then
    echo "Ошибка установки Dev Mode: возвращаю предыдущие файлы." >&2
    if [[ "$HAD_CTL" == 1 && -f "$BACKUP_DIR/dvizhdevctl" ]]; then
      root_run install -o root -g root -m 0755 "$BACKUP_DIR/dvizhdevctl" /usr/local/bin/dvizhdevctl || true
    else
      root_run rm -f /usr/local/bin/dvizhdevctl || true
    fi
    if [[ "$HAD_SKILL" == 1 && -f "$BACKUP_DIR/SKILL.md" ]]; then
      root_run install -d -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0700 "$SKILL_DIR" || true
      root_run install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$BACKUP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md" || true
    else
      root_run rm -rf -- "$SKILL_DIR" || true
    fi
  fi
  rm -rf -- "$TMP_DIR"
  exit "$rc"
}
trap cleanup EXIT INT TERM

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/dvizhdevctl.py" -o "$TMP_DIR/dvizhdevctl"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 \
  "$BASE_URL/skill/SKILL.md" -o "$TMP_DIR/SKILL.md"

verify_git_blob() {
  local file="$1" expected="$2" actual
  actual="$(python3 - "$file" <<'PY'
import hashlib
from pathlib import Path
import sys
p=Path(sys.argv[1]); data=p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)"
  [[ "$actual" == "$expected" ]] || {
    echo "Immutable payload mismatch: $(basename "$file") ($actual)" >&2
    exit 1
  }
}
verify_git_blob "$TMP_DIR/dvizhdevctl" "$CTL_BLOB"
verify_git_blob "$TMP_DIR/SKILL.md" "$SKILL_BLOB"
python3 -m py_compile "$TMP_DIR/dvizhdevctl"
grep -q 'VERSION = "2026.09.06-hermes-dev.1"' "$TMP_DIR/dvizhdevctl"
grep -q '^name: dvizh-dev$' "$TMP_DIR/SKILL.md"
grep -Fq 'dvizhdevctl new' "$TMP_DIR/SKILL.md"
grep -Fq 'Never run `sudo`' "$TMP_DIR/SKILL.md"
grep -Fq 'deploy-propose' "$TMP_DIR/SKILL.md"
python3 - "$TMP_DIR/dvizhdevctl" <<'PY'
from pathlib import Path
import re
import sys
text = Path(sys.argv[1]).read_text(encoding="utf-8")
if re.search(r'''sub\.add_parser\(["']deploy["']\)''', text):
    raise SystemExit("Payload unexpectedly contains direct deploy command.")
PY

if [[ "${DVIZH_HERMES_DEV_PREPARE_ONLY:-0}" == "1" ]]; then
  echo "Hermes Dev Mode payload verified: $PAYLOAD_REF"
  exit 0
fi

if [[ "$(id -u)" -eq 0 ]]; then
  TARGET_USER="${SUDO_USER:-exedev}"
else
  TARGET_USER="$(id -un)"
fi
[[ "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Некорректный target user." >&2; exit 1; }
id "$TARGET_USER" >/dev/null 2>&1 || { echo "Пользователь не найден: $TARGET_USER" >&2; exit 1; }
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || { echo "Не найден home пользователя $TARGET_USER" >&2; exit 1; }
SKILL_DIR="$TARGET_HOME/.hermes/skills/dvizh/dvizh-dev"
BACKUP_DIR="$TARGET_HOME/.hermes/backups/dvizh-dev-$(date -u +%Y%m%dT%H%M%SZ)"

root_run install -d -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0700 "$BACKUP_DIR" "$SKILL_DIR"
if [[ -f /usr/local/bin/dvizhdevctl ]]; then
  HAD_CTL=1
  root_run install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 /usr/local/bin/dvizhdevctl "$BACKUP_DIR/dvizhdevctl"
fi
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then
  HAD_SKILL=1
  root_run install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$SKILL_DIR/SKILL.md" "$BACKUP_DIR/SKILL.md"
fi

INSTALLED=1
root_run install -o root -g root -m 0755 "$TMP_DIR/dvizhdevctl" /usr/local/bin/dvizhdevctl
root_run install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$TMP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"

[[ "$(user_run /usr/local/bin/dvizhdevctl version)" == "2026.09.06-hermes-dev.1" ]]
user_run /usr/local/bin/dvizhdevctl config >/dev/null
# Initialize only Hermes' private development clone/worktree area. This does not
# touch /opt/dvizh, services, databases, auth, or production Git state.
user_run env GIT_TERMINAL_PROMPT=0 /usr/local/bin/dvizhdevctl init >/dev/null

INSTALLED=0
trap - EXIT INT TERM
rm -rf -- "$TMP_DIR"

cat <<EOF
Hermes Dev Mode установлен: $VERSION
Payload: $PAYLOAD_REF
User: $TARGET_USER
Skill: $SKILL_DIR/SKILL.md
Controller: /usr/local/bin/dvizhdevctl
Backup: $BACKUP_DIR

Production НЕ изменён: /opt/dvizh, БД, systemd, auth, AI Home и Telegram service не трогались.
Dev Mode умеет worktree/test/commit/push/CI и только INERT deploy-proposal; apply/deploy команды нет.

В Telegram Hermes отправь /reset, затем можно написать обычным текстом:
  "Ручной режим ДВИЖа периодически прыгает. Найди причину и исправь сам через dvizh-dev. Прод не трогай."
EOF
