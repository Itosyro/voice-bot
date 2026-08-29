#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

APP_VERSION = "2026.08.29-bridge.1"
UTC = timezone.utc
LOG = logging.getLogger("dvizh.bridge")

AREA_MAP = {
    "pdd": "ПДД",
    "cafe": "Кафе",
    "volleyball": "Волейбол",
    "social": "Соцсети",
    "recovery": "Восстановление",
    "other": "Разное",
}
STATE_HINT_KEYS = {"tasks", "sessions", "proofs", "checkins", "plans", "ladder"}
USER_COLUMN_RANK = (
    "user_id",
    "user_key",
    "external_user_id",
    "exedev_user_id",
    "subject",
    "owner_id",
    "identity",
    "user",
)
EMAIL_COLUMN_RANK = ("email", "user_email", "owner_email")
STATE_COLUMN_RANK = ("state_json", "state", "payload_json", "payload", "data_json", "data")
UPDATED_COLUMN_RANK = ("updated_at", "updated_at_utc", "modified_at", "created_at")


class BridgeError(RuntimeError):
    pass


class IdentityNotReady(BridgeError):
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
    telegram_db: str
    web_db: str
    web_api: str
    web_user_id: str
    web_user_email: str
    interval_seconds: int
    lookback_days: int
    status_path: str
    sync_signal_path: str
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            telegram_db=os.environ.get("DVIZH_TELEGRAM_DB", "/var/lib/dvizh/telegram.db"),
            web_db=os.environ.get("DVIZH_WEB_DB", "/var/lib/dvizh/dvizh.db"),
            web_api=os.environ.get("DVIZH_WEB_API", "http://127.0.0.1:8000").rstrip("/"),
            web_user_id=os.environ.get("DVIZH_WEB_USER_ID", "").strip(),
            web_user_email=os.environ.get("DVIZH_WEB_USER_EMAIL", "").strip(),
            interval_seconds=max(5, int(os.environ.get("DVIZH_BRIDGE_INTERVAL_SECONDS", "20"))),
            lookback_days=max(1, min(120, int(os.environ.get("DVIZH_BRIDGE_LOOKBACK_DAYS", "30")))),
            status_path=os.environ.get("DVIZH_BRIDGE_STATUS", "/var/lib/dvizh/bridge-status.json"),
            sync_signal_path=os.environ.get("DVIZH_BRIDGE_SYNC_SIGNAL", "/var/lib/dvizh/bridge-sync-now"),
            timeout_seconds=max(2, int(os.environ.get("DVIZH_BRIDGE_HTTP_TIMEOUT", "8"))),
        )


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(UTC).isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(low, min(high, number))


def _is_state_object(value: Any) -> bool:
    return isinstance(value, dict) and len(STATE_HINT_KEYS.intersection(value.keys())) >= 2


