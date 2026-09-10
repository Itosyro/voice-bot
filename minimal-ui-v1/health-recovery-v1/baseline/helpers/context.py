#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VERSION = "2026.09.05-hermes-context.1"
DB_PATH = Path("/var/lib/dvizh/telegram.db")
IDENTITY_PATH = Path("/var/lib/dvizh/auth-identity.json")
WEB_API = "http://127.0.0.1:8000"
STATUS_FILES = {
    "bridge": Path("/var/lib/dvizh/bridge-status.json"),
    "week": Path("/var/lib/dvizh/web-week-status.json"),
    "editor": Path("/var/lib/dvizh/web-editor-status.json"),
    "training": Path("/var/lib/dvizh/training-status.json"),
    "jump": Path("/var/lib/dvizh/jump-status.json"),
    "social": Path("/var/lib/dvizh/social-status.json"),
}
ALLOWED_VIEWS = {"today", "week", "training", "jump", "social", "full", "health"}
SENSITIVE_FRAGMENTS = (
    "token", "password", "passwd", "secret", "api_key", "apikey",
    "cookie", "authorization", "credential", "bearer", "session_key",
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS)


def sanitize(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED_DEPTH]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if is_sensitive_key(key):
                out[key] = "[REDACTED]"
            else:
                out[key] = sanitize(raw_value, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize(item, depth=depth + 1) for item in value[:120]]
    if isinstance(value, str):
        if len(value) > 4000:
            return value[:4000] + "…[TRUNCATED]"
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[:1] in "[{" and stripped[-1:] in "]}":
            try:
                decoded = json.loads(stripped)
            except Exception:
                return value
            return sanitize(decoded, depth=depth + 1)
        return value
    return value


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def identity() -> tuple[str, str] | None:
    data = read_json(IDENTITY_PATH)
    if not data:
        return None
    user_id = str(data.get("user_id") or data.get("userId") or data.get("id") or "").strip()
    email = str(data.get("email") or "telegram@dvizh.local").strip()
    return (user_id, email) if user_id else None


def web_state() -> dict[str, Any]:
    ident = identity()
    if not ident:
        return {"ok": False, "error": "auth identity unavailable"}
    user_id, email = ident
    request = urllib.request.Request(
        WEB_API + "/api/state",
        headers={
            "Accept": "application/json",
            "User-Agent": f"DVIZH-Hermes-Context/{VERSION}",
            "X-ExeDev-UserID": user_id,
            "X-ExeDev-Email": email,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            raw = response.read()
            status = int(response.status)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"web state unavailable: {type(exc).__name__}"}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"ok": False, "error": f"web state invalid JSON (http={status})"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "web state payload is not an object"}
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    return {
        "ok": True,
        "revision": payload.get("revision"),
        "state": sanitize(state),
    }


def open_db() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    try:
        db = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=4)
    except sqlite3.Error:
        return None
    db.row_factory = sqlite3.Row
    return db


def table_columns(db: sqlite3.Connection, table: str) -> list[str]:
    safe = table.replace('"', '""')
    return [str(row[1]) for row in db.execute(f'PRAGMA table_info("{safe}")').fetchall()]


