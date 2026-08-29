#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_TITLE="${1:-Проверка связи}"
WEB_DB="/var/lib/dvizh/dvizh.db"
BRIDGE_ENV="/etc/dvizh/bridge.env"
BRIDGE_SCRIPT="/opt/dvizh-integration/bridge.py"
STATUS_FILE="/var/lib/dvizh/bridge-status.json"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ENV_BACKUP="${BRIDGE_ENV}.before-user-pin-${STAMP}"
SUCCESS=0

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  exec sudo -n "$0" "$@"
fi

cleanup_on_error() {
  local code=$?
  if [[ "$SUCCESS" -eq 1 ]]; then
    return 0
  fi
  echo "Не удалось закрепить пользователя. Возвращаю прежнюю конфигурацию моста..." >&2
  if [[ -f "$ENV_BACKUP" ]]; then
    cp -a "$ENV_BACKUP" "$BRIDGE_ENV"
  fi
  systemctl restart dvizh-bridge.service >/dev/null 2>&1 || true
  exit "$code"
}
trap cleanup_on_error ERR INT TERM

for required in "$WEB_DB" "$BRIDGE_ENV" "$BRIDGE_SCRIPT"; do
  if [[ ! -f "$required" ]]; then
    echo "Не найден обязательный файл: $required" >&2
    exit 1
  fi
done

cp -a "$BRIDGE_ENV" "$ENV_BACKUP"
systemctl stop dvizh-bridge.service

python3 - "$WEB_DB" "$BRIDGE_ENV" "$BRIDGE_SCRIPT" "$TARGET_TITLE" <<'PY'
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

web_db = Path(sys.argv[1])
env_path = Path(sys.argv[2])
bridge_path = Path(sys.argv[3])
target = sys.argv[4].strip().casefold()

spec = importlib.util.spec_from_file_location("dvizh_bridge_runtime", bridge_path)
if spec is None or spec.loader is None:
    raise SystemExit("Не удалось загрузить bridge.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


def row_updated(row: sqlite3.Row) -> datetime:
    pair = bridge._column_value(row, bridge.UPDATED_COLUMN_RANK)
    parsed = bridge.parse_datetime(pair[1]) if pair else None
    return parsed or datetime(1970, 1, 1, tzinfo=timezone.utc)


def identity_from_row(row: sqlite3.Row, columns: list[str], state_column: str):
    user_pair = bridge._column_value(row, bridge.USER_COLUMN_RANK)
    if user_pair is None:
        for column in columns:
            value = row[column]
            lowered = column.lower()
            if column == state_column or value in (None, ""):
                continue
            if any(token in lowered for token in ("revision", "updated", "created", "email", "state", "payload")):
                continue
            if isinstance(value, str) and 1 <= len(value) <= 512:
                user_pair = (column, value)
                break
    if user_pair is None:
        return None
    email_pair = bridge._column_value(row, bridge.EMAIL_COLUMN_RANK)
    return str(user_pair[1]), str(email_pair[1]) if email_pair else "telegram@dvizh.local"


all_users: dict[str, dict] = {}
matches: dict[str, dict] = {}
with sqlite3.connect(f"file:{web_db}?mode=ro", uri=True, timeout=5) as db:
    db.row_factory = sqlite3.Row
    tables = [
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    for table in tables:
        columns = [row[1] for row in db.execute(f"PRAGMA table_info({bridge.quote_ident(table)})")]
        if not columns:
            continue
        lower = {name.lower(): name for name in columns}
        likely_state_columns = [lower[name] for name in bridge.STATE_COLUMN_RANK if name in lower]
        scan_columns = likely_state_columns or columns
        try:
            rows = db.execute(f"SELECT * FROM {bridge.quote_ident(table)} ORDER BY rowid DESC LIMIT 500").fetchall()
        except sqlite3.Error:
            rows = db.execute(f"SELECT * FROM {bridge.quote_ident(table)} LIMIT 500").fetchall()
        for row in rows:
            state = None
            state_column = None
            for column in scan_columns:
                decoded = bridge._decode_state(row[column])
                if decoded is not None:
                    state = decoded
                    state_column = column
                    break
            if state is None or state_column is None:
                continue
            identity = identity_from_row(row, columns, state_column)
            if identity is None:
                continue
            user_id, email = identity
            titles = [
                str(item.get("title", "")).strip()
                for item in state.get("tasks", [])
                if isinstance(item, dict)
            ]
            record = {
                "user_id": user_id,
                "email": email,
                "updated": row_updated(row),
                "titles": titles,
                "table": table,
            }
            previous = all_users.get(user_id)
            if previous is None or record["updated"] > previous["updated"]:
                all_users[user_id] = record
            if any(title.casefold() == target for title in titles):
                previous = matches.get(user_id)
                if previous is None or record["updated"] > previous["updated"]:
                    matches[user_id] = record

if len(matches) != 1:
    print(f"Не найден ровно один веб-пользователь с задачей «{sys.argv[4]}».", file=sys.stderr)
    print("Безопасный список кандидатов:", file=sys.stderr)
    for user_id, record in sorted(all_users.items(), key=lambda item: item[1]["updated"], reverse=True):
        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8]
        preview = ", ".join(record["titles"][-4:]) or "без задач"
        print(
            f"  {digest} updated={record['updated'].isoformat()} tasks={len(record['titles'])}: {preview}",
            file=sys.stderr,
        )
    raise SystemExit(2)

record = next(iter(matches.values()))
user_id = record["user_id"]
email = record["email"]


def quote_env(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise SystemExit("Недопустимый перевод строки в идентификаторе")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

lines = env_path.read_text(encoding="utf-8").splitlines()
lines = [
    line
    for line in lines
    if not line.startswith("DVIZH_WEB_USER_ID=") and not line.startswith("DVIZH_WEB_USER_EMAIL=")
]
lines.append(f"DVIZH_WEB_USER_ID={quote_env(user_id)}")
lines.append(f"DVIZH_WEB_USER_EMAIL={quote_env(email)}")
tmp = env_path.with_suffix(env_path.suffix + ".tmp")
tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.chmod(tmp, 0o640)
os.replace(tmp, env_path)

digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:8]
print(f"Выбран веб-пользователь: {digest}")
print(f"Найдена задача: {sys.argv[4]}")
PY

chown root:dvizh "$BRIDGE_ENV"
chmod 0640 "$BRIDGE_ENV"
systemctl start dvizh-bridge.service
systemctl is-active --quiet dvizh-bridge.service

for _ in $(seq 1 30); do
  if [[ -f "$STATUS_FILE" ]] && python3 - "$STATUS_FILE" <<'PY' >/dev/null 2>&1
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
raise SystemExit(0 if payload.get("ok") else 1)
PY
  then
    break
  fi
  sleep 1
done

if ! python3 - "$STATUS_FILE" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0 if payload.get("ok") else 1)
PY
then
  echo "Мост не вышел в состояние ok после выбора пользователя." >&2
  journalctl -u dvizh-bridge.service -n 30 --no-pager >&2 || true
  exit 1
fi

SUCCESS=1
trap - ERR INT TERM

echo
echo "Готово: Telegram привязан к нужному веб-пользователю."
echo "Резервная копия конфигурации: $ENV_BACKUP"
echo "Теперь обнови веб-ДВИЖ и открой в боте: ⚙️ Настройки."
