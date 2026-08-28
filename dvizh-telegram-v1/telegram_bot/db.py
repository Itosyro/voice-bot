from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from .logic import Checkin, local_to_utc, mask_has_day

UTC = ZoneInfo("UTC")


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


def from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None


@dataclass(frozen=True)
class RecurringTask:
    id: int
    chat_id: int
    title: str
    microstep: str | None
    area: str
    weekdays_mask: int
    time_local: str
    min_minutes: int
    normal_minutes: int
    energy_cost: int
    enabled: bool


@dataclass(frozen=True)
class Occurrence:
    id: int
    recurring_task_id: int
    chat_id: int
    title: str
    microstep: str | None
    area: str
    scheduled_at_utc: datetime
    min_minutes: int
    normal_minutes: int
    energy_cost: int
    status: str
    snoozed_until_utc: datetime | None
    reminder_sent_at_utc: datetime | None
    followup_sent_at_utc: datetime | None


class Database:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            try:
                yield db
                db.commit()
            finally:
                db.close()

    def init_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            telegram_user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            timezone TEXT NOT NULL,
            quiet_start TEXT NOT NULL,
            quiet_end TEXT NOT NULL,
            authorized INTEGER NOT NULL DEFAULT 0,
            pending_occurrence_id INTEGER,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            energy INTEGER NOT NULL,
            body INTEGER NOT NULL,
            stress INTEGER NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY(chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_checkins_chat_created ON checkins(chat_id, created_at_utc DESC);
        CREATE TABLE IF NOT EXISTS checkin_drafts (
            chat_id INTEGER PRIMARY KEY,
            energy INTEGER,
            body INTEGER,
            stress INTEGER,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY(chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS recurring_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            microstep TEXT,
            area TEXT NOT NULL,
            weekdays_mask INTEGER NOT NULL,
            time_local TEXT NOT NULL,
            min_minutes INTEGER NOT NULL,
            normal_minutes INTEGER NOT NULL,
            energy_cost INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY(chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS occurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recurring_task_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            due_date_local TEXT NOT NULL,
            title TEXT NOT NULL,
            microstep TEXT,
            area TEXT NOT NULL,
            scheduled_at_utc TEXT NOT NULL,
            min_minutes INTEGER NOT NULL,
            normal_minutes INTEGER NOT NULL,
            energy_cost INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            snoozed_until_utc TEXT,
            reminder_sent_at_utc TEXT,
            followup_sent_at_utc TEXT,
            completed_at_utc TEXT,
            created_at_utc TEXT NOT NULL,
            UNIQUE(recurring_task_id, due_date_local),
            FOREIGN KEY(recurring_task_id) REFERENCES recurring_tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_occ_due ON occurrences(chat_id, status, scheduled_at_utc);
        CREATE TABLE IF NOT EXISTS focus_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            occurrence_id INTEGER,
            source TEXT NOT NULL,
            planned_minutes INTEGER NOT NULL,
            started_at_utc TEXT NOT NULL,
            due_at_utc TEXT NOT NULL,
            finished_at_utc TEXT,
            result TEXT,
            result_prompt_sent_at_utc TEXT,
            FOREIGN KEY(chat_id) REFERENCES users(chat_id) ON DELETE CASCADE,
            FOREIGN KEY(occurrence_id) REFERENCES occurrences(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_focus_due ON focus_sessions(result, due_at_utc);
        CREATE TABLE IF NOT EXISTS event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT,
            created_at_utc TEXT NOT NULL
        );
        """
        with self.conn() as db:
            db.executescript(schema)

    def authorized_count(self) -> int:
        with self.conn() as db:
            return int(db.execute("SELECT COUNT(*) FROM users WHERE authorized=1").fetchone()[0])

    def upsert_user(
        self,
        *,
        chat_id: int,
        telegram_user_id: int,
        username: str | None,
        first_name: str | None,
        timezone: str,
        quiet_start: str,
        quiet_end: str,
        authorized: bool,
    ) -> None:
        now = iso(utcnow())
        with self.conn() as db:
            db.execute(
                """
                INSERT INTO users(chat_id, telegram_user_id, username, first_name, timezone, quiet_start, quiet_end, authorized, created_at_utc, updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    telegram_user_id=excluded.telegram_user_id,
                    username=excluded.username,
                    first_name=excluded.first_name,
                    timezone=excluded.timezone,
                    quiet_start=excluded.quiet_start,
                    quiet_end=excluded.quiet_end,
                    authorized=MAX(users.authorized, excluded.authorized),
                    updated_at_utc=excluded.updated_at_utc
                """,
                (chat_id, telegram_user_id, username, first_name, timezone, quiet_start, quiet_end, int(authorized), now, now),
            )

    def is_authorized(self, chat_id: int) -> bool:
        with self.conn() as db:
            row = db.execute("SELECT authorized FROM users WHERE chat_id=?", (chat_id,)).fetchone()
            return bool(row and row[0])

    def list_authorized_users(self) -> list[sqlite3.Row]:
        with self.conn() as db:
            return list(db.execute("SELECT * FROM users WHERE authorized=1 ORDER BY chat_id"))

    def get_user(self, chat_id: int) -> sqlite3.Row | None:
        with self.conn() as db:
            return db.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()

    def set_pending_occurrence(self, chat_id: int, occurrence_id: int | None) -> None:
        with self.conn() as db:
            db.execute(
                "UPDATE users SET pending_occurrence_id=?, updated_at_utc=? WHERE chat_id=?",
                (occurrence_id, iso(utcnow()), chat_id),
            )

    def start_checkin_draft(self, chat_id: int) -> None:
        with self.conn() as db:
            db.execute(
                """
                INSERT INTO checkin_drafts(chat_id, energy, body, stress, updated_at_utc)
                VALUES(?,?,?,?,?)
                ON CONFLICT(chat_id) DO UPDATE SET energy=NULL, body=NULL, stress=NULL, updated_at_utc=excluded.updated_at_utc
                """,
                (chat_id, None, None, None, iso(utcnow())),
            )

    def update_checkin_draft(self, chat_id: int, field: str, value: int) -> None:
        if field not in {"energy", "body", "stress"}:
            raise ValueError("invalid checkin field")
        with self.conn() as db:
            db.execute(f"UPDATE checkin_drafts SET {field}=?, updated_at_utc=? WHERE chat_id=?", (value, iso(utcnow()), chat_id))

    def finish_checkin(self, chat_id: int) -> Checkin:
        with self.conn() as db:
            row = db.execute("SELECT energy, body, stress FROM checkin_drafts WHERE chat_id=?", (chat_id,)).fetchone()
            if not row or any(row[key] is None for key in ("energy", "body", "stress")):
                raise RuntimeError("checkin draft incomplete")
            created = utcnow()
            db.execute(
                "INSERT INTO checkins(chat_id, energy, body, stress, created_at_utc) VALUES(?,?,?,?,?)",
                (chat_id, row["energy"], row["body"], row["stress"], iso(created)),
            )
            db.execute("DELETE FROM checkin_drafts WHERE chat_id=?", (chat_id,))
            return Checkin(int(row["energy"]), int(row["body"]), int(row["stress"]), created)

    def latest_checkin(self, chat_id: int) -> Checkin | None:
        with self.conn() as db:
            row = db.execute(
                "SELECT energy, body, stress, created_at_utc FROM checkins WHERE chat_id=? ORDER BY created_at_utc DESC LIMIT 1",
                (chat_id,),
            ).fetchone()
            if not row:
                return None
            return Checkin(int(row["energy"]), int(row["body"]), int(row["stress"]), from_iso(row["created_at_utc"]))

    def add_recurring_task(
        self,
        *,
        chat_id: int,
        title: str,
        microstep: str | None,
        area: str,
        weekdays_mask: int,
        time_local: str,
        min_minutes: int,
        normal_minutes: int,
        energy_cost: int,
    ) -> int:
        now = iso(utcnow())
        with self.conn() as db:
            cur = db.execute(
                """
                INSERT INTO recurring_tasks(chat_id, title, microstep, area, weekdays_mask, time_local, min_minutes, normal_minutes, energy_cost, created_at_utc, updated_at_utc)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (chat_id, title.strip(), (microstep or "").strip() or None, area, weekdays_mask, time_local, min_minutes, normal_minutes, energy_cost, now, now),
            )
            return int(cur.lastrowid)

    def list_recurring_tasks(self, chat_id: int, enabled_only: bool = False) -> list[RecurringTask]:
        sql = "SELECT * FROM recurring_tasks WHERE chat_id=?"
        params: list[Any] = [chat_id]
        if enabled_only:
            sql += " AND enabled=1"
        sql += " ORDER BY time_local, id"
        with self.conn() as db:
            rows = db.execute(sql, params).fetchall()
        return [self._task_from_row(r) for r in rows]

    def get_recurring_task(self, task_id: int) -> RecurringTask | None:
        with self.conn() as db:
            row = db.execute("SELECT * FROM recurring_tasks WHERE id=?", (task_id,)).fetchone()
            return self._task_from_row(row) if row else None

    def set_task_enabled(self, chat_id: int, task_id: int, enabled: bool) -> None:
        with self.conn() as db:
            db.execute(
                "UPDATE recurring_tasks SET enabled=?, updated_at_utc=? WHERE id=? AND chat_id=?",
                (int(enabled), iso(utcnow()), task_id, chat_id),
            )

    def delete_task(self, chat_id: int, task_id: int) -> None:
        with self.conn() as db:
            db.execute("DELETE FROM recurring_tasks WHERE id=? AND chat_id=?", (task_id, chat_id))

    def _task_from_row(self, row: sqlite3.Row) -> RecurringTask:
        return RecurringTask(
            id=int(row["id"]), chat_id=int(row["chat_id"]), title=row["title"], microstep=row["microstep"], area=row["area"],
            weekdays_mask=int(row["weekdays_mask"]), time_local=row["time_local"], min_minutes=int(row["min_minutes"]),
            normal_minutes=int(row["normal_minutes"]), energy_cost=int(row["energy_cost"]), enabled=bool(row["enabled"]),
        )

    def ensure_occurrences_for_day(self, chat_id: int, day_local: date, timezone: str) -> int:
        tasks = self.list_recurring_tasks(chat_id, enabled_only=True)
        created = 0
        with self.conn() as db:
            for task in tasks:
                if not mask_has_day(task.weekdays_mask, day_local.weekday()):
                    continue
                scheduled = local_to_utc(day_local, task.time_local, timezone)
                cur = db.execute(
                    """
                    INSERT OR IGNORE INTO occurrences(
                        recurring_task_id, chat_id, due_date_local, title, microstep, area, scheduled_at_utc,
                        min_minutes, normal_minutes, energy_cost, created_at_utc
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (task.id, chat_id, day_local.isoformat(), task.title, task.microstep, task.area, iso(scheduled), task.min_minutes, task.normal_minutes, task.energy_cost, iso(utcnow())),
                )
                created += cur.rowcount
        return created

    def list_today_occurrences(self, chat_id: int, day_local: date) -> list[Occurrence]:
        with self.conn() as db:
            rows = db.execute(
                "SELECT * FROM occurrences WHERE chat_id=? AND due_date_local=? ORDER BY scheduled_at_utc, id",
                (chat_id, day_local.isoformat()),
            ).fetchall()
        return [self._occ_from_row(r) for r in rows]

    def get_occurrence(self, occurrence_id: int, chat_id: int | None = None) -> Occurrence | None:
        sql = "SELECT * FROM occurrences WHERE id=?"
        params: list[Any] = [occurrence_id]
        if chat_id is not None:
            sql += " AND chat_id=?"
            params.append(chat_id)
        with self.conn() as db:
            row = db.execute(sql, params).fetchone()
            return self._occ_from_row(row) if row else None

    def pending_due_occurrences(self, chat_id: int, now_utc: datetime) -> list[Occurrence]:
        with self.conn() as db:
            rows = db.execute(
                """
                SELECT * FROM occurrences
                WHERE chat_id=? AND status='pending'
                  AND scheduled_at_utc<=?
                  AND (snoozed_until_utc IS NULL OR snoozed_until_utc<=?)
                ORDER BY scheduled_at_utc, id
                """,
                (chat_id, iso(now_utc), iso(now_utc)),
            ).fetchall()
        return [self._occ_from_row(r) for r in rows]

    def mark_reminder_sent(self, occurrence_id: int, when: datetime | None = None) -> None:
        with self.conn() as db:
            db.execute("UPDATE occurrences SET reminder_sent_at_utc=? WHERE id=?", (iso(when or utcnow()), occurrence_id))

    def mark_followup_sent(self, occurrence_id: int, when: datetime | None = None) -> None:
        with self.conn() as db:
            db.execute("UPDATE occurrences SET followup_sent_at_utc=? WHERE id=?", (iso(when or utcnow()), occurrence_id))

    def set_occurrence_status(self, occurrence_id: int, chat_id: int, status: str) -> None:
        if status not in {"pending", "done", "partial", "skipped"}:
            raise ValueError("invalid status")
        completed = iso(utcnow()) if status in {"done", "skipped"} else None
        with self.conn() as db:
            db.execute(
                "UPDATE occurrences SET status=?, completed_at_utc=COALESCE(?, completed_at_utc) WHERE id=? AND chat_id=?",
                (status, completed, occurrence_id, chat_id),
            )

    def snooze_occurrence(self, occurrence_id: int, chat_id: int, minutes: int) -> None:
        until = utcnow() + timedelta(minutes=minutes)
        with self.conn() as db:
            db.execute(
                "UPDATE occurrences SET snoozed_until_utc=?, reminder_sent_at_utc=NULL, followup_sent_at_utc=NULL WHERE id=? AND chat_id=?",
                (iso(until), occurrence_id, chat_id),
            )

    def overdue_followups(self, chat_id: int, now_utc: datetime, followup_minutes: int) -> list[Occurrence]:
        threshold = now_utc - timedelta(minutes=followup_minutes)
        with self.conn() as db:
            rows = db.execute(
                """
                SELECT * FROM occurrences
                WHERE chat_id=? AND status='pending'
                  AND reminder_sent_at_utc IS NOT NULL AND reminder_sent_at_utc<=?
                  AND followup_sent_at_utc IS NULL
                ORDER BY reminder_sent_at_utc
                """,
                (chat_id, iso(threshold)),
            ).fetchall()
        return [self._occ_from_row(r) for r in rows]

    def best_pending_occurrence(self, chat_id: int, now_utc: datetime) -> Occurrence | None:
        due = self.pending_due_occurrences(chat_id, now_utc)
        return due[0] if due else None

    def start_focus_session(self, chat_id: int, occurrence_id: int | None, source: str, minutes: int) -> int:
        started = utcnow()
        due = started + timedelta(minutes=minutes)
        with self.conn() as db:
            cur = db.execute(
                "INSERT INTO focus_sessions(chat_id, occurrence_id, source, planned_minutes, started_at_utc, due_at_utc) VALUES(?,?,?,?,?,?)",
                (chat_id, occurrence_id, source, minutes, iso(started), iso(due)),
            )
            return int(cur.lastrowid)

    def focus_sessions_due_for_prompt(self, now_utc: datetime) -> list[sqlite3.Row]:
        with self.conn() as db:
            return list(db.execute(
                "SELECT * FROM focus_sessions WHERE result IS NULL AND result_prompt_sent_at_utc IS NULL AND due_at_utc<=? ORDER BY due_at_utc",
                (iso(now_utc),),
            ))

    def mark_focus_prompt_sent(self, session_id: int) -> None:
        with self.conn() as db:
            db.execute("UPDATE focus_sessions SET result_prompt_sent_at_utc=? WHERE id=?", (iso(utcnow()), session_id))

    def finish_focus_session(self, session_id: int, chat_id: int, result: str) -> sqlite3.Row | None:
        if result not in {"done", "partial", "no"}:
            raise ValueError("invalid focus result")
        with self.conn() as db:
            row = db.execute("SELECT * FROM focus_sessions WHERE id=? AND chat_id=?", (session_id, chat_id)).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE focus_sessions SET result=?, finished_at_utc=? WHERE id=? AND chat_id=?",
                (result, iso(utcnow()), session_id, chat_id),
            )
            return row

    def log_event(self, chat_id: int, event_type: str, payload: dict[str, Any] | None = None) -> None:
        with self.conn() as db:
            db.execute(
                "INSERT INTO event_log(chat_id, event_type, payload_json, created_at_utc) VALUES(?,?,?,?)",
                (chat_id, event_type, json.dumps(payload or {}, ensure_ascii=False), iso(utcnow())),
            )

    def _occ_from_row(self, row: sqlite3.Row) -> Occurrence:
        return Occurrence(
            id=int(row["id"]), recurring_task_id=int(row["recurring_task_id"]), chat_id=int(row["chat_id"]),
            title=row["title"], microstep=row["microstep"], area=row["area"], scheduled_at_utc=from_iso(row["scheduled_at_utc"]),
            min_minutes=int(row["min_minutes"]), normal_minutes=int(row["normal_minutes"]), energy_cost=int(row["energy_cost"]),
            status=row["status"], snoozed_until_utc=from_iso(row["snoozed_until_utc"]), reminder_sent_at_utc=from_iso(row["reminder_sent_at_utc"]),
            followup_sent_at_utc=from_iso(row["followup_sent_at_utc"]),
        )
