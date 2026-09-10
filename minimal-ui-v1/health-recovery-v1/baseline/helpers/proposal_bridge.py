#!/usr/bin/env python3
from __future__ import annotations

import copy
import fcntl
import json
import logging
import os
import secrets
import signal
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

VERSION = "2026.09.05-ai-approval.1"
UTC = timezone.utc
LOG = logging.getLogger("dvizh.ai.approval")

PROPOSAL_DIR = Path("/var/lib/dvizh/hermes-proposals")
PROPOSAL_STORE = PROPOSAL_DIR / "proposals.json"
PROPOSAL_LOCK = PROPOSAL_DIR / ".lock"
IDENTITY_PATH = Path("/var/lib/dvizh/auth-identity.json")
TELEGRAM_DB = Path("/var/lib/dvizh/telegram.db")
STATUS_PATH = Path("/var/lib/dvizh/ai-approval-status.json")
WEB_API = os.environ.get("DVIZH_WEB_API", "http://127.0.0.1:8000").rstrip("/")
INTERVAL = max(2, min(30, int(os.environ.get("DVIZH_AI_APPROVAL_INTERVAL", "3"))))
TIMEOUT = max(2, min(20, int(os.environ.get("DVIZH_AI_APPROVAL_TIMEOUT", "8"))))

ALLOWED_ACTIONS = {"task_create", "task_complete", "schedule_move", "day_plan"}
AREA_LABELS = {
    "pdd": "ПДД",
    "cafe": "Кафе",
    "volleyball": "Волейбол",
    "social": "Соцсети",
    "recovery": "Восстановление",
    "other": "Разное",
}
SENSITIVE_FRAGMENTS = (
    "token", "password", "passwd", "secret", "api_key", "apikey",
    "cookie", "authorization", "credential", "bearer", "session_key",
)

STOP = False


class BridgeError(RuntimeError):
    pass


class RevisionConflict(BridgeError):
    pass


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(UTC).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS)


def sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED_DEPTH]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            out[key] = "[REDACTED]" if is_sensitive_key(key) else sanitize(raw_value, depth + 1)
        return out
    if isinstance(value, list):
        return [sanitize(item, depth + 1) for item in value[:80]]
    if isinstance(value, str):
        return value[:2000] + ("…[TRUNCATED]" if len(value) > 2000 else "")
    return value


