#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-ai-home-v2-routing-diagnostic.1"
TEST_ROOT="${DVIZH_AI_HOME_V2_ROOT:-}"
BASE_URL="${DVIZH_AI_HOME_V2_ROUTE_BASE_URL:-http://127.0.0.1:8000}"

[[ $# -eq 0 ]] || { echo "Диагностика не принимает аргументы." >&2; exit 1; }
if [[ -n "${DVIZH_AI_HOME_V2_ROUTE_BASE_URL:-}" && -z "$TEST_ROOT" ]]; then
  echo "Переопределение HTTP origin разрешено только в тестовом root." >&2
  exit 1
fi
for tool in curl sha256sum cmp grep awk; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

if [[ -n "$TEST_ROOT" ]]; then
  APP_ROOT="$TEST_ROOT"
elif [[ -f /opt/dvizh/static/index.html ]]; then
  APP_ROOT=/opt/dvizh/static
elif [[ -f /opt/dvizh/index.html ]]; then
  APP_ROOT=/opt/dvizh
else
  echo "Не найден веб-интерфейс ДВИЖа." >&2
  exit 1
fi
APP_ROOT="$(cd -- "$APP_ROOT" && pwd -P)"

for name in index.html app.js styles.css sw.js ai-home-v2-preview.html ai-home-v2.js ai-home-v2.css; do
  [[ -f "$APP_ROOT/$name" && ! -L "$APP_ROOT/$name" ]] || {
    echo "Нет ожидаемого обычного файла: $APP_ROOT/$name" >&2
    exit 1
  }
done

TMP_DIR="$(mktemp -d /tmp/dvizh-ai-home-v2-route-probe.XXXXXX)"
cleanup() { rm -rf -- "$TMP_DIR"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

snapshot_known() {
  for name in index.html app.js styles.css sw.js ai-home-v2-preview.html ai-home-v2.js ai-home-v2.css manual.html; do
    if [[ -f "$APP_ROOT/$name" ]]; then
      sha256sum "$APP_ROOT/$name"
    else
      printf 'ABSENT  %s\n' "$APP_ROOT/$name"
    fi
  done
}
snapshot_known > "$TMP_DIR/before.sha"

stamp="$(date +%s)"
http_get() {
  local label="$1" path="$2"
  local body="$TMP_DIR/$label.body" headers="$TMP_DIR/$label.headers" code
  code="$(curl --silent --show-error --location --max-time 8 \
    -H 'Cache-Control: no-cache' -D "$headers" -o "$body" -w '%{http_code}' \
    "$BASE_URL$path")" || {
      echo "HTTP $label: curl failed for $path" >&2
      return 1
    }
  printf '%s\n' "$code" > "$TMP_DIR/$label.code"
  printf 'HTTP %-8s code=%s bytes=%s sha256=%s\n' \
    "$label" "$code" "$(wc -c < "$body")" "$(sha256sum "$body" | awk '{print $1}')"
  awk 'BEGIN{IGNORECASE=1} /^content-type:|^location:|^cache-control:|^etag:/{gsub(/\r$/,""); print "  " $0}' "$headers" || true
  if grep -Fq '/ai-home-v2.js' "$body"; then echo '  marker=AI_HOME_V2'; fi
  if grep -Eq "(src|href)=[\"'](\\./|/)?app\\.js" "$body"; then echo '  marker=MANUAL_APP_JS'; fi
}

printf '=== DVIZH AI Home v2 routing diagnostic ===\n'
printf 'version=%s\napp_root=%s\nbase_url=%s\n' "$VERSION" "$APP_ROOT" "$BASE_URL"
printf 'manual_file=%s\n' "$([[ -f "$APP_ROOT/manual.html" ]] && echo present || echo absent)"
printf '\n--- services (read-only) ---\n'
if [[ -z "$TEST_ROOT" ]]; then
  for unit in dvizh.service dvizh-auth.service dvizh-ai-home.service; do
    printf '%-24s ' "$unit"
    systemctl is-active "$unit" 2>/dev/null || true
  done
fi

printf '\n--- live HTTP bodies ---\n'
http_get root "/?_dvizh_ai_home_route_probe=$stamp"
http_get index "/index.html?_dvizh_ai_home_route_probe=$stamp"
http_get preview "/ai-home-v2-preview.html?_dvizh_ai_home_route_probe=$stamp"
http_get manual "/manual.html?_dvizh_ai_home_route_probe=$stamp"

printf '\n--- file vs HTTP relation ---\n'
relation() {
  local file="$1" body="$2" label="$3"
  if [[ ! -f "$file" ]]; then
    printf '%-28s local=ABSENT\n' "$label"
  elif cmp -s "$file" "$body"; then
    printf '%-28s MATCH\n' "$label"
  else
    printf '%-28s DIFFERENT\n' "$label"
  fi
}
relation "$APP_ROOT/index.html" "$TMP_DIR/root.body" 'index.html <-> GET /'
relation "$APP_ROOT/index.html" "$TMP_DIR/index.body" 'index.html <-> GET /index'
relation "$APP_ROOT/ai-home-v2-preview.html" "$TMP_DIR/preview.body" 'preview file <-> GET preview'
relation "$APP_ROOT/manual.html" "$TMP_DIR/manual.body" 'manual file <-> GET manual'

if [[ ! -f "$APP_ROOT/manual.html" ]]; then
  if cmp -s "$APP_ROOT/index.html" "$TMP_DIR/manual.body"; then
    echo 'manual_absent_http_relation=FALLBACK_TO_ROOT_INDEX'
  elif cmp -s "$APP_ROOT/ai-home-v2-preview.html" "$TMP_DIR/manual.body"; then
    echo 'manual_absent_http_relation=FALLBACK_TO_PREVIEW'
  else
    echo 'manual_absent_http_relation=OTHER_RESPONSE'
  fi
fi

snapshot_known > "$TMP_DIR/after.sha"
cmp -s "$TMP_DIR/before.sha" "$TMP_DIR/after.sha" || {
  echo "ОШИБКА: во время read-only диагностики изменилось содержимое известного файла сайта." >&2
  diff -u "$TMP_DIR/before.sha" "$TMP_DIR/after.sha" || true
  exit 2
}

printf '\nRESULT: read-only probe complete; site files unchanged.\n'
