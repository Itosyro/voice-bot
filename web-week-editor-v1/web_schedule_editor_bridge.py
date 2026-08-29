#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import logging
import os
import shlex
import signal
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VERSION = "2026.08.29-web-editor.1"
UTC = timezone.utc
LOG = logging.getLogger("dvizh.week.web.editor")
KINDS = {"work", "rest", "friend", "errand", "documents", "health", "gym", "volleyball", "other"}
REMINDERS = {0, 10, 30, 60, 120}
USER_ID_KEYS = ("DVIZH_WEB_USER_ID", "user_id", "userId", "web_user_id", "webUserId", "subject", "uid")
EMAIL_KEYS = ("DVIZH_WEB_USER_EMAIL", "email", "user_email", "userEmail")


class EditorError(RuntimeError):
    pass


class NotReady(EditorError):
    pass


class RevisionConflict(EditorError):
    pass


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str

    @property
    def masked(self) -> str:
        return hashlib.sha256(self.user_id.encode("utf-8")).hexdigest()[:10]


@dataclass(frozen=True)
class Config:
    telegram_db: str = "/var/lib/dvizh/telegram.db"
    web_api: str = "http://127.0.0.1:8000"
    bridge_env: str = "/etc/dvizh/bridge.env"
    identity_json: str = "/var/lib/dvizh/auth-identity.json"
    status_path: str = "/var/lib/dvizh/web-editor-status.json"
    interval_seconds: int = 5
    timeout_seconds: int = 8

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            telegram_db=os.environ.get("DVIZH_TELEGRAM_DB", cls.telegram_db),
            web_api=os.environ.get("DVIZH_WEB_API", cls.web_api).rstrip("/"),
            bridge_env=os.environ.get("DVIZH_BRIDGE_ENV", cls.bridge_env),
            identity_json=os.environ.get("DVIZH_AUTH_IDENTITY", cls.identity_json),
            status_path=os.environ.get("DVIZH_WEEK_EDITOR_STATUS", cls.status_path),
            interval_seconds=max(3, min(60, int(os.environ.get("DVIZH_WEEK_EDITOR_INTERVAL", "5")))),
            timeout_seconds=max(2, min(30, int(os.environ.get("DVIZH_WEEK_EDITOR_TIMEOUT", "8")))),
        )


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(UTC).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def recursive_value(payload: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
        for value in payload.values():
            found = recursive_value(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = recursive_value(value, keys)
            if found:
                return found
    return None


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        try:
            parsed = shlex.split(value.strip(), posix=True)
            result[key.strip()] = parsed[0] if parsed else ""
        except ValueError:
            result[key.strip()] = value.strip().strip('"\'')
    return result


def load_identity(config: Config) -> Identity:
    # The local login/password account is authoritative. bridge.env is only a
    # fallback for installations that pre-date the auth gateway.
    identity_path = Path(config.identity_json)
    if identity_path.is_file():
        try:
            payload = json.loads(identity_path.read_text(encoding="utf-8"))
            user_id = recursive_value(payload, USER_ID_KEYS) or ""
            email = recursive_value(payload, EMAIL_KEYS) or ""
            if user_id:
                return Identity(user_id, email or "local-account@dvizh.invalid")
        except Exception as exc:
            LOG.warning("cannot parse auth identity: %s", exc)
    env = parse_env(Path(config.bridge_env))
    user_id = (env.get("DVIZH_WEB_USER_ID") or "").strip()
    email = (env.get("DVIZH_WEB_USER_EMAIL") or "").strip()
    if not user_id:
        raise NotReady("stable DVIZH account identity is not ready")
    return Identity(user_id, email or "local-account@dvizh.invalid")


class WebClient:
    def __init__(self, config: Config, identity: Identity):
        self.base = config.web_api
        self.identity = identity
        self.timeout = config.timeout_seconds

    def request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = canonical(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/json",
            "User-Agent": f"DVIZH-WebEditor/{VERSION}",
            "X-ExeDev-UserID": self.identity.user_id,
            "X-ExeDev-Email": self.identity.email,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 409:
                raise RevisionConflict(detail) from exc
            raise EditorError(f"web API {method} {path}: HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise EditorError(f"web API unavailable: {exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise EditorError("web API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise EditorError("web API returned non-object JSON")
        return result

    def get_state(self) -> tuple[int, dict[str, Any]]:
        response = self.request("/api/state")
        state = response.get("state")
        if not isinstance(state, dict):
            raise EditorError("web state missing")
        return int(response.get("revision") or 0), state

    def put_state(self, revision: int, state: dict[str, Any]) -> int:
        response = self.request("/api/state", "PUT", {"baseRevision": revision, "state": state})
        if response.get("ok") is not True:
            raise EditorError(f"web state write refused: {response}")
        return int(response.get("revision") or revision + 1)



def connect_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def ensure_schema(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_web_commands(
          command_id TEXT PRIMARY KEY,
          chat_id INTEGER NOT NULL,
          action TEXT NOT NULL,
          result TEXT NOT NULL,
          detail TEXT,
          processed_at_utc TEXT NOT NULL
        )
        """
    )


def authorized_user(db: sqlite3.Connection) -> sqlite3.Row:
    rows = db.execute("SELECT * FROM users WHERE authorized=1 ORDER BY chat_id").fetchall()
    if len(rows) != 1:
        raise NotReady(f"expected one paired Telegram chat, found {len(rows)}")
    return rows[0]


def command_seen(db: sqlite3.Connection, command_id: str) -> bool:
    return db.execute("SELECT 1 FROM schedule_web_commands WHERE command_id=?", (command_id,)).fetchone() is not None


def remember_command(db: sqlite3.Connection, command_id: str, chat_id: int, action: str, result: str, detail: str = "") -> None:
    db.execute(
        "INSERT OR IGNORE INTO schedule_web_commands(command_id,chat_id,action,result,detail,processed_at_utc) VALUES(?,?,?,?,?,?)",
        (command_id, chat_id, action, result, detail[:500], iso()),
    )


def parse_hhmm(value: Any) -> str:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError("time must be HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("invalid time")
    return f"{hour:02d}:{minute:02d}"


def parse_item_id(raw: Any, chat_id: int) -> int:
    text = str(raw or "").strip()
    prefix = f"tg-schedule-item-{chat_id}-"
    if text.startswith(prefix):
        text = text[len(prefix):]
    item_id = int(text)
    if item_id <= 0:
        raise ValueError("invalid item id")
    return item_id


def normalized_payload(command: dict[str, Any]) -> dict[str, Any]:
    title = str(command.get("title") or "").strip()
    if not title or len(title) > 120:
        raise ValueError("title must be 1..120 chars")
    kind = str(command.get("kind") or "other")
    if kind not in KINDS:
        raise ValueError("invalid kind")
    recurrence = str(command.get("recurrence") or "once")
    if recurrence not in {"once", "weekly"}:
        raise ValueError("invalid recurrence")
    start_local = parse_hhmm(command.get("startLocal"))
    duration = int(command.get("durationMinutes") or 0)
    if not 5 <= duration <= 720:
        raise ValueError("duration must be 5..720")
    reminder = int(command.get("reminderMinutes") or 0)
    if reminder not in REMINDERS:
        raise ValueError("invalid reminder")
    date_local: str | None = None
    weekdays_mask: int | None = None
    if recurrence == "once":
        date_local = date.fromisoformat(str(command.get("dateLocal") or "")).isoformat()
    else:
        weekdays_mask = int(command.get("weekdaysMask") or 0)
        if not 1 <= weekdays_mask <= 127:
            raise ValueError("invalid weekdays")
    return {
        "title": title,
        "kind": kind,
        "recurrence": recurrence,
        "date_local": date_local,
        "weekdays_mask": weekdays_mask,
        "start_local": start_local,
        "duration_minutes": duration,
        "reminder_minutes": reminder,
    }


def mask_has_day(mask: int, day: int) -> bool:
    return bool(mask & (1 << day))


def local_to_utc(day: date, hhmm: str, timezone_name: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":", 1))
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(timezone_name))
    return local.astimezone(UTC)


def rebuild_pending(db: sqlite3.Connection, chat_id: int, item_id: int, timezone_name: str) -> int:
    item = db.execute("SELECT * FROM schedule_items WHERE id=? AND chat_id=?", (item_id, chat_id)).fetchone()
    if not item:
        return 0
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        timezone_name = "Europe/Moscow"
        tz = ZoneInfo(timezone_name)
    today = utcnow().astimezone(tz).date()
    db.execute(
        "DELETE FROM schedule_occurrences WHERE schedule_item_id=? AND chat_id=? AND status='pending'",
        (item_id, chat_id),
    )
    if not bool(item["enabled"]):
        return 0
    created = 0
    for offset in range(8):
        day = today + timedelta(days=offset)
        if item["recurrence"] == "once":
            if str(item["date_local"] or "") != day.isoformat():
                continue
        else:
            mask = int(item["weekdays_mask"] or 0)
            if not mask_has_day(mask, day.weekday()):
                continue
        start_at = local_to_utc(day, str(item["start_local"]), timezone_name)
        end_at = start_at + timedelta(minutes=int(item["duration_minutes"]))
        cur = db.execute(
            """
            INSERT OR IGNORE INTO schedule_occurrences(
              schedule_item_id,chat_id,due_date_local,title,kind,start_at_utc,end_at_utc,
              reminder_minutes,status,created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?, 'pending', ?)
            """,
            (
                item_id,
                chat_id,
                day.isoformat(),
                str(item["title"]),
                str(item["kind"]),
                iso(start_at),
                iso(end_at),
                int(item["reminder_minutes"]),
                iso(),
            ),
        )
        created += cur.rowcount
    return created


def apply_create(db: sqlite3.Connection, user: sqlite3.Row, command: dict[str, Any]) -> str:
    chat_id = int(user["chat_id"])
    payload = normalized_payload(command)
    now = iso()
    cur = db.execute(
        """
        INSERT INTO schedule_items(
          chat_id,title,kind,recurrence,date_local,weekdays_mask,start_local,
          duration_minutes,reminder_minutes,enabled,created_at_utc,updated_at_utc
        ) VALUES(?,?,?,?,?,?,?,?,?,1,?,?)
        """,
        (
            chat_id,
            payload["title"],
            payload["kind"],
            payload["recurrence"],
            payload["date_local"],
            payload["weekdays_mask"],
            payload["start_local"],
            payload["duration_minutes"],
            payload["reminder_minutes"],
            now,
            now,
        ),
    )
    item_id = int(cur.lastrowid)
    rebuild_pending(db, chat_id, item_id, str(user["timezone"] or "Europe/Moscow"))
    return f"created:{item_id}"


def apply_update(db: sqlite3.Connection, user: sqlite3.Row, command: dict[str, Any]) -> str:
    chat_id = int(user["chat_id"])
    item_id = parse_item_id(command.get("itemId"), chat_id)
    payload = normalized_payload(command)
    cur = db.execute(
        """
        UPDATE schedule_items
        SET title=?,kind=?,recurrence=?,date_local=?,weekdays_mask=?,start_local=?,
            duration_minutes=?,reminder_minutes=?,updated_at_utc=?
        WHERE id=? AND chat_id=?
        """,
        (
            payload["title"], payload["kind"], payload["recurrence"], payload["date_local"],
            payload["weekdays_mask"], payload["start_local"], payload["duration_minutes"],
            payload["reminder_minutes"], iso(), item_id, chat_id,
        ),
    )
    if not cur.rowcount:
        raise ValueError("schedule item not found")
    rebuild_pending(db, chat_id, item_id, str(user["timezone"] or "Europe/Moscow"))
    return f"updated:{item_id}"


def apply_enabled(db: sqlite3.Connection, user: sqlite3.Row, command: dict[str, Any]) -> str:
    chat_id = int(user["chat_id"])
    item_id = parse_item_id(command.get("itemId"), chat_id)
    enabled = bool(command.get("enabled"))
    cur = db.execute(
        "UPDATE schedule_items SET enabled=?,updated_at_utc=? WHERE id=? AND chat_id=?",
        (int(enabled), iso(), item_id, chat_id),
    )
    if not cur.rowcount:
        raise ValueError("schedule item not found")
    rebuild_pending(db, chat_id, item_id, str(user["timezone"] or "Europe/Moscow"))
    return f"enabled:{item_id}:{int(enabled)}"


def apply_delete(db: sqlite3.Connection, user: sqlite3.Row, command: dict[str, Any]) -> str:
    chat_id = int(user["chat_id"])
    item_id = parse_item_id(command.get("itemId"), chat_id)
    cur = db.execute("DELETE FROM schedule_items WHERE id=? AND chat_id=?", (item_id, chat_id))
    if not cur.rowcount:
        raise ValueError("schedule item not found")
    return f"deleted:{item_id}"


def apply_command(db: sqlite3.Connection, user: sqlite3.Row, command: dict[str, Any]) -> tuple[str, str]:
    command_id = str(command.get("id") or "").strip()
    if not command_id or len(command_id) > 160:
        raise ValueError("invalid command id")
    action = str(command.get("action") or "").strip()
    if command_seen(db, command_id):
        return command_id, "duplicate"
    handlers = {
        "create": apply_create,
        "update": apply_update,
        "set_enabled": apply_enabled,
        "delete": apply_delete,
    }
    if action not in handlers:
        raise ValueError("invalid action")
    chat_id = int(user["chat_id"])
    db.execute("SAVEPOINT web_schedule_command")
    try:
        detail = handlers[action](db, user, command)
        remember_command(db, command_id, chat_id, action, "ok", detail)
        db.execute("RELEASE SAVEPOINT web_schedule_command")
        return command_id, "ok"
    except Exception as exc:
        db.execute("ROLLBACK TO SAVEPOINT web_schedule_command")
        db.execute("RELEASE SAVEPOINT web_schedule_command")
        remember_command(db, command_id, chat_id, action or "invalid", "error", str(exc))
        return command_id, "error"


def extract_commands(state: dict[str, Any]) -> list[dict[str, Any]]:
    weekly = state.get("weeklySchedule")
    if not isinstance(weekly, dict):
        return []
    commands = weekly.get("webCommands")
    if not isinstance(commands, list):
        return []
    return [command for command in commands if isinstance(command, dict)]


def acknowledge_commands(client: WebClient, processed_ids: set[str]) -> int:
    if not processed_ids:
        return 0
    for attempt in range(1, 6):
        revision, state = client.get_state()
        weekly = state.get("weeklySchedule")
        if not isinstance(weekly, dict):
            return 0
        commands = weekly.get("webCommands")
        if not isinstance(commands, list):
            return 0
        remaining = [
            command for command in commands
            if not (isinstance(command, dict) and str(command.get("id") or "") in processed_ids)
        ]
        if len(remaining) == len(commands):
            return 0
        updated_state = json.loads(canonical(state))
        updated_week = dict(updated_state.get("weeklySchedule") or {})
        updated_week["webCommands"] = remaining
        updated_week["editorAckAt"] = iso()
        updated_state["weeklySchedule"] = updated_week
        try:
            client.put_state(revision, updated_state)
            return len(commands) - len(remaining)
        except RevisionConflict:
            time.sleep(0.15 * attempt)
    raise EditorError("could not acknowledge web commands after revision conflicts")


def write_status(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps({"version": VERSION, "at": iso(), **payload}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temp, 0o640)
    os.replace(temp, target)


def sync_once(config: Config) -> dict[str, Any]:
    identity = load_identity(config)
    client = WebClient(config, identity)
    _revision, state = client.get_state()
    commands = extract_commands(state)
    if not commands:
        return {"ok": True, "commands": 0, "applied": 0, "errors": 0, "acknowledged": 0, "webUser": identity.masked}

    applied = errors = duplicates = 0
    processed_ids: set[str] = set()
    with connect_db(config.telegram_db) as db:
        ensure_schema(db)
        user = authorized_user(db)
        for command in commands[:50]:
            command_id = str(command.get("id") or "").strip()
            if not command_id:
                continue
            try:
                processed_id, result = apply_command(db, user, command)
            except Exception as exc:
                LOG.exception("unexpected command failure")
                remember_command(db, command_id, int(user["chat_id"]), str(command.get("action") or "invalid"), "error", str(exc))
                processed_id, result = command_id, "error"
            processed_ids.add(processed_id)
            if result == "ok":
                applied += 1
            elif result == "duplicate":
                duplicates += 1
            else:
                errors += 1
        db.commit()

    acknowledged = acknowledge_commands(client, processed_ids)
    return {
        "ok": True,
        "commands": len(commands),
        "applied": applied,
        "duplicates": duplicates,
        "errors": errors,
        "acknowledged": acknowledged,
        "webUser": identity.masked,
    }


def run_loop(config: Config) -> int:
    stopped = False

    def stop_handler(_signum: int, _frame: Any) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    LOG.info("web schedule editor %s started", VERSION)
    while not stopped:
        try:
            result = sync_once(config)
            write_status(config.status_path, result)
            if result.get("commands"):
                LOG.info("commands=%s applied=%s errors=%s", result.get("commands"), result.get("applied"), result.get("errors"))
        except NotReady as exc:
            write_status(config.status_path, {"ok": False, "waiting": True, "error": str(exc)})
            LOG.warning("waiting: %s", exc)
        except Exception as exc:
            write_status(config.status_path, {"ok": False, "waiting": False, "error": str(exc)})
            LOG.exception("editor sync failed")
        for _ in range(config.interval_seconds):
            if stopped:
                break
            time.sleep(1)
    return 0


def main() -> int:
    logging.basicConfig(level=os.environ.get("DVIZH_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run_loop(Config.from_env())


if __name__ == "__main__":
    raise SystemExit(main())
