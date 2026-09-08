#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.08-hermes-autopilot-installer.2"
PAYLOAD_REF="0b6f9f17f1d1d314be61ec6b9b2a104b343ba864"
AUTOPILOT_BLOB="1133a558b459dc5c1d4f76af066eb8132506e6be"
RELEASE_BLOB="b25a42654300f0e5595763a8b8753188039e34e3"
GIT_GATE_BLOB="71a50de55f30858708b0c5d6e3e7946e3211ff31"
SKILL_BLOB="626a3c29cfd4f77f2612c92f2b4ff20780f473ce"
BASE_URL="https://raw.githubusercontent.com/Itosyro/voice-bot/${PAYLOAD_REF}/hermes-dev-v2"
PREPARE_ONLY="${DVIZH_HERMES_AUTOPILOT_PREPARE_ONLY:-0}"

[[ $# -eq 0 ]] || { echo "Этот установщик не принимает аргументы." >&2; exit 1; }
for tool in curl python3 git ssh-keygen getent id stat install mktemp grep visudo; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-hermes-autopilot.XXXXXX)"
TARGET_USER=""
TARGET_HOME=""
TARGET_GROUP=""
SKILL_DIR=""
BACKUP_DIR=""
ROOT_KEY_DIR="/var/lib/dvizh/autopilot-github"
KEY_PATH="$ROOT_KEY_DIR/id_ed25519"
SUDOERS_PATH="/etc/sudoers.d/dvizh-hermes-autopilot"
HAD_AUTOPILOT=0
HAD_RELEASE=0
HAD_GIT_GATE=0
HAD_SKILL=0
HAD_SUDOERS=0
GENERATED_KEY=0
INSTALLED=0

cleanup() {
  local rc=$?
  trap - EXIT INT TERM HUP
  if [[ "$INSTALLED" == 1 ]]; then
    echo "Ошибка установки Autopilot v2.1: возвращаю предыдущую dev-инфраструктуру." >&2
    if [[ "$HAD_AUTOPILOT" == 1 ]]; then install -o root -g root -m 0755 "$BACKUP_DIR/dvizhautopilot" /usr/local/bin/dvizhautopilot || true; else rm -f /usr/local/bin/dvizhautopilot || true; fi
    if [[ "$HAD_RELEASE" == 1 ]]; then install -o root -g root -m 0755 "$BACKUP_DIR/dvizhrelease" /usr/local/sbin/dvizhrelease || true; else rm -f /usr/local/sbin/dvizhrelease || true; fi
    if [[ "$HAD_GIT_GATE" == 1 ]]; then install -o root -g root -m 0755 "$BACKUP_DIR/dvizhgitpush" /usr/local/sbin/dvizhgitpush || true; else rm -f /usr/local/sbin/dvizhgitpush || true; fi
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
curl --fail --silent --show-error --location --retry 4 --retry-delay 1 "$BASE_URL/dvizhgitpush.py" -o "$TMP_DIR/dvizhgitpush"
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
verify_git_blob "$TMP_DIR/dvizhgitpush" "$GIT_GATE_BLOB"
verify_git_blob "$TMP_DIR/SKILL.md" "$SKILL_BLOB"
python3 -m py_compile "$TMP_DIR/dvizhautopilot" "$TMP_DIR/dvizhrelease" "$TMP_DIR/dvizhgitpush"
grep -Fq 'VERSION = "2026.09.08-hermes-autopilot.2"' "$TMP_DIR/dvizhautopilot"
grep -Fq 'VERSION = "2026.09.08-dvizh-release-gate.1"' "$TMP_DIR/dvizhrelease"
grep -Fq 'VERSION = "2026.09.08-dvizh-git-push-gate.1"' "$TMP_DIR/dvizhgitpush"
grep -q '^name: dvizh-dev$' "$TMP_DIR/SKILL.md"
grep -Fq 'friend-project paths' "$TMP_DIR/SKILL.md"
grep -Fq 'private GitHub deploy key' "$TMP_DIR/SKILL.md"
grep -Fq 'FRIEND_PROJECT_MARKERS' "$TMP_DIR/dvizhgitpush"
grep -Fq 'CONTROL_PLANE_DENY' "$TMP_DIR/dvizhgitpush"
! grep -Eq 'shell\s*=\s*True|os\.system\(' "$TMP_DIR/dvizhautopilot" "$TMP_DIR/dvizhrelease" "$TMP_DIR/dvizhgitpush"

if [[ "$PREPARE_ONLY" == 1 ]]; then
  echo "Hermes Autopilot v2.1 payload verified: $PAYLOAD_REF"
  exit 0
fi

[[ ${EUID:-$(id -u)} -eq 0 ]] || { echo "Запусти через sudo: installer ставит root-owned gates." >&2; exit 1; }
[[ -x /usr/local/bin/dvizhdevctl ]] || { echo "Сначала должен быть установлен Hermes Dev Mode v1 (/usr/local/bin/dvizhdevctl)." >&2; exit 1; }

TARGET_USER="${SUDO_USER:-exedev}"
[[ "$TARGET_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "Некорректный target user." >&2; exit 1; }
id "$TARGET_USER" >/dev/null 2>&1 || { echo "Пользователь не найден: $TARGET_USER" >&2; exit 1; }
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
TARGET_GROUP="$(id -gn "$TARGET_USER")"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME" ]] || { echo "Не найден home пользователя $TARGET_USER" >&2; exit 1; }
[[ "$(stat -c '%U' "$TARGET_HOME")" == "$TARGET_USER" ]] || { echo "Home $TARGET_HOME не принадлежит $TARGET_USER." >&2; exit 1; }

SKILL_DIR="$TARGET_HOME/.hermes/skills/dvizh/dvizh-dev"
BACKUP_DIR="$TARGET_HOME/.hermes/backups/dvizh-autopilot-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0700 "$TARGET_HOME/.hermes" "$TARGET_HOME/.hermes/backups" "$TARGET_HOME/.hermes/skills" "$TARGET_HOME/.hermes/skills/dvizh" "$SKILL_DIR" "$BACKUP_DIR"
install -d -o root -g root -m 0700 "$ROOT_KEY_DIR"

if [[ -f /usr/local/bin/dvizhautopilot ]]; then HAD_AUTOPILOT=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 /usr/local/bin/dvizhautopilot "$BACKUP_DIR/dvizhautopilot"; fi
if [[ -f /usr/local/sbin/dvizhrelease ]]; then HAD_RELEASE=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 /usr/local/sbin/dvizhrelease "$BACKUP_DIR/dvizhrelease"; fi
if [[ -f /usr/local/sbin/dvizhgitpush ]]; then HAD_GIT_GATE=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 /usr/local/sbin/dvizhgitpush "$BACKUP_DIR/dvizhgitpush"; fi
if [[ -f "$SKILL_DIR/SKILL.md" ]]; then HAD_SKILL=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$SKILL_DIR/SKILL.md" "$BACKUP_DIR/SKILL.md"; fi
if [[ -f "$SUDOERS_PATH" ]]; then HAD_SUDOERS=1; install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$SUDOERS_PATH" "$BACKUP_DIR/sudoers"; fi

cat > "$TMP_DIR/sudoers" <<EOF
# DVIZH Hermes Autopilot v2.1: only two root-owned narrow gates.
$TARGET_USER ALL=(root) NOPASSWD: /usr/local/sbin/dvizhgitpush *
$TARGET_USER ALL=(root) NOPASSWD: /usr/local/sbin/dvizhrelease *
EOF
chmod 0440 "$TMP_DIR/sudoers"
visudo -cf "$TMP_DIR/sudoers" >/dev/null

if [[ -e "$KEY_PATH" || -e "$KEY_PATH.pub" ]]; then
  [[ -f "$KEY_PATH" && -f "$KEY_PATH.pub" && ! -L "$KEY_PATH" && ! -L "$KEY_PATH.pub" ]] || { echo "Небезопасное состояние root GitHub deploy key path." >&2; exit 1; }
else
  ssh-keygen -q -t ed25519 -f "$KEY_PATH" -C "dvizh-hermes-autopilot-root-gate" -N ""
  GENERATED_KEY=1
fi
chown root:root "$KEY_PATH" "$KEY_PATH.pub"
chmod 0600 "$KEY_PATH"
chmod 0644 "$KEY_PATH.pub"

LEGACY_KEY="$TARGET_HOME/.hermes/dev/dvizh/github/id_ed25519"
if [[ -e "$LEGACY_KEY" || -e "$LEGACY_KEY.pub" ]]; then
  echo "ВНИМАНИЕ: найден старый user-readable Autopilot key: $LEGACY_KEY" >&2
  echo "v2.1 его НЕ использует. Не добавляй его в GitHub; после проверки v2.1 его можно удалить." >&2
fi

INSTALLED=1
install -o root -g root -m 0755 "$TMP_DIR/dvizhautopilot" /usr/local/bin/dvizhautopilot
install -o root -g root -m 0755 "$TMP_DIR/dvizhrelease" /usr/local/sbin/dvizhrelease
install -o root -g root -m 0755 "$TMP_DIR/dvizhgitpush" /usr/local/sbin/dvizhgitpush
install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 0600 "$TMP_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
install -o root -g root -m 0440 "$TMP_DIR/sudoers" "$SUDOERS_PATH"
visudo -cf "$SUDOERS_PATH" >/dev/null

[[ "$(sudo -u "$TARGET_USER" /usr/local/bin/dvizhautopilot version)" == "2026.09.08-hermes-autopilot.2" ]]
sudo -u "$TARGET_USER" /usr/local/bin/dvizhdevctl config >/dev/null
sudo -u "$TARGET_USER" sudo -n /usr/local/sbin/dvizhrelease doctor >/dev/null
sudo -u "$TARGET_USER" sudo -n /usr/local/sbin/dvizhgitpush doctor > "$TMP_DIR/git-doctor.json" || true
grep -Fq '"key_present": true' "$TMP_DIR/git-doctor.json"
[[ "$(stat -c '%U:%G:%a' "$KEY_PATH")" == "root:root:600" ]]

INSTALLED=0
trap - EXIT INT TERM HUP
rm -rf -- "$TMP_DIR"

cat <<EOF
Hermes Autopilot v2.1 установлен: $VERSION
Payload: $PAYLOAD_REF
User: $TARGET_USER
Autopilot: /usr/local/bin/dvizhautopilot
Git push gate: /usr/local/sbin/dvizhgitpush
Release gate: /usr/local/sbin/dvizhrelease
Skill: $SKILL_DIR/SKILL.md
Sudoers: $SUDOERS_PATH
Backup: $BACKUP_DIR

Production-приложение не изменено. Установлена только dev/release инфраструктура.
Другой проект в репозитории защищён DVIZH-only path allowlist перед каждым push.
Приватный GitHub deploy key root:root 0600 и недоступен Hermes: $KEY_PATH
Произвольный sudo не выдавался.

ONE-TIME GITHUB SETUP REQUIRED
Добавь следующий PUBLIC deploy key в GitHub repo Itosyro/voice-bot → Settings → Deploy keys → Add deploy key.
Название: DVIZH Hermes Autopilot v2.1
Поставь галочку "Allow write access".
Добавляй ТОЛЬКО этот новый public key; никакой private key не копируй.

--- PUBLIC KEY START ---
$(cat "$KEY_PATH.pub")
--- PUBLIC KEY END ---

После добавления ключа в Telegram отправь Hermes:
  /reset
  Используй dvizh-dev. Запусти dvizhautopilot doctor и подтверди, что Autopilot v2.1 полностью готов, private_git_key_visible_to_hermes=false и friend project protected.
EOF
