from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")

KIND_LABELS = {
    "work": "💼 Работа",
    "rest": "🛋 Отдых",
    "friend": "🤝 Встреча",
    "errand": "📍 Дела",
    "documents": "📄 Документы",
    "health": "🩺 Здоровье",
    "gym": "🏋️ Зал",
    "volleyball": "🏐 Волейбол",
    "other": "• Разное",
}

WEEKDAY_LABELS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


def from_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None


def weekday_mask(days: set[int]) -> int:
    mask = 0
    for day in days:
        if not 0 <= day <= 6:
            raise ValueError("weekday must be 0..6")
        mask |= 1 << day
    return mask


def mask_has_day(mask: int, day: int) -> bool:
    return bool(mask & (1 << day))


def describe_weekdays(mask: int) -> str:
    if mask == 0b1111111:
        return "каждый день"
    weekdays = weekday_mask({0, 1, 2, 3, 4})
    if mask == weekdays:
        return "по будням"
    return " ".join(label for index, label in enumerate(WEEKDAY_LABELS) if mask_has_day(mask, index))


def parse_hhmm(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    hour, minute = int(hour_text), int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("invalid HH:MM")
    return hour, minute


def local_to_utc(day: date, hhmm: str, timezone: str) -> datetime:
    hour, minute = parse_hhmm(hhmm)
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(timezone))
    return local.astimezone(UTC)


@dataclass(frozen=True)
class ScheduleItem:
    id: int
    chat_id: int
    title: str
    kind: str
    recurrence: str
    date_local: str | None
    weekdays_mask: int | None
    start_local: str
    duration_minutes: int
    reminder_minutes: int
    enabled: bool


@dataclass(frozen=True)
class ScheduleOccurrence:
    id: int
    schedule_item_id: int
    chat_id: int
    due_date_local: str
    title: str
    kind: str
    start_at_utc: datetime
    end_at_utc: datetime
    reminder_minutes: int
    status: str
    reminder_sent_at_utc: datetime | None
    snoozed_until_utc: datetime | None


