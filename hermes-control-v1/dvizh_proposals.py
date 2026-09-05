#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2026.09.05-hermes-proposals.2"
STORE_DIR = Path(os.environ.get("DVIZH_PROPOSAL_DIR", "/var/lib/dvizh/hermes-proposals"))
STORE = STORE_DIR / "proposals.json"
LOCK = STORE_DIR / ".lock"
ALLOWED_ACTIONS = {"task_create", "task_complete", "schedule_move", "day_plan"}
VISIBLE_STATUSES = {"pending", "rejected", "superseded", "applied", "failed"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)


def load_unlocked() -> list[dict[str, Any]]:
    if not STORE.exists():
        return []
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_unlocked(rows: list[dict[str, Any]]) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix="proposals.", suffix=".json", dir=str(STORE_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, STORE)
        os.chmod(STORE, 0o640)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def locked_update(fn):
    ensure_dir()
    with LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows = load_unlocked()
        result = fn(rows)
        save_unlocked(rows)
        return result


def parse_payload(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"payload must be valid JSON: {exc}")
    if not isinstance(value, dict):
        raise SystemExit("payload must be a JSON object")
    if len(json.dumps(value, ensure_ascii=False)) > 12000:
        raise SystemExit("payload too large")
    return value


def validate(action: str, payload: dict[str, Any]) -> None:
    if action not in ALLOWED_ACTIONS:
        raise SystemExit("unsupported action")
    if action == "task_create":
        title = str(payload.get("title") or "").strip()
        if not 1 <= len(title) <= 240:
            raise SystemExit("task_create requires title (1..240 chars)")
    elif action == "task_complete":
        if not str(payload.get("task_id") or "").strip():
            raise SystemExit("task_complete requires task_id")
    elif action == "schedule_move":
        if not str(payload.get("occurrence_id") or "").strip():
            raise SystemExit("schedule_move requires occurrence_id")
        start = str(payload.get("start_local") or "").strip()
        if len(start) != 5 or start[2] != ":":
            raise SystemExit("schedule_move requires start_local HH:MM")
        try:
            hour, minute = map(int, start.split(":"))
        except ValueError:
            raise SystemExit("invalid start_local")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise SystemExit("invalid start_local")
    elif action == "day_plan":
        blocks = payload.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise SystemExit("day_plan requires non-empty blocks array")
        if len(blocks) > 40:
            raise SystemExit("too many day_plan blocks")


def create(action: str, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    validate(action, payload)
    summary = summary.strip()
    if not 1 <= len(summary) <= 500:
        raise SystemExit("summary must be 1..500 chars")
    proposal = {
        "id": uuid.uuid4().hex[:12],
        "action": action,
        "summary": summary,
        "payload": payload,
        "status": "pending",
        "source": "hermes",
        "created_at_utc": now_iso(),
        "resolved_at_utc": None,
        "resolution": None,
        "version": VERSION,
    }
    def mut(rows):
        rows.append(proposal)
        if len(rows) > 200:
            del rows[:-200]
        return proposal
    return locked_update(mut)


def resolve(proposal_id: str, resolution: str) -> dict[str, Any]:
    # Hermes may only withdraw/reject its own pending suggestion. It cannot
    # mark anything applied; authenticated DVIZH approval service owns that.
    if resolution not in {"rejected", "superseded"}:
        raise SystemExit("only rejected/superseded can be resolved by Hermes control")
    def mut(rows):
        for row in rows:
            if row.get("id") == proposal_id:
                if row.get("status") != "pending":
                    raise SystemExit("proposal is not pending")
                row["status"] = resolution
                row["resolution"] = resolution
                row["resolved_at_utc"] = now_iso()
                return row
        raise SystemExit("proposal not found")
    return locked_update(mut)


def list_rows(status: str | None) -> list[dict[str, Any]]:
    ensure_dir()
    rows = load_unlocked()
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows[-50:]


def main() -> int:
    parser = argparse.ArgumentParser(description="DVIZH AI proposal spool (does not apply changes)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_create = sub.add_parser("create")
    p_create.add_argument("action", choices=sorted(ALLOWED_ACTIONS))
    p_create.add_argument("summary")
    p_create.add_argument("payload_json")
    p_list = sub.add_parser("list")
    p_list.add_argument("--status", choices=sorted(VISIBLE_STATUSES))
    p_reject = sub.add_parser("reject")
    p_reject.add_argument("proposal_id")
    sub.add_parser("version")
    args = parser.parse_args()

    if args.cmd == "create":
        out = create(args.action, args.summary, parse_payload(args.payload_json))
    elif args.cmd == "list":
        out = list_rows(args.status)
    elif args.cmd == "reject":
        out = resolve(args.proposal_id, "rejected")
    else:
        print(VERSION)
        return 0
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
