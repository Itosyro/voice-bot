#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.08-hermes-autopilot-installer.1"
PAYLOAD_REF="4424a8922c4cc8013ecb15bda501558808070490"
AUTOPILOT_BLOB="5da144b8b014abd5b73d625e565ed06cb4d6a80c"
RELEASE_BLOB="b25a42654300f0e5595763a8b8753188039e34e3"
SKILL_BLOB="1cc82c07df04e59bd14e8eb641bae77e6f98c009"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-dev-v2"
PREPARE_ONLY="${DVIZH_HERMES_AUTOPILOT_PREPARE_ONLY:-0}"

[[ $# -eq 0 ]] || { echo "Этот установщик не принимает аргументы." >&2; exit 1; }
for tool in curl python3 git ssh-keygen getent id stat install mktemp sha256sum grep visudo; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-hermes-autopilot.XXXXXX)"
TARGET_USER=""
TARGET_HOME=""
TARGET_GROUP=""
SKILL_DIR=""
BACKUP_DIR=""
KEY_DIR=""
KEY_PATH=""
SUDOERS_PATH="/etc/sudoers.d/dvizh-hermes-autopilot"
HAD_AUTOPILOT=0
HAD_RELEASE=0
HAD_SKILL=0
HAD_SUDOERS=0
GENERATED_KEY=0
INSTALLED=0

cleanup() {
  local rc=$?
  trap - EXIT INT TERM HUP
  if [[ "$INSTALLED" == 1 ]]; then
    echo "Ошибка установки Autopilot v2: возвращаю предыдущие файлы." >&2
    if [[ "$HAD_AUTOPILOT" == 1 ]]; then install -o root -g root -m 0755 "$BACKUP_DIR/dvizhautopilot" /usr/local/bin/dvizhautopilot || true; else rm -f /usr/local/bin/dvizhautopilot || true; fi
    if [[ "$HAD_RELEASE" == 1 ]]; then install -o root -g root -m 0755 "$BACKUP_DIR/dvizhrelease" /usr/local/sbin/dvizhrelease || true; else rm -f /usr/local/sbin/dvizhrelease || true; fi
    if [[ "$HAD_SKILL" == 1 ]]; then install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$BACKUP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md" || true; else rm -f "$SKILL_DIR/SKILL.md" || true; fi
    if [[ "$HAD_SUDOERS" == 1 ]]; then install -o root -g root -m 0440 "$BACKUP_DIR/sudoers" "$SUDOERS_PATH" || true; else rm -f "$SUDOERS_PATH" || true; fi
    if [[ "$GENERATED_KEY" == 1 ]]; then rm -f -- "$KEY_PATH" "$KEY_PATH.pub" || true; fi
  fi
  rm -rf -- "$TMP_DIR"
  exit "$rc"
}
trap cleanup EXIT INT TERM HUP

curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/dvizhautopilot.py" -o "$TMP_DIR/dvizhautopilot"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/dvizhrelease.py" -o "$TMP_DIR/dvizhrelease"
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/skill/SKILL.md" -o "$TMP_DIR/SKILL.md"

verify_git_blob() {
  local file="$1" expected="$2" actual
  actual="$(python3 - "$file" <<'PY'
from pathlib import Path
import hashlib, sys
p=Path(sys.argv[1]); data=p.read_bytes()
print(hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest())
PY
)"
  [[ "$actual" == "$expected" ]] || { echo "Immutable payload mismatch: $(basename "$file") ($actual)" >&2; exit 1; }
}
verify_git_blob "$TMP_DIR/dvizhautopilot" "$AUTOPILOT_BLOB"
verify_git_blob "$TMP_DIR/dvizhrelease" "$RELEASE_BLOB"
verify_git_blob "$TMP_DIR/SKILL.md" "$SKILL_BLOB"
python3 -m py_compile "$TMP_DIR/dvizhautopilot" "$TMP_DIR/dvizhrelease"
grep -Fq 'VERSION = "2026.09.08-hermes-autopilot.1"' "$TMP_DIR/dvizhautopilot"
grep -Fq 'VERSION = "2026.09.08-dvizh-release-gate.1"' "$TMP_DIR/dvizhrelease"
grep -q '^name: dvizh-dev$' "$TMP_DIR/SKILL.md"
grep -Fq 'Do not call release-apply until a later user Telegram message contains that exact phrase.' "$TMP_DIR/SKILL.md"
grep -Fq 'SAFE_TARGETS' "$TMP_DIR/dvizhrelease"
grep -Fq 'DENY_PREFIXES' "$TMP_DIR/dvizhrelease"
! grep -Eq 'shell\s*=\s*True|os\.system\(' "$TMP_DIR/dvizhautopilot" "$TMP_DIR/dvizhrelease"

if [[ "$PREPARE_ONLY" == 1 ]]; then
  echo "Hermes Autopilot v2 payload verified: $PAYLOAD_REF"
  exit 0
fi

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Запусти через sudo: installer ставит root-owned release gate." >&2; exit 1; }
[[ -x /usr/local/bin/dvizhdevctl ]] || { echo "Сначала должен быть установлен Hermes Dev Mode v1 (/usr/local/bin/dvizhdevctl)." >&2; exit 1; }

