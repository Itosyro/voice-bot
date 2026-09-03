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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .training_store import ACTIVITY_LABELS, TrainingStore

VERSION = "2026.08.30-training.1"
UTC = timezone.utc
LOG = logging.getLogger("dvizh.training.web")
USER_ID_KEYS = ("DVIZH_WEB_USER_ID", "user_id", "userId", "web_user_id", "webUserId", "subject", "uid")
EMAIL_KEYS = ("DVIZH_WEB_USER_EMAIL", "email", "user_email", "userEmail")


class BridgeError(RuntimeError):
    pass


class NotReady(BridgeError):
    pass


class RevisionConflict(BridgeError):
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
    status_path: str = "/var/lib/dvizh/training-status.json"
    interval_seconds: int = 5
    timeout_seconds: int = 8

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            telegram_db=os.environ.get("DVIZH_TELEGRAM_DB", cls.telegram_db),
            web_api=os.environ.get("DVIZH_WEB_API", cls.web_api).rstrip("/"),
            bridge_env=os.environ.get("DVIZH_BRIDGE_ENV", cls.bridge_env),
            identity_json=os.environ.get("DVIZH_AUTH_IDENTITY", cls.identity_json),
            status_path=os.environ.get("DVIZH_TRAINING_STATUS", cls.status_path),
            interval_seconds=max(3, min(60, int(os.environ.get("DVIZH_TRAINING_INTERVAL", "5")))),
            timeout_seconds=max(2, min(30, int(os.environ.get("DVIZH_TRAINING_TIMEOUT", "8")))),
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
            parts = shlex.split(value.strip(), posix=True)
            result[key.strip()] = parts[0] if parts else ""
        except ValueError:
            result[key.strip()] = value.strip().strip('"\'')
    return result