class WeeklyStore:
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
        CREATE TABLE IF NOT EXISTS schedule_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            recurrence TEXT NOT NULL CHECK(recurrence IN ('once','weekly')),
            date_local TEXT,
            weekdays_mask INTEGER,
            start_local TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            reminder_minutes INTEGER NOT NULL DEFAULT 30,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            CHECK(
                (recurrence='once' AND date_local IS NOT NULL AND weekdays_mask IS NULL) OR
                (recurrence='weekly' AND date_local IS NULL AND weekdays_mask IS NOT NULL)
            )
        );
        CREATE INDEX IF NOT EXISTS idx_schedule_items_chat ON schedule_items(chat_id, enabled, start_local);

        CREATE TABLE IF NOT EXISTS schedule_occurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_item_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            due_date_local TEXT NOT NULL,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            start_at_utc TEXT NOT NULL,
            end_at_utc TEXT NOT NULL,
            reminder_minutes INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','done','skipped')),
            reminder_sent_at_utc TEXT,
            snoozed_until_utc TEXT,
            completed_at_utc TEXT,
            created_at_utc TEXT NOT NULL,
            UNIQUE(schedule_item_id, due_date_local),
            FOREIGN KEY(schedule_item_id) REFERENCES schedule_items(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_schedule_occ_due
          ON schedule_occurrences(chat_id, status, start_at_utc);
        """
        with self.conn() as db:
            db.executescript(schema)

    def add_once(
        self,
        *,
        chat_id: int,
        title: str,
        kind: str,
        date_local: date,
        start_local: str,
        duration_minutes: int,
        reminder_minutes: int,
    ) -> int:
        if kind not in KIND_LABELS:
            raise ValueError("invalid kind")
        parse_hhmm(start_local)
        if not 5 <= duration_minutes <= 720:
            raise ValueError("duration out of range")
        if reminder_minutes not in {0, 10, 30, 60, 120}:
            raise ValueError("invalid reminder")
        now = iso(utcnow())
        with self.conn() as db:
            cur = db.execute(
                """
                INSERT INTO schedule_items(
                  chat_id,title,kind,recurrence,date_local,weekdays_mask,start_local,
                  duration_minutes,reminder_minutes,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,'once',?,NULL,?,?,?,?,?)
                """,
                (chat_id, title.strip(), kind, date_local.isoformat(), start_local,
                 duration_minutes, reminder_minutes, now, now),
            )
            return int(cur.lastrowid)

    def add_weekly(
        self,
        *,
        chat_id: int,
        title: str,
        kind: str,
        weekdays_mask: int,
        start_local: str,
        duration_minutes: int,
        reminder_minutes: int,
    ) -> int:
        if kind not in KIND_LABELS:
            raise ValueError("invalid kind")
        if weekdays_mask <= 0 or weekdays_mask > 0b1111111:
            raise ValueError("invalid weekdays")
        parse_hhmm(start_local)
        if not 5 <= duration_minutes <= 720:
            raise ValueError("duration out of range")
        if reminder_minutes not in {0, 10, 30, 60, 120}:
            raise ValueError("invalid reminder")
        now = iso(utcnow())
        with self.conn() as db:
            cur = db.execute(
                """
                INSERT INTO schedule_items(
                  chat_id,title,kind,recurrence,date_local,weekdays_mask,start_local,
                  duration_minutes,reminder_minutes,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,'weekly',NULL,?,?,?,?,?,?)
                """,
                (chat_id, title.strip(), kind, weekdays_mask, start_local,
                 duration_minutes, reminder_minutes, now, now),
            )
            return int(cur.lastrowid)

    def list_items(self, chat_id: int, *, enabled_only: bool = False) -> list[ScheduleItem]:
        sql = "SELECT * FROM schedule_items WHERE chat_id=?"
        params: list[object] = [chat_id]
        if enabled_only:
            sql += " AND enabled=1"
        sql += " ORDER BY start_local,id"
        with self.conn() as db:
            return [self._item(row) for row in db.execute(sql, params).fetchall()]

    def get_item(self, chat_id: int, item_id: int) -> ScheduleItem | None:
        with self.conn() as db:
            row = db.execute("SELECT * FROM schedule_items WHERE id=? AND chat_id=?", (item_id, chat_id)).fetchone()
            return self._item(row) if row else None

    def set_item_enabled(self, chat_id: int, item_id: int, enabled: bool) -> bool:
        with self.conn() as db:
            cur = db.execute(
                "UPDATE schedule_items SET enabled=?,updated_at_utc=? WHERE id=? AND chat_id=?",
                (int(enabled), iso(utcnow()), item_id, chat_id),
            )
            if cur.rowcount and not enabled:
                # Future pending rows are projections of the recurring rule, not
                # history. Drop them so pausing immediately stops reminders;
                # re-enabling can recreate the applicable dates safely.
                db.execute(
                    "DELETE FROM schedule_occurrences WHERE schedule_item_id=? AND chat_id=? AND status='pending'",
                    (item_id, chat_id),
                )
            return bool(cur.rowcount)

    def delete_item(self, chat_id: int, item_id: int) -> bool:
        with self.conn() as db:
            cur = db.execute("DELETE FROM schedule_items WHERE id=? AND chat_id=?", (item_id, chat_id))
            return bool(cur.rowcount)

    def ensure_range(self, chat_id: int, start_day: date, days: int, timezone: str) -> int:
        if days < 1 or days > 31:
            raise ValueError("days out of range")
        items = self.list_items(chat_id, enabled_only=True)
        created = 0
        with self.conn() as db:
            for offset in range(days):
                day = start_day + timedelta(days=offset)
                for item in items:
                    if item.recurrence == "once":
                        if item.date_local != day.isoformat():
                            continue
                    elif item.weekdays_mask is None or not mask_has_day(item.weekdays_mask, day.weekday()):
                        continue
                    start_at = local_to_utc(day, item.start_local, timezone)
                    end_at = start_at + timedelta(minutes=item.duration_minutes)
                    cur = db.execute(
                        """
                        INSERT OR IGNORE INTO schedule_occurrences(
                          schedule_item_id,chat_id,due_date_local,title,kind,start_at_utc,end_at_utc,
                          reminder_minutes,created_at_utc
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (item.id, chat_id, day.isoformat(), item.title, item.kind,
                         iso(start_at), iso(end_at), item.reminder_minutes, iso(utcnow())),
                    )
                    created += cur.rowcount
        return created

    def expire_before(self, chat_id: int, day: date) -> int:
        with self.conn() as db:
            cur = db.execute(
                """
                UPDATE schedule_occurrences
                SET status='skipped', completed_at_utc=?
                WHERE chat_id=? AND status='pending' AND due_date_local<?
                """,
                (iso(utcnow()), chat_id, day.isoformat()),
            )
            return cur.rowcount

    def list_occurrences(self, chat_id: int, start_day: date, days: int) -> list[ScheduleOccurrence]:
        end_day = start_day + timedelta(days=days - 1)
        with self.conn() as db:
            rows = db.execute(
                """
                SELECT * FROM schedule_occurrences
                WHERE chat_id=? AND due_date_local BETWEEN ? AND ?
                ORDER BY due_date_local,start_at_utc,id
                """,
                (chat_id, start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
        return [self._occurrence(row) for row in rows]

    def due_for_reminder(self, chat_id: int, now_utc: datetime) -> list[ScheduleOccurrence]:
        with self.conn() as db:
            rows = db.execute(
                """
                SELECT * FROM schedule_occurrences
                WHERE chat_id=? AND status='pending' AND reminder_sent_at_utc IS NULL
                ORDER BY start_at_utc,id
                """,
                (chat_id,),
            ).fetchall()
        due: list[ScheduleOccurrence] = []
        for row in rows:
            occurrence = self._occurrence(row)
            trigger_at = occurrence.start_at_utc - timedelta(minutes=occurrence.reminder_minutes)
            if occurrence.snoozed_until_utc:
                trigger_at = occurrence.snoozed_until_utc
            if trigger_at <= now_utc:
                due.append(occurrence)
        return due

    def mark_reminder_sent(self, chat_id: int, occurrence_id: int) -> None:
        with self.conn() as db:
            db.execute(
                "UPDATE schedule_occurrences SET reminder_sent_at_utc=? WHERE id=? AND chat_id=?",
                (iso(utcnow()), occurrence_id, chat_id),
            )

    def snooze(self, chat_id: int, occurrence_id: int, minutes: int) -> None:
        if minutes not in {10, 30, 60}:
            raise ValueError("invalid snooze")
        with self.conn() as db:
            db.execute(
                """
                UPDATE schedule_occurrences
                SET snoozed_until_utc=?, reminder_sent_at_utc=NULL
                WHERE id=? AND chat_id=? AND status='pending'
                """,
                (iso(utcnow() + timedelta(minutes=minutes)), occurrence_id, chat_id),
            )

    def set_occurrence_status(self, chat_id: int, occurrence_id: int, status: str) -> bool:
        if status not in {"done", "skipped"}:
            raise ValueError("invalid status")
        with self.conn() as db:
            cur = db.execute(
                """
                UPDATE schedule_occurrences
                SET status=?, completed_at_utc=?
                WHERE id=? AND chat_id=? AND status='pending'
                """,
                (status, iso(utcnow()), occurrence_id, chat_id),
            )
            return bool(cur.rowcount)

    def _item(self, row: sqlite3.Row) -> ScheduleItem:
        return ScheduleItem(
            id=int(row["id"]),
            chat_id=int(row["chat_id"]),
            title=str(row["title"]),
            kind=str(row["kind"]),
            recurrence=str(row["recurrence"]),
            date_local=row["date_local"],
            weekdays_mask=int(row["weekdays_mask"]) if row["weekdays_mask"] is not None else None,
            start_local=str(row["start_local"]),
            duration_minutes=int(row["duration_minutes"]),
            reminder_minutes=int(row["reminder_minutes"]),
            enabled=bool(row["enabled"]),
        )

    def _occurrence(self, row: sqlite3.Row) -> ScheduleOccurrence:
        return ScheduleOccurrence(
            id=int(row["id"]),
            schedule_item_id=int(row["schedule_item_id"]),
            chat_id=int(row["chat_id"]),
            due_date_local=str(row["due_date_local"]),
            title=str(row["title"]),
            kind=str(row["kind"]),
            start_at_utc=from_iso(row["start_at_utc"]),
            end_at_utc=from_iso(row["end_at_utc"]),
            reminder_minutes=int(row["reminder_minutes"]),
            status=str(row["status"]),
            reminder_sent_at_utc=from_iso(row["reminder_sent_at_utc"]),
            snoozed_until_utc=from_iso(row["snoozed_until_utc"]),
        )