TARGET_USER="${SUDO_USER:-exedev}"
[[ "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Некорректный target user." >&2; exit 1; }
id "$TARGET_USER" >/dev/null 2>&1 || { echo "Пользователь не найден: $TARGET_USER" >&2; exit 1; }
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || { echo "Не найден home пользователя $TARGET_USER" >&2; exit 1; }
[[ "$(stat -c '%U' "$TARGET_HOME")" == "$TARGET_USER" ]] || { echo "Home $TARGET_HOME не принадлежит $TARGET_USER." >&2; exit 1; }

SKILL_DIR="$TARGET_HOME/.hermes/skills/dvizh/dvizh-dev"
KEY_DIR="$TARGET_HOME/.hermes/dev/dvizh/github"
KEY_PATH="$KEY_DIR/id_ed25519"
BACKUP_DIR="$TARGET_HOME/.hermes/backups/dvizh-autopilot-$(date -u +%Y%m%dT%H%M%SZ)"

install -d -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0700 "$TARGET_HOME/.hermes" "$TARGET_HOME/.hermes/backups" "$TARGET_HOME/.hermes/skills" "$TARGET_HOME/.hermes/skills/dvizh" "$SKILL_DIR" "$TARGET_HOME/.hermes/dev" "$TARGET_HOME/.hermes/dev/dvizh" "$KEY_DIR" "$BACKUP_DIR"

if [[ -f /usr/local/bin/dvizhautopilot ]]; then HAD_AUTOPILOT=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 /usr/local/bin/dvizhautopilot "$BACKUP_DIR/dvizhautopilot"; fi
if [[ -f /usr/local/sbin/dvizhrelease ]]; then HAD_RELEASE=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 /usr/local/sbin/dvizhrelease "$BACKUP_DIR/dvizhrelease"; fi
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then HAD_SKILL=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$SKILL_DIR/SKILL.md" "$BACKUP_DIR/SKILL.md"; fi
if [[ -f "$SUDOERS_PATH" ]]; then HAD_SUDOERS=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$SUDOERS_PATH" "$BACKUP_DIR/sudoers"; fi

cat > "$TMP_DIR/sudoers" <<EOF
# DVIZH Hermes Autopilot v2: only the root-owned allowlisted release gate.
$TARGET_USER ALL=(root) NOPASSWD: /usr/local/sbin/dvizhrelease *
EOF
chmod 0440 "$TMP_DIR/sudoers"
visudo -cf "$TMP_DIR/sudoers" >/dev/null

if [[ -e "$KEY_PATH" || -e "$KEY_PATH.pub" ]]; then
  [[ -f "$KEY_PATH" && -f "$KEY_PATH.pub" && ! -L "$KEY_PATH" && ! -L "$KEY_PATH.pub" ]] || { echo "Небезопасное состояние GitHub deploy key path." >&2; exit 1; }
else
  sudo -u "$TARGET_USER" ssh-keygen -q -t ed25519 -f "$KEY_PATH" -C "dvizh-hermes-autopilot" -N ""
  GENERATED_KEY=1
fi
chown "$TARGET_USER:$TARGET_GROUP" "$KEY_PATH" "$KEY_PATH.pub"
chmod 0600 "$KEY_PATH"
chmod 0644 "$KEY_PATH.pub"

INSTALLED=1
install -o root -g root -m 0755 "$TMP_DIR/dvizhautopilot" /usr/local/bin/dvizhautopilot
install -o root -g root -m 0755 "$TMP_DIR/dvizhrelease" /usr/local/sbin/dvizhrelease
install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$TMP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
install -o root -g root -m 0440 "$TMP_DIR/sudoers" "$SUDOERS_PATH"
visudo -cf "$SUDOERS_PATH" >/dev/null

[[ "$(sudo -u "$TARGET_USER" /usr/local/bin/dvizhautopilot version)" == "2026.09.08-hermes-autopilot.1" ]]
sudo -u "$TARGET_USER" /usr/local/bin/dvizhdevctl config >/dev/null
sudo -u "$TARGET_USER" sudo -n /usr/local/sbin/dvizhrelease doctor >/dev/null

INSTALLED=0
trap - EXIT INT TERM HUP
rm -rf -- "$TMP_DIR"

cat <<EOF
Hermes Autopilot v2 установлен: $VERSION
Payload: $PAYLOAD_REF
User: $TARGET_USER
Autopilot: /usr/local/bin/dvizhautopilot
Release gate: /usr/local/sbin/dvizhrelease
Skill: $SKILL_DIR/SKILL.md
Sudoers: $SUDOERS_PATH
Backup: $BACKUP_DIR

Production-приложение не изменено. Установлена только dev/release инфраструктура.
Root-доступ ограничен root-owned dvizhrelease gate; произвольный sudo не выдавался.

ONE-TIME GITHUB SETUP REQUIRED
Добавь следующий PUBLIC deploy key в GitHub repo Itosyro/voice-bot → Settings → Deploy keys → Add deploy key.
Поставь галочку "Allow write access". Приватный файл $KEY_PATH никому не отправляй.

--- PUBLIC KEY START ---
$(cat "$KEY_PATH.pub")
--- PUBLIC KEY END ---

После добавления ключа в Telegram отправь Hermes:
  /reset
  Используй dvizh-dev. Запусти dvizhautopilot doctor и подтверди, что Autopilot v2 полностью готов.
EOF