def clamp_int(value: Any, low: int, high: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


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


def load_identity() -> tuple[str, str]:
    payload = read_json(IDENTITY_PATH)
    if not payload:
        raise BridgeError("stable DVIZH auth identity is unavailable")
    user_id = recursive_value(payload, ("DVIZH_WEB_USER_ID", "user_id", "userId", "web_user_id", "webUserId", "subject", "uid", "id")) or ""
    email = recursive_value(payload, ("DVIZH_WEB_USER_EMAIL", "email", "user_email", "userEmail")) or ""
    if not user_id:
        raise BridgeError("stable DVIZH auth identity has no user id")
    return user_id, email or "local-account@dvizh.invalid"


class WebClient:
    def __init__(self, user_id: str, email: str):
        self.user_id = user_id
        self.email = email

    def request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = canonical(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/json",
            "User-Agent": f"DVIZH-AI-Approval/{VERSION}",
            "X-ExeDev-UserID": self.user_id,
            "X-ExeDev-Email": self.email,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(WEB_API + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 409:
                raise RevisionConflict(detail) from exc
            raise BridgeError(f"web API {method} {path}: HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise BridgeError(f"web API unavailable: {type(exc).__name__}") from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise BridgeError("web API returned invalid JSON") from exc
        if not isinstance(value, dict):
            raise BridgeError("web API returned non-object JSON")
        return value

    def get_state(self) -> tuple[int, dict[str, Any]]:
        response = self.request("/api/state")
        state = response.get("state")
        if not isinstance(state, dict):
            raise BridgeError("web state missing")
        return int(response.get("revision") or 0), state

    def put_state(self, revision: int, state: dict[str, Any]) -> int:
        response = self.request("/api/state", "PUT", {"baseRevision": revision, "state": state})
        if response.get("ok") is not True:
            raise BridgeError(f"web state write refused: {response}")
        return int(response.get("revision") or revision + 1)


def ensure_proposal_dir() -> None:
    PROPOSAL_DIR.mkdir(parents=True, exist_ok=True)


def load_queue_unlocked() -> list[dict[str, Any]]:
    if not PROPOSAL_STORE.exists():
        return []
    try:
        value = json.loads(PROPOSAL_STORE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def save_queue_unlocked(rows: list[dict[str, Any]]) -> None:
    fd, tmp = tempfile.mkstemp(prefix="proposals.", suffix=".json", dir=str(PROPOSAL_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, PROPOSAL_STORE)
        os.chmod(PROPOSAL_STORE, 0o640)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def with_queue_lock(fn: Callable[[list[dict[str, Any]]], Any]) -> Any:
    ensure_proposal_dir()
    with PROPOSAL_LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows = load_queue_unlocked()
        result = fn(rows)
        save_queue_unlocked(rows)
        return result


def queue_snapshot() -> list[dict[str, Any]]:
    def read(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return copy.deepcopy(rows)
    return with_queue_lock(read)


def resolve_queue(proposal_id: str, status: str, result: str) -> dict[str, Any]:
    if status not in {"applied", "rejected", "failed", "superseded"}:
        raise ValueError("invalid proposal resolution")

    def mutate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        for row in rows:
            if str(row.get("id") or "") != proposal_id:
                continue
            if row.get("status") != "pending":
                return row
            row["status"] = status
            row["resolution"] = status
            row["result"] = result[:1000]
            row["resolved_at_utc"] = iso()
            return row
        raise BridgeError("proposal not found")

    return with_queue_lock(mutate)


def public_proposal(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "action": str(row.get("action") or ""),
        "summary": str(row.get("summary") or "")[:500],
        "payload": sanitize(row.get("payload") if isinstance(row.get("payload"), dict) else {}),
        "status": str(row.get("status") or "pending"),
        "source": "hermes",
        "createdAt": row.get("created_at_utc"),
    }


def pending_proposals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "pending":
            continue
        if str(row.get("action") or "") not in ALLOWED_ACTIONS:
            continue
        result.append(public_proposal(row))
    return result[-20:]


def parse_hhmm(value: Any) -> tuple[int, int, str]:
    text = str(value or "").strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise BridgeError("time must be HH:MM")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise BridgeError("time must be HH:MM") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise BridgeError("invalid time")
    return hour, minute, f"{hour:02d}:{minute:02d}"


def local_today() -> str:
    if not TELEGRAM_DB.exists():
        return datetime.now().date().isoformat()
    try:
        db = sqlite3.connect(f"file:{TELEGRAM_DB}?mode=ro", uri=True, timeout=3)
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT timezone FROM users WHERE authorized=1 ORDER BY chat_id LIMIT 1").fetchone()
        db.close()
        timezone_name = str(row["timezone"] or "Europe/Moscow") if row else "Europe/Moscow"
        return utcnow().astimezone(ZoneInfo(timezone_name)).date().isoformat()
    except Exception:
        return utcnow().astimezone(ZoneInfo("Europe/Moscow")).date().isoformat()


def task_area_label(raw: Any) -> str:
    text = str(raw or "other").strip()
    return AREA_LABELS.get(text, text if 1 <= len(text) <= 40 else "Разное")


def state_task_create(state: dict[str, Any], proposal: dict[str, Any]) -> str:
    payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
    title = str(payload.get("title") or "").strip()
    if not 1 <= len(title) <= 240:
        raise BridgeError("task title is invalid")
    proposal_id = str(proposal.get("id") or "")
    task_id = f"ai-task-{proposal_id}"
    tasks = [item for item in state.get("tasks", []) if isinstance(item, dict)] if isinstance(state.get("tasks"), list) else []
    if any(str(item.get("id")) == task_id for item in tasks):
        return f"task already exists:{task_id}"
    task = {
        "id": task_id,
        "title": title,
        "micro": str(payload.get("micro") or f"Открой «{title}» и сделай первый шаг.")[:500],
        "area": task_area_label(payload.get("area")),
        "energy": clamp_int(payload.get("energy"), 1, 3, 1),
        "fear": clamp_int(payload.get("fear"), 0, 3, 0),
        "priority": clamp_int(payload.get("priority"), 1, 3, 2),
        "duration": clamp_int(payload.get("duration"), 2, 240, 10),
        "done": False,
        "createdAt": iso(),
        "source": "hermes",
        "dueDate": str(payload.get("due_date") or local_today())[:10],
        "proposalId": proposal_id,
    }
    state["tasks"] = tasks + [task]
    return f"created:{task_id}"


def state_task_complete(state: dict[str, Any], proposal: dict[str, Any]) -> str:
    payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise BridgeError("task_id missing")
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        raise BridgeError("task list unavailable")
    found = False
    for item in tasks:
        if not isinstance(item, dict) or str(item.get("id") or "") != task_id:
            continue
        item["done"] = True
        item["completedAt"] = iso()
        item["completedBy"] = "ai-approved"
        found = True
        break
    if not found:
        raise BridgeError("task not found")
    return f"completed:{task_id}"


def state_day_plan(state: dict[str, Any], proposal: dict[str, Any]) -> str:
    payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
    blocks = payload.get("blocks")
    if not isinstance(blocks, list) or not blocks or len(blocks) > 40:
        raise BridgeError("day plan blocks invalid")
    state["aiDayPlan"] = {
        "proposalId": str(proposal.get("id") or ""),
        "blocks": sanitize(blocks),
        "acceptedAt": iso(),
        "source": "hermes",
    }
    return f"day-plan:{len(blocks)}"


def parse_occurrence_id(raw: Any) -> int:
    text = str(raw or "").strip()
    if text.isdigit():
        value = int(text)
    else:
        tail = text.rsplit("-", 1)[-1]
        if not tail.isdigit():
            raise BridgeError("schedule occurrence id is invalid")
        value = int(tail)
    if value <= 0:
        raise BridgeError("schedule occurrence id is invalid")
    return value


def apply_schedule_move(proposal: dict[str, Any]) -> str:
    if not TELEGRAM_DB.exists():
        raise BridgeError("telegram database unavailable")
    payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
    occurrence_id = parse_occurrence_id(payload.get("occurrence_id"))
    hour, minute, hhmm = parse_hhmm(payload.get("start_local"))
    db = sqlite3.connect(str(TELEGRAM_DB), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    try:
        users = db.execute("SELECT chat_id,timezone FROM users WHERE authorized=1 ORDER BY chat_id").fetchall()
        if len(users) != 1:
            raise BridgeError("expected exactly one authorized DVIZH user")
        chat_id = int(users[0]["chat_id"])
        timezone_name = str(users[0]["timezone"] or "Europe/Moscow")
        row = db.execute(
            "SELECT * FROM schedule_occurrences WHERE id=? AND chat_id=?",
            (occurrence_id, chat_id),
        ).fetchone()
        if not row:
            raise BridgeError("schedule occurrence not found")
        day = date.fromisoformat(str(row["due_date_local"]))
        local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(timezone_name))
        new_start = local.astimezone(UTC)
        old_start = datetime.fromisoformat(str(row["start_at_utc"])).astimezone(UTC)
        old_end = datetime.fromisoformat(str(row["end_at_utc"])).astimezone(UTC)
        duration = old_end - old_start
        if duration <= timedelta(0) or duration > timedelta(hours=24):
            raise BridgeError("schedule occurrence duration invalid")
        new_end = new_start + duration
        db.execute(
            """
            UPDATE schedule_occurrences
            SET start_at_utc=?, end_at_utc=?, reminder_sent_at_utc=NULL, snoozed_until_utc=NULL
            WHERE id=? AND chat_id=?
            """,
            (iso(new_start), iso(new_end), occurrence_id, chat_id),
        )
        db.commit()
        return f"moved:{occurrence_id}:{hhmm}"
    finally:
        db.close()


def apply_state_action(client: WebClient, proposal: dict[str, Any], command_id: str, command_token: str) -> str:
    action = str(proposal.get("action") or "")
    handlers: dict[str, Callable[[dict[str, Any], dict[str, Any]], str]] = {
        "task_create": state_task_create,
        "task_complete": state_task_complete,
        "day_plan": state_day_plan,
    }
    if action not in handlers:
        raise BridgeError("not a state action")
    for attempt in range(1, 7):
        revision, state = client.get_state()
        token = str(state.get("aiProposalUiToken") or "")
        if not token or not secrets.compare_digest(token, command_token):
            raise BridgeError("approval token mismatch")
        updated = copy.deepcopy(state)
        result = handlers[action](updated, proposal)
        commands = updated.get("aiProposalCommands") if isinstance(updated.get("aiProposalCommands"), list) else []
        updated["aiProposalCommands"] = [
            cmd for cmd in commands
            if not (isinstance(cmd, dict) and str(cmd.get("id") or "") == command_id)
        ]
        updated["aiProposalLastResult"] = {
            "proposalId": str(proposal.get("id") or ""),
            "decision": "approve",
            "ok": True,
            "detail": result,
            "at": iso(),
        }
        # Optimistically hide the proposal. Queue status is committed immediately after web state succeeds.
        proposals = updated.get("aiProposals") if isinstance(updated.get("aiProposals"), list) else []
        updated["aiProposals"] = [p for p in proposals if not (isinstance(p, dict) and str(p.get("id") or "") == str(proposal.get("id") or ""))]
        try:
            client.put_state(revision, updated)
            return result
        except RevisionConflict:
            time.sleep(0.12 * attempt)
    raise BridgeError("web state revision kept changing")


def remove_command_and_publish(
    client: WebClient,
    command_id: str,
    pending: list[dict[str, Any]],
    *,
    result: dict[str, Any] | None = None,
) -> None:
    for attempt in range(1, 7):
        revision, state = client.get_state()
        updated = copy.deepcopy(state)
        commands = updated.get("aiProposalCommands") if isinstance(updated.get("aiProposalCommands"), list) else []
        updated["aiProposalCommands"] = [
            cmd for cmd in commands
            if not (isinstance(cmd, dict) and str(cmd.get("id") or "") == command_id)
        ]
        updated["aiProposals"] = pending
        if result is not None:
            updated["aiProposalLastResult"] = result
        try:
            client.put_state(revision, updated)
            return
        except RevisionConflict:
            time.sleep(0.12 * attempt)
    raise BridgeError("could not acknowledge AI proposal command")


def publish_only(client: WebClient, rows: list[dict[str, Any]]) -> int:
    pending = pending_proposals(rows)
    for attempt in range(1, 7):
        revision, state = client.get_state()
        updated = copy.deepcopy(state)
        token = str(updated.get("aiProposalUiToken") or "")
        if len(token) < 24:
            updated["aiProposalUiToken"] = secrets.token_urlsafe(32)
        if not isinstance(updated.get("aiProposalCommands"), list):
            updated["aiProposalCommands"] = []
        updated["aiProposals"] = pending
        if canonical(updated) == canonical(state):
            return len(pending)
        try:
            client.put_state(revision, updated)
            return len(pending)
        except RevisionConflict:
            time.sleep(0.12 * attempt)
    raise BridgeError("could not publish AI proposals after revision conflicts")


def find_pending(rows: list[dict[str, Any]], proposal_id: str) -> dict[str, Any] | None:
    for row in rows:
        if isinstance(row, dict) and row.get("status") == "pending" and str(row.get("id") or "") == proposal_id:
            return row
    return None


def process_one_command(client: WebClient, rows: list[dict[str, Any]]) -> bool:
    _revision, state = client.get_state()
    commands = state.get("aiProposalCommands") if isinstance(state.get("aiProposalCommands"), list) else []
    if not commands:
        return False
    command = next((cmd for cmd in commands if isinstance(cmd, dict)), None)
    if command is None:
        return False
    command_id = str(command.get("id") or "")[:160]
    proposal_id = str(command.get("proposalId") or "")[:80]
    decision = str(command.get("decision") or "")
    command_token = str(command.get("token") or "")
    current_token = str(state.get("aiProposalUiToken") or "")

    def ack(detail: str, ok: bool = False) -> None:
        result = {"proposalId": proposal_id, "decision": decision, "ok": ok, "detail": detail[:500], "at": iso()}
        remove_command_and_publish(client, command_id, pending_proposals(queue_snapshot()), result=result)

    if not command_id or not proposal_id or decision not in {"approve", "reject"}:
        ack("invalid approval command")
        return True
    if len(current_token) < 24 or len(command_token) < 24 or not secrets.compare_digest(current_token, command_token):
        ack("approval token mismatch")
        return True

    proposal = find_pending(rows, proposal_id)
    if proposal is None:
        ack("proposal is no longer pending")
        return True
    action = str(proposal.get("action") or "")
    if action not in ALLOWED_ACTIONS:
        resolve_queue(proposal_id, "failed", "unsupported proposal action")
        ack("unsupported proposal action")
        return True

    if decision == "reject":
        resolve_queue(proposal_id, "rejected", "rejected in authenticated DVIZH UI")
        ack("rejected", True)
        return True

    try:
        if action == "schedule_move":
            detail = apply_schedule_move(proposal)
            resolve_queue(proposal_id, "applied", detail)
            ack(detail, True)
        else:
            detail = apply_state_action(client, proposal, command_id, command_token)
            resolve_queue(proposal_id, "applied", detail)
            # apply_state_action already acknowledged this command; next publish refreshes queue.
            publish_only(client, queue_snapshot())
    except Exception as exc:
        LOG.exception("proposal apply failed: %s", proposal_id)
        resolve_queue(proposal_id, "failed", f"{type(exc).__name__}: {exc}")
        ack(f"apply failed: {type(exc).__name__}")
    return True


def write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": VERSION, "at": iso(), **payload}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o640)
    os.replace(tmp, STATUS_PATH)


def sync_once() -> dict[str, Any]:
    user_id, email = load_identity()
    client = WebClient(user_id, email)
    rows = queue_snapshot()
    processed = process_one_command(client, rows)
    rows = queue_snapshot()
    pending_count = publish_only(client, rows)
    payload = {"ok": True, "pending": pending_count, "processedCommand": processed}
    write_status(payload)
    return payload


def handle_signal(_signum: int, _frame: Any) -> None:
    global STOP
    STOP = True


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    LOG.info("starting DVIZH AI approval bridge %s", VERSION)
    while not STOP:
        try:
            result = sync_once()
            LOG.debug("sync: %s", result)
        except Exception as exc:
            LOG.warning("sync waiting/error: %s", exc)
            try:
                write_status({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            except Exception:
                pass
        for _ in range(INTERVAL * 2):
            if STOP:
                break
            time.sleep(0.5)
    LOG.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
