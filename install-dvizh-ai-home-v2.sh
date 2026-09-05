#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.05-ai-home-v2.3"
# An explicitly supplied legacy mode is still supported; an unqualified run is read-only.
MODE="${DVIZH_AI_HOME_V2_MODE:-check}"
[[ $# -le 1 ]] || { echo "Ожидается не более одного аргумента." >&2; exit 1; }
case "${1:-}" in
  '') ;;
  --check) MODE=check ;;
  --install-preview) MODE=preview ;;
  --promote) MODE=promote ;;
  --help)
    echo "Без аргументов: проверка. --install-preview: /ai-home-v2-preview.html без замены /."
    echo "--promote: отдельный явный этап, только после проверки установленного preview на устройстве."
    echo "Нужен локальный проверенный checkout. curl | bash не поддерживается."
    exit 0 ;;
  *) echo "Неизвестный аргумент: $1" >&2; exit 1 ;;
esac
case "$MODE" in check|preview|promote) ;; *) echo "Недопустимый режим: $MODE" >&2; exit 1 ;; esac
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="${DVIZH_AI_HOME_V2_SOURCE_DIR:-$SCRIPT_DIR/ai-home-v2}"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"
if [[ -n "$TEST_ROOT" ]]; then APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/index.html ]]; then APP_ROOT=/opt/dvizh/static
elif [[ -f /opt/dvizh/index.html ]]; then APP_ROOT=/opt/dvizh
else echo "Не найден веб-интерфейс ДВИЖа." >&2; exit 1
fi
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"
if [[ -z "$TEST_ROOT" && "$MODE" != check && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Для записи нужен root; проверку можно запустить без sudo." >&2; exit 1
fi
# Directory lock creates no public file. Hold it throughout validation and writing.
exec 9< "$APP_ROOT"
flock -n 9 || { echo "Другая установка AI Home v2 уже выполняется." >&2; exit 1; }
for name in index.html app.js styles.css sw.js; do
  [[ -f "$APP_ROOT/$name" && ! -L "$APP_ROOT/$name" ]] || { echo "Нет обычного файла: $name" >&2; exit 1; }
done
for name in manual.html ai-home-v2-preview.html ai-home-v2.js ai-home-v2.css; do
  if [[ -L "$APP_ROOT/$name" || ( -e "$APP_ROOT/$name" && ! -f "$APP_ROOT/$name" ) ]]; then
    echo "Небезопасный путь: $name" >&2; exit 1
  fi
done
PROMOTED=0
if grep -q 'ai-home-v2.js' "$APP_ROOT/index.html"; then
  PROMOTED=1
  [[ -s "$APP_ROOT/manual.html" ]] || { echo "Главная уже AI Home, но manual.html отсутствует." >&2; exit 1; }
fi
readonly_files=(app.js styles.css sw.js)
[[ "$MODE" == promote ]] || readonly_files+=(index.html)
[[ ! -f "$APP_ROOT/manual.html" ]] || readonly_files+=(manual.html)
TMP_DIR="$(mktemp -d)"
STAGE=""; BACKUP_DIR=""; WRITING=0; SUCCESS=0
targets=(ai-home-v2.js ai-home-v2.css ai-home-v2-preview.html)
if [[ "$MODE" == promote ]]; then
  targets=(index.html)
  [[ -f "$APP_ROOT/manual.html" ]] || targets=(manual.html index.html)
fi
cleanup() {
  local code=$? failed=0
  trap - EXIT
  if [[ "$WRITING" == 1 && "$SUCCESS" != 1 ]]; then
    echo "Сбой записи: возвращаю изменяемые файлы из $BACKUP_DIR." >&2
    for name in "${targets[@]}"; do
      if [[ -f "$BACKUP_DIR/$name" ]]; then cp -a -- "$BACKUP_DIR/$name" "$APP_ROOT/$name" || failed=1
      else rm -f -- "$APP_ROOT/$name" || failed=1; fi
    done
    [[ "$failed" == 0 ]] || echo "ВНИМАНИЕ: откат неполный; проверь backup вручную." >&2
  fi
  [[ -z "$STAGE" ]] || rm -rf -- "$STAGE"
  rm -rf -- "$TMP_DIR"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
for name in index.html ai-home-v2.js ai-home-v2.css; do
  [[ -f "$SOURCE_DIR/$name" && ! -L "$SOURCE_DIR/$name" ]] || { echo "Нет локального payload: $SOURCE_DIR/$name. Нужен проверенный checkout." >&2; exit 1; }
  cp -- "$SOURCE_DIR/$name" "$TMP_DIR/$name"
done
grep -Fq '/ai-home-v2.js?v=20260905-3' "$TMP_DIR/index.html"
grep -Fq '/ai-home-v2.css?v=20260905-3' "$TMP_DIR/index.html"
grep -Fq "const API = '/api/state';" "$TMP_DIR/ai-home-v2.js"
grep -Fq 'location.assign(manualTarget())' "$TMP_DIR/ai-home-v2.js"
if grep -Eq 'MutationObserver|setInterval[[:space:]]*\(|serviceWorker|caches[[:space:]]*\.' "$TMP_DIR/ai-home-v2.js"; then
  echo "Payload нарушает изоляцию страницы." >&2; exit 1
fi
if grep -Eq "(src|href)=[\"']/?(app\\.js|styles\\.css)" "$TMP_DIR/index.html"; then
  echo "Preview подключает старый интерфейс." >&2; exit 1
fi
if command -v node >/dev/null 2>&1; then node --check "$TMP_DIR/ai-home-v2.js"; fi
if [[ -z "$TEST_ROOT" ]]; then
  for unit in dvizh.service dvizh-auth.service dvizh-ai-home.service; do
    systemctl is-active --quiet "$unit" || { echo "$unit не активен" >&2; exit 1; }
  done
  curl -fsS --max-time 8 http://127.0.0.1:8000/api/health >/dev/null
fi
if [[ "$MODE" == check ]]; then
  echo "Проверка пройдена: $VERSION. Файлы сайта НЕ изменены."
  echo "Следующий отдельный этап: --install-preview. Это не подтверждение работоспособности Hermes или телефона."
  exit 0
fi
if [[ "$MODE" == preview && "$PROMOTED" == 1 ]]; then
  echo "Главная уже использует общие AI-assets. Preview мог бы её изменить; остановка." >&2; exit 1
fi
if [[ "$MODE" == promote ]]; then
  # Preserve explicit promotion from v2.2, but never promote an uninstalled/different payload.
  cmp -s "$TMP_DIR/index.html" "$APP_ROOT/ai-home-v2-preview.html" || { echo "Сначала установи и проверь именно этот preview." >&2; exit 1; }
  for name in ai-home-v2.js ai-home-v2.css; do
    cmp -s "$TMP_DIR/$name" "$APP_ROOT/$name" || { echo "Preview-assets отличаются: $name" >&2; exit 1; }
    readonly_files+=("$name")
  done
  readonly_files+=(ai-home-v2-preview.html)
  if [[ "$PROMOTED" == 0 && -f "$APP_ROOT/manual.html" ]]; then
    cmp -s "$APP_ROOT/index.html" "$APP_ROOT/manual.html" || { echo "manual.html отличается от стабильной главной; автоматическая перезапись запрещена." >&2; exit 1; }
  fi
  if [[ -f "$APP_ROOT/manual.html" ]] && grep -q 'ai-home-v2.js' "$APP_ROOT/manual.html"; then
    echo "manual.html не является ручным интерфейсом." >&2; exit 1
  fi
fi
for name in "${readonly_files[@]}"; do sha256sum "$APP_ROOT/$name"; done > "$TMP_DIR/readonly.sha256"
if [[ -n "$TEST_ROOT" ]]; then
  BACKUP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dvizh-ai-home-v2-backup.XXXXXX")"
else
  install -d -m 0700 /var/lib/dvizh/backups
  BACKUP_DIR="$(mktemp -d "/var/lib/dvizh/backups/ai-home-v2-${MODE}.XXXXXX")"
fi
for name in "${targets[@]}"; do
  [[ ! -f "$APP_ROOT/$name" ]] || cp -a -- "$APP_ROOT/$name" "$BACKUP_DIR/$name"
done
STAGE="$(mktemp -d "$APP_ROOT/.ai-home-v2-stage.XXXXXX")"
if [[ "$MODE" == preview ]]; then
  install -m 0644 "$TMP_DIR/ai-home-v2.js" "$STAGE/ai-home-v2.js"
  install -m 0644 "$TMP_DIR/ai-home-v2.css" "$STAGE/ai-home-v2.css"
  install -m 0644 "$TMP_DIR/index.html" "$STAGE/ai-home-v2-preview.html"
else
  [[ -f "$APP_ROOT/manual.html" ]] || install -m 0644 "$APP_ROOT/index.html" "$STAGE/manual.html"
  install -m 0644 "$TMP_DIR/index.html" "$STAGE/index.html"
fi
WRITING=1
# Replace each file atomically on the same filesystem; publish the document last.
for name in "${targets[@]}"; do mv -f -- "$STAGE/$name" "$APP_ROOT/$name"; done
sha256sum --check --status "$TMP_DIR/readonly.sha256"
if [[ "$MODE" == preview ]]; then cmp -s "$TMP_DIR/index.html" "$APP_ROOT/ai-home-v2-preview.html"
else cmp -s "$TMP_DIR/index.html" "$APP_ROOT/index.html"; fi
SUCCESS=1
echo "Установлен режим $MODE: $VERSION. Backup: $BACKUP_DIR"
if [[ "$MODE" == preview ]]; then
  echo "Preview: /ai-home-v2-preview.html. Ручной режим: /. Главная и manual.html не изменены."
else echo "Явный перенос завершён: AI на /, ручной интерфейс на /manual.html."
fi
echo "app.js, styles.css, sw.js, БД и Hermes не изменены; сервисы не перезапускались."