def _decode_state(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value if _is_state_object(value) else None
    if not isinstance(value, str) or len(value) < 8:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if _is_state_object(parsed) else None


def _column_value(row: sqlite3.Row, columns: Iterable[str]) -> tuple[str, Any] | None:
    names = {name.lower(): name for name in row.keys()}
    for preferred in columns:
        actual = names.get(preferred)
        if actual is not None and row[actual] not in (None, ""):
            return actual, row[actual]
    return None


def discover_identity(config: Config) -> Identity:
    if config.web_user_id:
        return Identity(config.web_user_id, config.web_user_email or "telegram@dvizh.local")

    db_path = Path(config.web_db)
    if not db_path.exists():
        raise IdentityNotReady(f"web database not found: {db_path}")

    candidates: list[tuple[int, datetime, Identity]] = []
    uri = f"file:{db_path}?mode=ro"
    try:
        db = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        raise IdentityNotReady(f"cannot open web database: {exc}") from exc
    db.row_factory = sqlite3.Row
    try:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table in tables:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({quote_ident(table)})")]
            if not columns:
                continue
            lower = {name.lower(): name for name in columns}
            likely_state_columns = [lower[name] for name in STATE_COLUMN_RANK if name in lower]
            scan_columns = likely_state_columns or columns
            try:
                rows = db.execute(f"SELECT * FROM {quote_ident(table)} ORDER BY rowid DESC LIMIT 200").fetchall()
            except sqlite3.Error:
                rows = db.execute(f"SELECT * FROM {quote_ident(table)} LIMIT 200").fetchall()
            for row in rows:
                state_column: str | None = None
                for column in scan_columns:
                    if _decode_state(row[column]) is not None:
                        state_column = column
                        break
                if state_column is None:
                    continue

                user_pair = _column_value(row, USER_COLUMN_RANK)
                if user_pair is None:
                    for column in columns:
                        lowered = column.lower()
                        value = row[column]
                        if column == state_column or value in (None, ""):
                            continue
                        if any(token in lowered for token in ("revision", "updated", "created", "email", "state", "payload")):
                            continue
                        if isinstance(value, str) and 1 <= len(value) <= 512:
                            user_pair = (column, value)
                            break
                if user_pair is None:
                    continue

                email_pair = _column_value(row, EMAIL_COLUMN_RANK)
                email = str(email_pair[1]) if email_pair else "telegram@dvizh.local"
                updated_pair = _column_value(row, UPDATED_COLUMN_RANK)
                updated = parse_datetime(updated_pair[1]) if updated_pair else None
                updated = updated or datetime(1970, 1, 1, tzinfo=UTC)

                table_penalty = 5 if any(word in table.lower() for word in ("history", "snapshot", "backup")) else 0
                user_bonus = 20 if user_pair[0].lower() in USER_COLUMN_RANK else 0
                state_bonus = 10 if state_column.lower() in STATE_COLUMN_RANK else 0
                candidates.append((user_bonus + state_bonus - table_penalty, updated, Identity(str(user_pair[1]), email)))
    finally:
        db.close()

    if not candidates:
        raise IdentityNotReady(
            "no web user state found yet; open the web DVIZH once while logged into exe.dev, then request /sync"
        )

    best_by_id: dict[str, tuple[int, datetime, Identity]] = {}
    for candidate in candidates:
        key = candidate[2].user_id
        previous = best_by_id.get(key)
        if previous is None or (candidate[0], candidate[1]) > (previous[0], previous[1]):
            best_by_id[key] = candidate

    if len(best_by_id) != 1:
        masked = ", ".join(sorted(hashlib.sha256(key.encode()).hexdigest()[:8] for key in best_by_id))
        raise IdentityNotReady(
            f"multiple web users found ({masked}); set DVIZH_WEB_USER_ID explicitly before syncing"
        )
    return next(iter(best_by_id.values()))[2]


class WebStateClient:
    def __init__(self, config: Config, identity: Identity):
        self.base = config.web_api
        self.identity = identity
        self.timeout = config.timeout_seconds

    def _request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else canonical(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "User-Agent": f"DVIZH-Bridge/{APP_VERSION}",
            "X-ExeDev-UserID": self.identity.user_id,
            "X-ExeDev-Email": self.identity.email,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            try:
                detail = json.loads(raw.decode("utf-8"))
            except Exception:
                detail = {"raw": raw.decode("utf-8", errors="replace")[:500]}
            if status == 409:
                raise RevisionConflict(detail)
            raise BridgeError(f"web API {method} {path} returned HTTP {status}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BridgeError(f"web API {method} {path} unavailable: {exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeError(f"web API {method} {path} returned invalid JSON (HTTP {status})") from exc
        if not isinstance(data, dict):
            raise BridgeError(f"web API {method} {path} returned non-object JSON")
        return data

    def health(self) -> dict[str, Any]:
        return self._request("/api/health")

    def get_state(self) -> tuple[int, dict[str, Any]]:
        response = self._request("/api/state")
        revision = clamp_int(response.get("revision"), 0, 2_147_483_647, 0)
        state = response.get("state")
        if not isinstance(state, dict):
            raise BridgeError("web API state payload is missing or invalid")
        return revision, state

    def put_state(self, base_revision: int, state: dict[str, Any]) -> int:
        response = self._request(
            "/api/state",
            method="PUT",
            payload={"baseRevision": base_revision, "state": state},
        )
        if response.get("ok") is not True:
            raise BridgeError(f"web API refused state update: {response}")
        return clamp_int(response.get("revision"), 0, 2_147_483_647, base_revision + 1)


class RevisionConflict(BridgeError):
    def __init__(self, payload: dict[str, Any]):
        super().__init__("web state revision conflict")
        self.payload = payload


def telegram_connection(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def _authorized_user(db: sqlite3.Connection) -> sqlite3.Row:
    rows = db.execute("SELECT * FROM users WHERE authorized=1 ORDER BY chat_id").fetchall()
    if not rows:
        raise IdentityNotReady("Telegram bot is not paired yet")
    if len(rows) != 1:
        raise BridgeError("bridge v1 requires exactly one authorized Telegram chat")
    return rows[0]


def _local_date(value: str | None, timezone_name: str) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return date.today().isoformat()
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
    return parsed.astimezone(tz).date().isoformat()


def _valid_web_checkin(value: Any) -> bool:
    return isinstance(value, dict) and all(value.get(key) is not None for key in ("energy", "pain", "fear"))


def import_web_actions(db: sqlite3.Connection, state: dict[str, Any], user: sqlite3.Row) -> dict[str, int]:
    chat_id = int(user["chat_id"])
    imported_done = 0
    imported_checkins = 0

    for task in state.get("tasks", []) if isinstance(state.get("tasks"), list) else []:
        if not isinstance(task, dict) or not task.get("done"):
            continue
        task_id = str(task.get("id", ""))
        prefix = f"tg-occ-{chat_id}-"
        if not task_id.startswith(prefix):
            continue
        try:
            occurrence_id = int(task_id[len(prefix):])
        except ValueError:
            continue
        row = db.execute(
            "SELECT status FROM occurrences WHERE id=? AND chat_id=?",
            (occurrence_id, chat_id),
        ).fetchone()
        if row and row["status"] == "pending":
            db.execute(
                "UPDATE occurrences SET status='done', completed_at_utc=? WHERE id=? AND chat_id=?",
                (iso_utc(), occurrence_id, chat_id),
            )
            db.execute(
                "INSERT INTO event_log(chat_id,event_type,payload_json,created_at_utc) VALUES(?,?,?,?)",
                (chat_id, "web_occurrence_done", canonical({"occurrence_id": occurrence_id}), iso_utc()),
            )
            imported_done += 1

    timezone_name = str(user["timezone"] or "Europe/Moscow")
    try:
        today_key = utcnow().astimezone(ZoneInfo(timezone_name)).date().isoformat()
    except Exception:
        today_key = utcnow().date().isoformat()
    web_checkins = state.get("checkins") if isinstance(state.get("checkins"), dict) else {}
    web_checkin = web_checkins.get(today_key)
    if _valid_web_checkin(web_checkin):
        web_updated = parse_datetime(web_checkin.get("updatedAt"))
        latest = db.execute(
            "SELECT created_at_utc FROM checkins WHERE chat_id=? ORDER BY created_at_utc DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        latest_at = parse_datetime(latest["created_at_utc"]) if latest else None
        if web_updated and (latest_at is None or web_updated > latest_at + timedelta(seconds=1)):
            db.execute(
                "INSERT INTO checkins(chat_id,energy,body,stress,created_at_utc) VALUES(?,?,?,?,?)",
                (
                    chat_id,
                    clamp_int(web_checkin.get("energy"), 0, 3, 1),
                    clamp_int(web_checkin.get("pain"), 0, 3, 0),
                    clamp_int(web_checkin.get("fear"), 0, 3, 0),
                    iso_utc(web_updated),
                ),
            )
            db.execute(
                "INSERT INTO event_log(chat_id,event_type,payload_json,created_at_utc) VALUES(?,?,?,?)",
                (chat_id, "web_checkin_imported", canonical({"date": today_key}), iso_utc()),
            )
            imported_checkins += 1

    return {"webDoneImported": imported_done, "webCheckinsImported": imported_checkins}


def build_projection(db: sqlite3.Connection, user: sqlite3.Row, lookback_days: int) -> dict[str, Any]:
    chat_id = int(user["chat_id"])
    timezone_name = str(user["timezone"] or "Europe/Moscow")
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("Europe/Moscow")
        timezone_name = "Europe/Moscow"
    today = utcnow().astimezone(tz).date()
    min_day = (today - timedelta(days=lookback_days)).isoformat()
    max_day = (today + timedelta(days=1)).isoformat()

    occurrences = db.execute(
        """
        SELECT o.*, r.created_at_utc AS recurring_created_at
        FROM occurrences o
        LEFT JOIN recurring_tasks r ON r.id=o.recurring_task_id
        WHERE o.chat_id=? AND o.due_date_local>=? AND o.due_date_local<=?
        ORDER BY o.scheduled_at_utc, o.id
        """,
        (chat_id, min_day, max_day),
    ).fetchall()

    tasks: list[dict[str, Any]] = []
    occurrence_by_id: dict[int, sqlite3.Row] = {}
    for row in occurrences:
        occurrence_by_id[int(row["id"])] = row
        due_day = str(row["due_date_local"])
        status = str(row["status"])
        if due_day < today.isoformat() and status == "pending":
            continue
        done = status in {"done", "partial", "skipped"}
        task: dict[str, Any] = {
            "id": f"tg-occ-{chat_id}-{int(row['id'])}",
            "title": str(row["title"]),
            "micro": str(row["microstep"] or f"Открой «{row['title']}» и сделай первый шаг."),
            "area": AREA_MAP.get(str(row["area"]), "Разное"),
            "energy": clamp_int(row["energy_cost"], 0, 2, 0) + 1,
            "fear": 0,
            "priority": 2,
            "duration": clamp_int(row["normal_minutes"], 2, 180, 8),
            "done": done,
            "createdAt": str(row["created_at_utc"] or row["scheduled_at_utc"]),
            "source": "telegram",
            "recurringTaskId": int(row["recurring_task_id"]),
            "dueDate": due_day,
            "scheduledAt": str(row["scheduled_at_utc"]),
            "telegramStatus": status,
        }
        if done:
            task["completedAt"] = str(row["completed_at_utc"] or row["scheduled_at_utc"])
        tasks.append(task)

    sessions_rows = db.execute(
        """
        SELECT f.*, o.title AS occurrence_title, o.area AS occurrence_area
        FROM focus_sessions f
        LEFT JOIN occurrences o ON o.id=f.occurrence_id
        WHERE f.chat_id=? AND f.started_at_utc>=? AND f.result IN ('done','partial','no')
        ORDER BY f.started_at_utc, f.id
        """,
        (chat_id, iso_utc(utcnow() - timedelta(days=lookback_days))),
    ).fetchall()

    sessions: list[dict[str, Any]] = []
    proofs: list[dict[str, Any]] = []
    occurrence_ids_with_positive_session: set[int] = set()
    for row in sessions_rows:
        result = str(row["result"])
        occurrence_id = int(row["occurrence_id"]) if row["occurrence_id"] is not None else None
        title = str(row["occurrence_title"] or ("Возврат из залипа" if row["source"] == "doomscroll_rescue" else "Фокус-раунд"))
        created_at = str(row["finished_at_utc"] or row["started_at_utc"])
        session_id = int(row["id"])
        task_id = f"tg-occ-{chat_id}-{occurrence_id}" if occurrence_id else None
        if result in {"done", "partial"}:
            if occurrence_id:
                occurrence_ids_with_positive_session.add(occurrence_id)
            sessions.append(
                {
                    "id": f"tg-session-{chat_id}-{session_id}",
                    "taskId": task_id,
                    "taskTitle": title,
                    "minutes": clamp_int(row["planned_minutes"], 1, 180, 5),
                    "plannedMinutes": clamp_int(row["planned_minutes"], 1, 180, 5),
                    "outcome": result,
                    "date": _local_date(created_at, timezone_name),
                    "createdAt": created_at,
                    "source": "telegram",
                }
            )
            proofs.append(
                {
                    "id": f"tg-proof-session-{chat_id}-{session_id}",
                    "text": ("Закрыл через Telegram: " if result == "done" else "Сделал часть через Telegram: ") + title,
                    "type": "task" if result == "done" else "session",
                    "taskId": task_id,
                    "date": _local_date(created_at, timezone_name),
                    "createdAt": created_at,
                    "source": "telegram",
                }
            )

    for occurrence_id, row in occurrence_by_id.items():
        status = str(row["status"])
        if status not in {"done", "partial"} or occurrence_id in occurrence_ids_with_positive_session:
            continue
        created_at = str(row["completed_at_utc"] or row["scheduled_at_utc"])
        proofs.append(
            {
                "id": f"tg-proof-occ-{chat_id}-{occurrence_id}",
                "text": ("Закрыл через Telegram: " if status == "done" else "Сделал часть через Telegram: ") + str(row["title"]),
                "type": "task" if status == "done" else "session",
                "taskId": f"tg-occ-{chat_id}-{occurrence_id}",
                "date": str(row["due_date_local"]),
                "createdAt": created_at,
                "source": "telegram",
            }
        )

    checkins: dict[str, dict[str, Any]] = {}
    rows = db.execute(
        "SELECT * FROM checkins WHERE chat_id=? AND created_at_utc>=? ORDER BY created_at_utc",
        (chat_id, iso_utc(utcnow() - timedelta(days=lookback_days))),
    ).fetchall()
    for row in rows:
        day_key = _local_date(str(row["created_at_utc"]), timezone_name)
        checkins[day_key] = {
            "energy": clamp_int(row["energy"], 0, 3, 1),
            "pain": clamp_int(row["body"], 0, 3, 0),
            "fear": clamp_int(row["stress"], 0, 3, 0),
            "updatedAt": str(row["created_at_utc"]),
            "source": "telegram",
        }

    event_row = db.execute("SELECT COALESCE(MAX(id),0) FROM event_log WHERE chat_id=?", (chat_id,)).fetchone()
    return {
        "chatId": chat_id,
        "timezone": timezone_name,
        "tasks": tasks,
        "sessions": sessions,
        "proofs": proofs,
        "checkins": checkins,
        "lastEventId": int(event_row[0] if event_row else 0),
    }


def _merge_managed_list(existing: Any, projected: list[dict[str, Any]], prefix: str, *, remove_stale: bool) -> list[dict[str, Any]]:
    current = [item for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    existing_by_id = {str(item.get("id")): item for item in current if item.get("id") is not None}
    projected_ids = {str(item["id"]) for item in projected}

    unmanaged: list[dict[str, Any]] = []
    for item in current:
        item_id = str(item.get("id", ""))
        if not item_id.startswith(prefix):
            unmanaged.append(item)
        elif not remove_stale and item_id not in projected_ids:
            unmanaged.append(item)

    merged_projected: list[dict[str, Any]] = []
    for item in projected:
        previous = existing_by_id.get(str(item["id"]), {})
        merged = dict(previous)
        merged.update(item)
        merged_projected.append(merged)
    return unmanaged + merged_projected


def merge_projection(state: dict[str, Any], projection: dict[str, Any]) -> tuple[dict[str, Any], bool, dict[str, int]]:
    before = canonical(state)
    merged = json.loads(before)
    merged.setdefault("version", 1)
    chat_id = int(projection["chatId"])

    merged["tasks"] = _merge_managed_list(
        merged.get("tasks"), projection["tasks"], f"tg-occ-{chat_id}-", remove_stale=True
    )
    merged["sessions"] = _merge_managed_list(
        merged.get("sessions"), projection["sessions"], f"tg-session-{chat_id}-", remove_stale=False
    )
    merged["proofs"] = _merge_managed_list(
        merged.get("proofs"), projection["proofs"], "tg-proof-", remove_stale=False
    )
    merged["proofs"] = sorted(
        merged["proofs"], key=lambda item: str(item.get("createdAt", "")), reverse=True
    )[:2000]

    existing_checkins = merged.get("checkins") if isinstance(merged.get("checkins"), dict) else {}
    checkins = dict(existing_checkins)
    for day_key, incoming in projection["checkins"].items():
        current = checkins.get(day_key)
        current_at = parse_datetime(current.get("updatedAt")) if isinstance(current, dict) else None
        incoming_at = parse_datetime(incoming.get("updatedAt"))
        if current_at is None or (incoming_at is not None and incoming_at >= current_at):
            checkins[day_key] = incoming
    merged["checkins"] = checkins

    integrations = merged.get("integrations") if isinstance(merged.get("integrations"), dict) else {}
    integrations = dict(integrations)
    projection_hash = hashlib.sha256(
        canonical(
            {
                "tasks": projection["tasks"],
                "sessions": projection["sessions"],
                "proofs": projection["proofs"],
                "checkins": projection["checkins"],
                "lastEventId": projection["lastEventId"],
            }
        ).encode("utf-8")
    ).hexdigest()
    previous_meta = integrations.get("telegram") if isinstance(integrations.get("telegram"), dict) else {}
    meta = {
        "linked": True,
        "version": APP_VERSION,
        "timezone": projection["timezone"],
        "projectionHash": projection_hash,
        "lastEventId": projection["lastEventId"],
        "lastSyncAt": previous_meta.get("lastSyncAt"),
    }
    integrations["telegram"] = meta
    merged["integrations"] = integrations

    changed_without_timestamp = canonical(merged) != before
    if changed_without_timestamp:
        integrations["telegram"]["lastSyncAt"] = iso_utc()
        merged["integrations"] = integrations

    stats = {
        "tasks": len(projection["tasks"]),
        "sessions": len(projection["sessions"]),
        "proofs": len(projection["proofs"]),
        "checkins": len(projection["checkins"]),
    }
    return merged, changed_without_timestamp, stats


def write_status(config: Config, payload: dict[str, Any]) -> None:
    path = Path(config.status_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    complete = {
        "version": APP_VERSION,
        "at": iso_utc(),
        **payload,
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(complete, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.chmod(temp, 0o640)
    os.replace(temp, path)


def sync_once(config: Config) -> dict[str, Any]:
    identity = discover_identity(config)
    client = WebStateClient(config, identity)
    health = client.health()
    if health.get("ok") is not True:
        raise BridgeError(f"web health check failed: {health}")

    telegram_path = Path(config.telegram_db)
    if not telegram_path.exists():
        raise IdentityNotReady(f"Telegram database not found: {telegram_path}")

    last_error: Exception | None = None
    for attempt in range(1, 5):
        revision, state = client.get_state()
        with telegram_connection(config.telegram_db) as db:
            user = _authorized_user(db)
            imported = import_web_actions(db, state, user)
            db.commit()
            projection = build_projection(db, user, config.lookback_days)

        merged, changed, stats = merge_projection(state, projection)
        if not changed:
            return {
                "ok": True,
                "changed": False,
                "webRevision": revision,
                "webUser": identity.masked,
                **stats,
                **imported,
            }
        try:
            new_revision = client.put_state(revision, merged)
        except RevisionConflict as exc:
            last_error = exc
            time.sleep(0.2 * attempt)
            continue
        return {
            "ok": True,
            "changed": True,
            "webRevision": new_revision,
            "webUser": identity.masked,
            **stats,
            **imported,
        }
    raise BridgeError(f"state kept changing during sync: {last_error}")


def run_loop(config: Config) -> int:
    stopped = False

    def stop_handler(_signum: int, _frame: Any) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    LOG.info("DVIZH bridge %s started; interval=%ss", APP_VERSION, config.interval_seconds)
    while not stopped:
        try:
            result = sync_once(config)
            write_status(config, result)
            LOG.info(
                "sync ok changed=%s revision=%s tasks=%s sessions=%s proofs=%s",
                result.get("changed"),
                result.get("webRevision"),
                result.get("tasks"),
                result.get("sessions"),
                result.get("proofs"),
            )
        except IdentityNotReady as exc:
            payload = {"ok": False, "waiting": True, "error": str(exc)}
            write_status(config, payload)
            LOG.warning("sync waiting: %s", exc)
        except Exception as exc:
            payload = {"ok": False, "waiting": False, "error": str(exc)}
            write_status(config, payload)
            LOG.exception("sync failed")

        waited = 0.0
        while not stopped and waited < config.interval_seconds:
            signal_path = Path(config.sync_signal_path)
            if signal_path.exists():
                try:
                    signal_path.unlink()
                except OSError:
                    pass
                break
            step = min(1.0, config.interval_seconds - waited)
            time.sleep(step)
            waited += step
    LOG.info("DVIZH bridge stopped")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize DVIZH Telegram state with the web application")
    parser.add_argument("--once", action="store_true", help="perform one synchronization and exit")
    parser.add_argument("--status", action="store_true", help="print the last sanitized status and exit")
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("DVIZH_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.from_env()

    if args.status:
        path = Path(config.status_path)
        if not path.exists():
            print(json.dumps({"ok": False, "error": "status not created yet"}, ensure_ascii=False))
            return 1
        print(path.read_text(encoding="utf-8"))
        return 0
    if args.once:
        try:
            result = sync_once(config)
            write_status(config, result)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        except IdentityNotReady as exc:
            result = {"ok": False, "waiting": True, "error": str(exc)}
            write_status(config, result)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 3
        except Exception as exc:
            result = {"ok": False, "waiting": False, "error": str(exc)}
            write_status(config, result)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 1
    return run_loop(config)


if __name__ == "__main__":
    sys.exit(main())