def load_identity(config: Config) -> Identity:
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
            "User-Agent": f"DVIZH-Training/{VERSION}",
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
            raise BridgeError(f"web API {method} {path}: HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise BridgeError(f"web API unavailable: {exc}") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise BridgeError("web API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise BridgeError("web API returned non-object JSON")
        return result

    def health(self) -> None:
        payload = self.request("/api/health")
        if payload.get("ok") is not True:
            raise BridgeError(f"web health failed: {payload}")

    def get_state(self) -> tuple[int, dict[str, Any]]:
        payload = self.request("/api/state")
        state = payload.get("state")
        if not isinstance(state, dict):
            raise BridgeError("web state missing")
        return int(payload.get("revision") or 0), state

    def put_state(self, revision: int, state: dict[str, Any]) -> int:
        payload = self.request("/api/state", "PUT", {"baseRevision": revision, "state": state})
        if payload.get("ok") is not True:
            raise BridgeError(f"web state write refused: {payload}")
        return int(payload.get("revision") or revision + 1)


def authorized_user(db_path: str) -> sqlite3.Row:
    with sqlite3.connect(db_path, timeout=10) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM users WHERE authorized=1 ORDER BY chat_id").fetchall()
    if len(rows) != 1:
        raise NotReady(f"expected one paired Telegram chat, found {len(rows)}")
    return rows[0]


def command_list(state: dict[str, Any]) -> list[dict[str, Any]]:
    hub = state.get("trainingHub")
    if not isinstance(hub, dict):
        return []
    commands = hub.get("webCommands")
    if not isinstance(commands, list):
        return []
    return [row for row in commands if isinstance(row, dict)]


def _int(command: dict[str, Any], key: str, low: int, high: int) -> int:
    value = int(command.get(key))
    if not low <= value <= high:
        raise ValueError(f"{key} out of range")
    return value


def process_commands(store: TrainingStore, user: sqlite3.Row, state: dict[str, Any]) -> list[dict[str, Any]]:
    chat_id = int(user["chat_id"])
    timezone_name = str(user["timezone"] or "Europe/Moscow")
    today = store.local_today(timezone_name)
    results: list[dict[str, Any]] = []
    for command in command_list(state)[:30]:
        command_id = str(command.get("id") or "").strip()
        action = str(command.get("action") or "").strip()
        if not command_id or not action:
            continue
        if store.command_seen(command_id):
            results.append({"id": command_id, "action": action, "result": "duplicate", "at": iso()})
            continue
        try:
            if action == "readiness_save":
                result = store.save_readiness(
                    chat_id=chat_id,
                    local_day=today,
                    sleep_hours=float(command.get("sleepHours")),
                    sleep_quality=_int(command, "sleepQuality", 0, 3),
                    energy=_int(command, "energy", 0, 3),
                    soreness=_int(command, "soreness", 0, 3),
                    pain=_int(command, "pain", 0, 3),
                    stress=_int(command, "stress", 0, 3),
                    illness=str(command.get("illness") or "none"),
                    red_flag=bool(command.get("redFlag")),
                )
                detail = f"readiness:{result.status}:{result.score}"
            elif action == "plan_enable":
                slots = store.ensure_default_plan(chat_id)
                detail = f"plan-enabled:{len(slots)}"
            elif action == "plan_disable":
                store.set_plan_enabled(chat_id, False)
                detail = "plan-disabled"
            elif action == "session_log":
                activity = str(command.get("activity") or "other")
                if activity not in ACTIVITY_LABELS:
                    raise ValueError("invalid activity")
                session_id = store.log_session(
                    chat_id=chat_id,
                    local_day=today,
                    activity=activity,
                    duration_minutes=_int(command, "durationMinutes", 1, 720),
                    rpe=_int(command, "rpe", 0, 10),
                    result=str(command.get("result") or "done"),
                    pain_after=_int(command, "painAfter", 0, 3),
                    jumps=int(command["jumps"]) if command.get("jumps") not in (None, "") else None,
                    notes=str(command.get("notes") or "")[:500],
                    source="web",
                )
                detail = f"session:{session_id}"
            else:
                raise ValueError("unknown action")
            store.remember_command(command_id, chat_id, action, "ok", detail)
            results.append({"id": command_id, "action": action, "result": "ok", "detail": detail, "at": iso()})
        except Exception as exc:
            detail = str(exc)[:300]
            store.remember_command(command_id, chat_id, action, "error", detail)
            results.append({"id": command_id, "action": action, "result": "error", "detail": detail, "at": iso()})
    return results[-20:]


def build_projection(store: TrainingStore, user: sqlite3.Row, command_results: list[dict[str, Any]]) -> dict[str, Any]:
    chat_id = int(user["chat_id"])
    timezone_name = str(user["timezone"] or "Europe/Moscow")
    today = store.local_today(timezone_name)
    store.sync_slots_from_schedule(chat_id)
    profile = store.profile(chat_id)
    slots = store.plan_slots(chat_id)
    readiness = store.readiness_for_day(chat_id, today)
    loads = store.load_summary(chat_id)
    sessions = store.recent_sessions(chat_id, 20)
    upcoming = store.upcoming_training(chat_id, today, 7)
    context = store.schedule_context(chat_id, today)
    return {
        "version": 1,
        "timezone": timezone_name,
        "localDate": today.isoformat(),
        "profile": {
            "planEnabled": bool(profile and profile["plan_enabled"]),
            "readinessPromptLocal": str(profile["readiness_prompt_local"] if profile else "10:00"),
        },
        "planSlots": [
            {
                "code": slot.code,
                "title": slot.title,
                "focus": slot.focus,
                "weekday": slot.weekday,
                "startLocal": slot.start_local,
                "durationMinutes": slot.duration_minutes,
                "scheduleItemId": f"tg-schedule-item-{chat_id}-{slot.schedule_item_id}" if slot.schedule_item_id else None,
                "enabled": slot.enabled,
            }
            for slot in slots
        ],
        "readiness": readiness,
        "todayContext": context,
        "metrics": {
            "load7d": int(loads["load_7d"] or 0),
            "baselineWeeklyLoad": int(loads["baseline_weekly_load"]) if loads["baseline_weekly_load"] is not None else None,
            "lowerLoad36h": int(loads["lower_load_36h"] or 0),
        },
        "upcoming": upcoming,
        "sessions": [
            {
                "id": session.id,
                "activity": session.activity,
                "activityLabel": ACTIVITY_LABELS.get(session.activity, session.activity),
                "date": session.planned_date_local,
                "durationMinutes": session.duration_minutes,
                "rpe": session.rpe,
                "load": session.session_load,
                "result": session.result,
                "painAfter": session.pain_after,
                "jumps": session.jumps,
                "createdAt": session.created_at_utc,
            }
            for session in sessions
        ],
        "commandResults": command_results,
        "webCommands": [],
    }


def normalized(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    result = dict(value)
    result.pop("syncedAt", None)
    return result


def merge_projection(state: dict[str, Any], projection: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    current = state.get("trainingHub")
    if canonical(normalized(current)) == canonical(normalized(projection)):
        return state, False
    merged = json.loads(canonical(state))
    payload = dict(projection)
    payload["syncedAt"] = iso()
    merged["trainingHub"] = payload
    return merged, True


def write_status(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": VERSION, "at": iso(), **payload}
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(temp, 0o640)
    os.replace(temp, target)


def sync_once(config: Config) -> dict[str, Any]:
    identity = load_identity(config)
    client = WebClient(config, identity)
    client.health()
    store = TrainingStore(config.telegram_db)
    user = authorized_user(config.telegram_db)
    last_conflict: Exception | None = None
    for attempt in range(1, 6):
        revision, state = client.get_state()
        command_results = process_commands(store, user, state)
        projection = build_projection(store, user, command_results)
        merged, changed = merge_projection(state, projection)
        if not changed:
            return {
                "ok": True,
                "changed": False,
                "webRevision": revision,
                "webUser": identity.masked,
                "score": projection.get("readiness", {}).get("result", {}).get("score") if projection.get("readiness") else None,
                "planSlots": len(projection["planSlots"]),
                "sessions": len(projection["sessions"]),
                "commands": len(command_results),
            }
        try:
            new_revision = client.put_state(revision, merged)
        except RevisionConflict as exc:
            last_conflict = exc
            time.sleep(0.15 * attempt)
            continue
        return {
            "ok": True,
            "changed": True,
            "webRevision": new_revision,
            "webUser": identity.masked,
            "score": projection.get("readiness", {}).get("result", {}).get("score") if projection.get("readiness") else None,
            "planSlots": len(projection["planSlots"]),
            "sessions": len(projection["sessions"]),
            "commands": len(command_results),
        }
    raise BridgeError(f"web state kept changing: {last_conflict}")


def run_loop(config: Config) -> int:
    stopped = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOG.info("training web bridge %s started", VERSION)
    while not stopped:
        try:
            result = sync_once(config)
            write_status(config.status_path, result)
            LOG.info(
                "sync ok changed=%s revision=%s score=%s plan=%s sessions=%s commands=%s",
                result.get("changed"), result.get("webRevision"), result.get("score"),
                result.get("planSlots"), result.get("sessions"), result.get("commands"),
            )
        except NotReady as exc:
            write_status(config.status_path, {"ok": False, "waiting": True, "error": str(exc)})
            LOG.warning("sync waiting: %s", exc)
        except Exception as exc:
            write_status(config.status_path, {"ok": False, "waiting": False, "error": str(exc)})
            LOG.exception("training sync failed")
        waited = 0
        while not stopped and waited < config.interval_seconds:
            time.sleep(1)
            waited += 1
    return 0


def main() -> int:
    logging.basicConfig(level=os.environ.get("DVIZH_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return run_loop(Config.from_env())


if __name__ == "__main__":
    raise SystemExit(main())