def table_names(db: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def authorized_user(db: sqlite3.Connection) -> tuple[int | None, str]:
    tables = table_names(db)
    if "users" not in tables:
        return None, "Europe/Moscow"
    columns = table_columns(db, "users")
    if "chat_id" not in columns:
        return None, "Europe/Moscow"
    where = " WHERE authorized=1" if "authorized" in columns else ""
    rows = db.execute(f"SELECT * FROM users{where} ORDER BY chat_id LIMIT 2").fetchall()
    if len(rows) != 1:
        return None, "Europe/Moscow"
    row = rows[0]
    timezone_name = str(row["timezone"] or "Europe/Moscow") if "timezone" in columns else "Europe/Moscow"
    return int(row["chat_id"]), timezone_name


def normalize_row(row: sqlite3.Row) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in row.keys():
        if is_sensitive_key(str(key)):
            result[str(key)] = "[REDACTED]"
            continue
        value = row[key]
        if isinstance(value, str) and str(key).lower().endswith("_json"):
            try:
                value = json.loads(value)
            except Exception:
                pass
        result[str(key)] = sanitize(value)
    return result


def fetch_rows(
    db: sqlite3.Connection,
    table: str,
    *,
    chat_id: int | None,
    limit: int = 30,
    ascending: bool = False,
) -> list[dict[str, Any]]:
    tables = table_names(db)
    if table not in tables:
        return []
    columns = table_columns(db, table)
    where = ""
    params: list[Any] = []
    if chat_id is not None and "chat_id" in columns:
        where = " WHERE chat_id=?"
        params.append(chat_id)
    candidates = (
        "due_date_local", "local_date", "planned_date_local", "updated_at_utc",
        "created_at_utc", "start_at_utc", "id",
    )
    order_col = next((name for name in candidates if name in columns), None)
    direction = "ASC" if ascending else "DESC"
    safe = table.replace('"', '""')
    sql = f'SELECT * FROM "{safe}"{where}'
    if order_col:
        sql += f' ORDER BY "{order_col}" {direction}'
        if "id" in columns and order_col != "id":
            sql += ", id " + direction
    sql += " LIMIT ?"
    params.append(max(1, min(120, limit)))
    try:
        rows = db.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    return [normalize_row(row) for row in rows]


def prefixed_tables(db: sqlite3.Connection, prefix: str, *, exclude: tuple[str, ...] = ()) -> list[str]:
    return sorted(
        table for table in table_names(db)
        if table.startswith(prefix) and not any(token in table for token in exclude)
    )


def selected_web_state(state: dict[str, Any], view: str, today_key: str) -> dict[str, Any]:
    if view == "full":
        return state
    selected: dict[str, Any] = {}
    core = {"tasks", "checkins", "plans", "sessions", "proofs", "ladder"}
    domain_words = {
        "today": ("today", "current", "schedule", "week", "training", "jump", "social"),
        "week": ("week", "schedule", "training", "social", "jump"),
        "training": ("training", "readiness", "schedule"),
        "jump": ("jump", "training"),
        "social": ("social", "schedule"),
        "health": ("checkin", "training", "readiness"),
    }[view]
    for key, value in state.items():
        lowered = str(key).lower()
        if key in core or any(word in lowered for word in domain_words):
            if key == "checkins" and isinstance(value, dict):
                selected[key] = {today_key: value.get(today_key)} if today_key in value else {}
            else:
                selected[key] = value
    return selected


def status_snapshot(view: str) -> dict[str, Any]:
    wanted = {
        "today": {"bridge", "week", "training", "jump", "social"},
        "week": {"week", "editor", "training"},
        "training": {"training"},
        "jump": {"jump", "training"},
        "social": {"social"},
        "health": {"bridge", "week", "editor", "training", "jump", "social"},
        "full": set(STATUS_FILES),
    }[view]
    out: dict[str, Any] = {}
    for name in sorted(wanted):
        data = read_json(STATUS_FILES[name])
        if data is not None:
            out[name] = sanitize(data)
    return out


def database_snapshot(view: str) -> dict[str, Any]:
    db = open_db()
    if db is None:
        return {"ok": False, "error": "telegram database unavailable"}
    try:
        chat_id, timezone_name = authorized_user(db)
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            timezone_name = "Europe/Moscow"
            tz = ZoneInfo(timezone_name)
        today_key = datetime.now(tz=timezone.utc).astimezone(tz).date().isoformat()
        result: dict[str, Any] = {
            "ok": True,
            "timezone": timezone_name,
            "today": today_key,
        }
        tables: dict[str, Any] = {}
        if view in {"today", "week", "full"}:
            tables["schedule_items"] = fetch_rows(db, "schedule_items", chat_id=chat_id, limit=40, ascending=True)
            tables["schedule_occurrences"] = fetch_rows(db, "schedule_occurrences", chat_id=chat_id, limit=80, ascending=True)
        if view in {"today", "training", "full", "health"}:
            for table in prefixed_tables(db, "training_", exclude=("web_commands", "notifications")):
                tables[table] = fetch_rows(db, table, chat_id=chat_id, limit=35)
        if view in {"jump", "full"}:
            for table in prefixed_tables(db, "jump_", exclude=("web_commands", "notifications")):
                tables[table] = fetch_rows(db, table, chat_id=chat_id, limit=40)
        if view in {"social", "full"}:
            for table in prefixed_tables(db, "social_", exclude=("web_commands", "notifications")):
                tables[table] = fetch_rows(db, table, chat_id=chat_id, limit=40)
        if view in {"today", "health", "full"}:
            for table in ("checkins", "occurrences"):
                rows = fetch_rows(db, table, chat_id=chat_id, limit=30)
                if rows:
                    tables[table] = rows
        result["tables"] = tables
        return result
    finally:
        db.close()


def build(view: str) -> dict[str, Any]:
    db_snapshot = database_snapshot(view)
    timezone_name = str(db_snapshot.get("timezone") or "Europe/Moscow")
    today_key = str(db_snapshot.get("today") or datetime.now().date().isoformat())
    web = web_state()
    web_out: dict[str, Any]
    if web.get("ok") and isinstance(web.get("state"), dict):
        web_out = {
            "ok": True,
            "revision": web.get("revision"),
            "state": selected_web_state(web["state"], view, today_key),
        }
    else:
        web_out = web
    return {
        "version": VERSION,
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "view": view,
        "timezone": timezone_name,
        "today": today_key,
        "web": web_out,
        "telegram": db_snapshot,
        "statuses": status_snapshot(view),
        "read_only": True,
    }


def main() -> int:
    view = (sys.argv[1] if len(sys.argv) > 1 else "today").strip().lower()
    if view not in ALLOWED_VIEWS:
        print("allowed views: " + ", ".join(sorted(ALLOWED_VIEWS)), file=sys.stderr)
        return 2
    print(json.dumps(build(view), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
