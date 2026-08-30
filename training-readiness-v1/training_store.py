from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from .readiness import ReadinessInputs, ReadinessResult, evaluate_readiness

UTC = timezone.utc

PLAN_DEFAULTS = (
    ("upper_a", "Силовая · Верх A", "upper", 0, "19:00", 75, 1),
    ("lower_a", "Силовая · Низ A", "lower", 1, "19:00", 75, 2),
    ("upper_b", "Силовая · Верх B", "upper", 3, "19:00", 75, 3),
    ("lower_b", "Силовая · Низ B", "lower", 5, "14:00", 75, 4),
)

ACTIVITY_LABELS = {
    "upper_a": "Верх A",
    "lower_a": "Низ A",
    "upper_b": "Верх B",
    "lower_b": "Низ B",
    "volleyball": "Волейбол",
    "recovery": "Восстановление",
    "other": "Другая нагрузка",
}

LOWER_FACTORS = {
    "upper_a": 0.15,
    "upper_b": 0.15,
    "lower_a": 0.85,
    "lower_b": 0.85,
    "volleyball": 1.0,
    "recovery": 0.15,
    "other": 0.5,
}


@dataclass(frozen=True)
class TrainingPlanSlot:
    chat_id: int
    code: str
    title: str
    focus: str
    weekday: int
    start_local: str
    duration_minutes: int
    schedule_item_id: int | None
    enabled: bool
    sort_order: int


@dataclass(frozen=True)
class TrainingSession:
    id: int
    chat_id: int
    activity: str
    planned_date_local: str
    duration_minutes: int
    rpe: int
    session_load: int
    result: str
    pain_after: int
    jumps: int | None
    created_at_utc: str


class TrainingStore:
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
        CREATE TABLE IF NOT EXISTS training_profiles (
          chat_id INTEGER PRIMARY KEY,
          plan_enabled INTEGER NOT NULL DEFAULT 0,
          readiness_prompt_local TEXT NOT NULL DEFAULT '10:00',
          created_at_utc TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS training_plan_slots (
          chat_id INTEGER NOT NULL,
          code TEXT NOT NULL,
          title TEXT NOT NULL,
          focus TEXT NOT NULL CHECK(focus IN ('upper','lower')),
          weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 6),
          start_local TEXT NOT NULL,
          duration_minutes INTEGER NOT NULL,
          schedule_item_id INTEGER,
          enabled INTEGER NOT NULL DEFAULT 1,
          sort_order INTEGER NOT NULL,
          created_at_utc TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL,
          PRIMARY KEY(chat_id, code)
        );
        CREATE INDEX IF NOT EXISTS idx_training_plan_chat
          ON training_plan_slots(chat_id, enabled, weekday, start_local);

        CREATE TABLE IF NOT EXISTS training_readiness (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chat_id INTEGER NOT NULL,
          local_date TEXT NOT NULL,
          sleep_hours REAL NOT NULL,
          sleep_quality INTEGER NOT NULL CHECK(sleep_quality BETWEEN 0 AND 3),
          energy INTEGER NOT NULL CHECK(energy BETWEEN 0 AND 3),
          soreness INTEGER NOT NULL CHECK(soreness BETWEEN 0 AND 3),
          pain INTEGER NOT NULL CHECK(pain BETWEEN 0 AND 3),
          stress INTEGER NOT NULL CHECK(stress BETWEEN 0 AND 3),
          illness TEXT NOT NULL CHECK(illness IN ('none','mild','systemic')),
          red_flag INTEGER NOT NULL DEFAULT 0,
          score INTEGER NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('green','yellow','red')),
          result_json TEXT NOT NULL,
          created_at_utc TEXT NOT NULL,
          updated_at_utc TEXT NOT NULL,
          UNIQUE(chat_id, local_date)
        );
        CREATE INDEX IF NOT EXISTS idx_training_readiness_chat_date
          ON training_readiness(chat_id, local_date DESC);

        CREATE TABLE IF NOT EXISTS training_sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          chat_id INTEGER NOT NULL,
          activity TEXT NOT NULL,
          planned_date_local TEXT NOT NULL,
          duration_minutes INTEGER NOT NULL CHECK(duration_minutes BETWEEN 1 AND 720),
          rpe INTEGER NOT NULL CHECK(rpe BETWEEN 0 AND 10),
          session_load INTEGER NOT NULL,
          result TEXT NOT NULL CHECK(result IN ('done','partial','skipped')),
          pain_after INTEGER NOT NULL CHECK(pain_after BETWEEN 0 AND 3),
          jumps INTEGER,
          notes TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT 'telegram',
          created_at_utc TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_training_sessions_chat_date
          ON training_sessions(chat_id, planned_date_local DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_training_sessions_chat_created
          ON training_sessions(chat_id, created_at_utc DESC);

        CREATE TABLE IF NOT EXISTS training_notifications (
          chat_id INTEGER NOT NULL,
          notification_key TEXT NOT NULL,
          sent_at_utc TEXT NOT NULL,
          PRIMARY KEY(chat_id, notification_key)
        );

        CREATE TABLE IF NOT EXISTS training_web_commands (
          command_id TEXT PRIMARY KEY,
          chat_id INTEGER NOT NULL,
          action TEXT NOT NULL,
          result TEXT NOT NULL,
          detail TEXT NOT NULL DEFAULT '',
          processed_at_utc TEXT NOT NULL
        );
        """
        with self.conn() as db:
            db.executescript(schema)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(tz=UTC)

    @classmethod
    def iso(cls, value: datetime | None = None) -> str:
        return (value or cls.utcnow()).astimezone(UTC).isoformat()

    @staticmethod
    def local_today(timezone_name: str) -> date:
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")
        return datetime.now(tz=UTC).astimezone(tz).date()

    def profile(self, chat_id: int) -> sqlite3.Row | None:
        with self.conn() as db:
            return db.execute("SELECT * FROM training_profiles WHERE chat_id=?", (chat_id,)).fetchone()

    def _ensure_profile(self, db: sqlite3.Connection, chat_id: int) -> None:
        now = self.iso()
        db.execute(
            "INSERT OR IGNORE INTO training_profiles(chat_id,created_at_utc,updated_at_utc) VALUES(?,?,?)",
            (chat_id, now, now),
        )

    def plan_slots(self, chat_id: int) -> list[TrainingPlanSlot]:
        with self.conn() as db:
            rows = db.execute(
                "SELECT * FROM training_plan_slots WHERE chat_id=? ORDER BY sort_order,code",
                (chat_id,),
            ).fetchall()
        return [self._slot(row) for row in rows]

    def ensure_default_plan(self, chat_id: int) -> list[TrainingPlanSlot]:
        now = self.iso()
        with self.conn() as db:
            self._ensure_profile(db, chat_id)
            for code, title, focus, weekday, start_local, duration, sort_order in PLAN_DEFAULTS:
                db.execute(
                    """
                    INSERT OR IGNORE INTO training_plan_slots(
                      chat_id,code,title,focus,weekday,start_local,duration_minutes,
                      enabled,sort_order,created_at_utc,updated_at_utc
                    ) VALUES(?,?,?,?,?,?,?,1,?,?,?)
                    """,
                    (chat_id, code, title, focus, weekday, start_local, duration, sort_order, now, now),
                )

            for code, title, _focus, weekday, start_local, duration, _sort_order in PLAN_DEFAULTS:
                slot = db.execute(
                    "SELECT * FROM training_plan_slots WHERE chat_id=? AND code=?",
                    (chat_id, code),
                ).fetchone()
                schedule_id = int(slot["schedule_item_id"]) if slot and slot["schedule_item_id"] is not None else None
                schedule_exists = False
                if schedule_id is not None:
                    schedule_exists = db.execute(
                        "SELECT 1 FROM schedule_items WHERE id=? AND chat_id=?",
                        (schedule_id, chat_id),
                    ).fetchone() is not None
                if not schedule_exists:
                    cur = db.execute(
                        """
                        INSERT INTO schedule_items(
                          chat_id,title,kind,recurrence,date_local,weekdays_mask,start_local,
                          duration_minutes,reminder_minutes,enabled,created_at_utc,updated_at_utc
                        ) VALUES(?,?, 'gym','weekly',NULL,?,?,?,?,1,?,?)
                        """,
                        (chat_id, title, 1 << weekday, start_local, duration, 60, now, now),
                    )
                    schedule_id = int(cur.lastrowid)
                    db.execute(
                        "UPDATE training_plan_slots SET schedule_item_id=?,updated_at_utc=? WHERE chat_id=? AND code=?",
                        (schedule_id, now, chat_id, code),
                    )
                else:
                    db.execute(
                        "UPDATE schedule_items SET enabled=1 WHERE id=? AND chat_id=?",
                        (schedule_id, chat_id),
                    )

            db.execute(
                "UPDATE training_profiles SET plan_enabled=1,updated_at_utc=? WHERE chat_id=?",
                (now, chat_id),
            )
        return self.plan_slots(chat_id)

    def set_plan_enabled(self, chat_id: int, enabled: bool) -> None:
        now = self.iso()
        with self.conn() as db:
            self._ensure_profile(db, chat_id)
            db.execute(
                "UPDATE training_profiles SET plan_enabled=?,updated_at_utc=? WHERE chat_id=?",
                (int(enabled), now, chat_id),
            )
            rows = db.execute(
                "SELECT schedule_item_id FROM training_plan_slots WHERE chat_id=? AND schedule_item_id IS NOT NULL",
                (chat_id,),
            ).fetchall()
            for row in rows:
                db.execute(
                    "UPDATE schedule_items SET enabled=?,updated_at_utc=? WHERE id=? AND chat_id=?",
                    (int(enabled), now, int(row["schedule_item_id"]), chat_id),
                )
                if not enabled:
                    db.execute(
                        "DELETE FROM schedule_occurrences WHERE schedule_item_id=? AND chat_id=? AND status='pending'",
                        (int(row["schedule_item_id"]), chat_id),
                    )

    def sync_slots_from_schedule(self, chat_id: int) -> None:
        """Keep the training dashboard aligned after rules are edited in the weekly editor."""
        now = self.iso()
        with self.conn() as db:
            rows = db.execute(
                """
                SELECT p.code,p.schedule_item_id,s.title,s.weekdays_mask,s.start_local,
                       s.duration_minutes,s.enabled
                FROM training_plan_slots p
                LEFT JOIN schedule_items s ON s.id=p.schedule_item_id AND s.chat_id=p.chat_id
                WHERE p.chat_id=?
                """,
                (chat_id,),
            ).fetchall()
            for row in rows:
                if row["schedule_item_id"] is None or row["title"] is None:
                    continue
                mask = int(row["weekdays_mask"] or 0)
                days = [index for index in range(7) if mask & (1 << index)]
                weekday = days[0] if days else 0
                db.execute(
                    """
                    UPDATE training_plan_slots
                    SET title=?,weekday=?,start_local=?,duration_minutes=?,enabled=?,updated_at_utc=?
                    WHERE chat_id=? AND code=?
                    """,
                    (
                        str(row["title"]), weekday, str(row["start_local"]),
                        int(row["duration_minutes"]), int(bool(row["enabled"])), now,
                        chat_id, str(row["code"]),
                    ),
                )

    def latest_checkin(self, chat_id: int, local_day: date, timezone_name: str) -> sqlite3.Row | None:
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("Europe/Moscow")
        start_local = datetime(local_day.year, local_day.month, local_day.day, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        with self.conn() as db:
            return db.execute(
                """
                SELECT * FROM checkins
                WHERE chat_id=? AND created_at_utc>=? AND created_at_utc<?
                ORDER BY created_at_utc DESC,id DESC LIMIT 1
                """,
                (chat_id, self.iso(start_local), self.iso(end_local)),
            ).fetchone()

    def schedule_context(self, chat_id: int, local_day: date) -> dict[str, Any]:
        with self.conn() as db:
            volleyball = db.execute(
                """
                SELECT COUNT(*) FROM schedule_occurrences
                WHERE chat_id=? AND due_date_local=? AND kind='volleyball' AND status='pending'
                """,
                (chat_id, local_day.isoformat()),
            ).fetchone()[0]
            lower = db.execute(
                """
                SELECT COUNT(*)
                FROM schedule_occurrences o
                JOIN training_plan_slots p ON p.schedule_item_id=o.schedule_item_id AND p.chat_id=o.chat_id
                WHERE o.chat_id=? AND o.due_date_local=? AND p.focus='lower' AND o.status='pending'
                """,
                (chat_id, local_day.isoformat()),
            ).fetchone()[0]
            gym = db.execute(
                """
                SELECT COUNT(*) FROM schedule_occurrences
                WHERE chat_id=? AND due_date_local=? AND kind='gym' AND status='pending'
                """,
                (chat_id, local_day.isoformat()),
            ).fetchone()[0]
        return {"volleyball_today": bool(volleyball), "lower_today": bool(lower), "gym_today": bool(gym)}

    def load_summary(self, chat_id: int, now_utc: datetime | None = None) -> dict[str, float | None]:
        now = (now_utc or self.utcnow()).astimezone(UTC)
        start_7 = self.iso(now - timedelta(days=7))
        start_28 = self.iso(now - timedelta(days=28))
        end_prev = start_7
        start_36 = self.iso(now - timedelta(hours=36))
        with self.conn() as db:
            rows7 = db.execute(
                "SELECT activity,session_load,created_at_utc FROM training_sessions WHERE chat_id=? AND created_at_utc>=? AND result!='skipped'",
                (chat_id, start_7),
            ).fetchall()
            previous = db.execute(
                "SELECT COALESCE(SUM(session_load),0) FROM training_sessions WHERE chat_id=? AND created_at_utc>=? AND created_at_utc<? AND result!='skipped'",
                (chat_id, start_28, end_prev),
            ).fetchone()[0]
            prior_count = db.execute(
                "SELECT COUNT(*) FROM training_sessions WHERE chat_id=? AND created_at_utc>=? AND created_at_utc<? AND result!='skipped'",
                (chat_id, start_28, end_prev),
            ).fetchone()[0]
            rows36 = db.execute(
                "SELECT activity,session_load FROM training_sessions WHERE chat_id=? AND created_at_utc>=? AND result!='skipped'",
                (chat_id, start_36),
            ).fetchall()
        load_7d = float(sum(int(row["session_load"]) for row in rows7))
        lower_36h = float(sum(int(row["session_load"]) * LOWER_FACTORS.get(str(row["activity"]), 0.5) for row in rows36))
        baseline = float(previous) / 3.0 if int(prior_count) >= 3 else None
        return {"load_7d": load_7d, "baseline_weekly_load": baseline, "lower_load_36h": lower_36h}

    def calculate(
        self,
        *,
        chat_id: int,
        local_day: date,
        sleep_hours: float,
        sleep_quality: int,
        energy: int,
        soreness: int,
        pain: int,
        stress: int,
        illness: str,
        red_flag: bool,
    ) -> ReadinessResult:
        context = self.schedule_context(chat_id, local_day)
        loads = self.load_summary(chat_id)
        return evaluate_readiness(
            ReadinessInputs(
                sleep_hours=sleep_hours,
                sleep_quality=sleep_quality,
                energy=energy,
                soreness=soreness,
                pain=pain,
                stress=stress,
                illness=illness,
                red_flag=red_flag,
                volleyball_today=bool(context["volleyball_today"]),
                lower_today=bool(context["lower_today"]),
                lower_load_36h=float(loads["lower_load_36h"] or 0),
                load_7d=float(loads["load_7d"] or 0),
                baseline_weekly_load=loads["baseline_weekly_load"],
            )
        )

    def save_readiness(
        self,
        *,
        chat_id: int,
        local_day: date,
        sleep_hours: float,
        sleep_quality: int,
        energy: int,
        soreness: int,
        pain: int,
        stress: int,
        illness: str,
        red_flag: bool,
    ) -> ReadinessResult:
        result = self.calculate(
            chat_id=chat_id,
            local_day=local_day,
            sleep_hours=sleep_hours,
            sleep_quality=sleep_quality,
            energy=energy,
            soreness=soreness,
            pain=pain,
            stress=stress,
            illness=illness,
            red_flag=red_flag,
        )
        now = self.iso()
        payload = json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True)
        with self.conn() as db:
            db.execute(
                """
                INSERT INTO training_readiness(
                  chat_id,local_date,sleep_hours,sleep_quality,energy,soreness,pain,stress,
                  illness,red_flag,score,status,result_json,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(chat_id,local_date) DO UPDATE SET
                  sleep_hours=excluded.sleep_hours,sleep_quality=excluded.sleep_quality,
                  energy=excluded.energy,soreness=excluded.soreness,pain=excluded.pain,
                  stress=excluded.stress,illness=excluded.illness,red_flag=excluded.red_flag,
                  score=excluded.score,status=excluded.status,result_json=excluded.result_json,
                  updated_at_utc=excluded.updated_at_utc
                """,
                (
                    chat_id, local_day.isoformat(), float(sleep_hours), int(sleep_quality), int(energy),
                    int(soreness), int(pain), int(stress), illness, int(red_flag), result.score,
                    result.status, payload, now, now,
                ),
            )
        return result

    def readiness_for_day(self, chat_id: int, local_day: date) -> dict[str, Any] | None:
        with self.conn() as db:
            row = db.execute(
                "SELECT * FROM training_readiness WHERE chat_id=? AND local_date=?",
                (chat_id, local_day.isoformat()),
            ).fetchone()
        if not row:
            return None
        try:
            result = json.loads(str(row["result_json"]))
        except Exception:
            result = {"score": int(row["score"]), "status": str(row["status"]), "reasons": []}
        return {
            "id": int(row["id"]),
            "localDate": str(row["local_date"]),
            "sleepHours": float(row["sleep_hours"]),
            "sleepQuality": int(row["sleep_quality"]),
            "energy": int(row["energy"]),
            "soreness": int(row["soreness"]),
            "pain": int(row["pain"]),
            "stress": int(row["stress"]),
            "illness": str(row["illness"]),
            "redFlag": bool(row["red_flag"]),
            "result": result,
            "updatedAt": str(row["updated_at_utc"]),
        }

    def log_session(
        self,
        *,
        chat_id: int,
        local_day: date,
        activity: str,
        duration_minutes: int,
        rpe: int,
        result: str,
        pain_after: int,
        jumps: int | None = None,
        notes: str = "",
        source: str = "telegram",
    ) -> int:
        if activity not in ACTIVITY_LABELS:
            raise ValueError("invalid activity")
        duration = int(duration_minutes)
        if not 1 <= duration <= 720:
            raise ValueError("duration out of range")
        rpe_value = int(rpe)
        if not 0 <= rpe_value <= 10:
            raise ValueError("rpe out of range")
        if result not in {"done", "partial", "skipped"}:
            raise ValueError("invalid result")
        pain_value = int(pain_after)
        if not 0 <= pain_value <= 3:
            raise ValueError("pain_after out of range")
        jumps_value = int(jumps) if jumps is not None else None
        if jumps_value is not None and not 0 <= jumps_value <= 2000:
            raise ValueError("jumps out of range")
        load = 0 if result == "skipped" else duration * rpe_value
        with self.conn() as db:
            cur = db.execute(
                """
                INSERT INTO training_sessions(
                  chat_id,activity,planned_date_local,duration_minutes,rpe,session_load,
                  result,pain_after,jumps,notes,source,created_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    chat_id, activity, local_day.isoformat(), duration, rpe_value, load, result,
                    pain_value, jumps_value, notes.strip()[:500], source, self.iso(),
                ),
            )
            session_id = int(cur.lastrowid)
            if result in {"done", "partial"}:
                self._mark_matching_schedule(db, chat_id, local_day, activity)
        return session_id

    def _mark_matching_schedule(self, db: sqlite3.Connection, chat_id: int, local_day: date, activity: str) -> None:
        if activity in {"upper_a", "lower_a", "upper_b", "lower_b"}:
            row = db.execute(
                "SELECT schedule_item_id FROM training_plan_slots WHERE chat_id=? AND code=?",
                (chat_id, activity),
            ).fetchone()
            if row and row["schedule_item_id"] is not None:
                db.execute(
                    """
                    UPDATE schedule_occurrences SET status='done',completed_at_utc=?
                    WHERE chat_id=? AND schedule_item_id=? AND due_date_local=? AND status='pending'
                    """,
                    (self.iso(), chat_id, int(row["schedule_item_id"]), local_day.isoformat()),
                )
        elif activity == "volleyball":
            row = db.execute(
                """
                SELECT id FROM schedule_occurrences
                WHERE chat_id=? AND due_date_local=? AND kind='volleyball' AND status='pending'
                ORDER BY start_at_utc,id LIMIT 1
                """,
                (chat_id, local_day.isoformat()),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE schedule_occurrences SET status='done',completed_at_utc=? WHERE id=? AND chat_id=?",
                    (self.iso(), int(row["id"]), chat_id),
                )

    def recent_sessions(self, chat_id: int, limit: int = 12) -> list[TrainingSession]:
        with self.conn() as db:
            rows = db.execute(
                "SELECT * FROM training_sessions WHERE chat_id=? ORDER BY created_at_utc DESC,id DESC LIMIT ?",
                (chat_id, max(1, min(100, int(limit)))),
            ).fetchall()
        return [self._session(row) for row in rows]

    def upcoming_training(self, chat_id: int, start_day: date, days: int = 7) -> list[dict[str, Any]]:
        end_day = start_day + timedelta(days=max(1, days) - 1)
        with self.conn() as db:
            rows = db.execute(
                """
                SELECT o.id,o.schedule_item_id,o.due_date_local,o.title,o.kind,o.start_at_utc,
                       o.end_at_utc,o.status,p.code,p.focus
                FROM schedule_occurrences o
                LEFT JOIN training_plan_slots p ON p.schedule_item_id=o.schedule_item_id AND p.chat_id=o.chat_id
                WHERE o.chat_id=? AND o.due_date_local BETWEEN ? AND ?
                  AND (p.code IS NOT NULL OR o.kind='volleyball')
                ORDER BY o.start_at_utc,o.id
                """,
                (chat_id, start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
        return [
            {
                "occurrenceId": int(row["id"]),
                "scheduleItemId": int(row["schedule_item_id"]),
                "dueDate": str(row["due_date_local"]),
                "title": str(row["title"]),
                "kind": str(row["kind"]),
                "startAt": str(row["start_at_utc"]),
                "endAt": str(row["end_at_utc"]),
                "status": str(row["status"]),
                "code": str(row["code"]) if row["code"] is not None else "volleyball",
                "focus": str(row["focus"]) if row["focus"] is not None else "volleyball",
            }
            for row in rows
        ]

    def notification_sent(self, chat_id: int, key: str) -> bool:
        with self.conn() as db:
            return db.execute(
                "SELECT 1 FROM training_notifications WHERE chat_id=? AND notification_key=?",
                (chat_id, key),
            ).fetchone() is not None

    def mark_notification(self, chat_id: int, key: str) -> None:
        with self.conn() as db:
            db.execute(
                "INSERT OR IGNORE INTO training_notifications(chat_id,notification_key,sent_at_utc) VALUES(?,?,?)",
                (chat_id, key, self.iso()),
            )

    def command_seen(self, command_id: str) -> bool:
        with self.conn() as db:
            return db.execute("SELECT 1 FROM training_web_commands WHERE command_id=?", (command_id,)).fetchone() is not None

    def remember_command(self, command_id: str, chat_id: int, action: str, result: str, detail: str = "") -> None:
        with self.conn() as db:
            db.execute(
                "INSERT OR IGNORE INTO training_web_commands(command_id,chat_id,action,result,detail,processed_at_utc) VALUES(?,?,?,?,?,?)",
                (command_id, chat_id, action, result, detail[:500], self.iso()),
            )

    def _slot(self, row: sqlite3.Row) -> TrainingPlanSlot:
        return TrainingPlanSlot(
            chat_id=int(row["chat_id"]),
            code=str(row["code"]),
            title=str(row["title"]),
            focus=str(row["focus"]),
            weekday=int(row["weekday"]),
            start_local=str(row["start_local"]),
            duration_minutes=int(row["duration_minutes"]),
            schedule_item_id=int(row["schedule_item_id"]) if row["schedule_item_id"] is not None else None,
            enabled=bool(row["enabled"]),
            sort_order=int(row["sort_order"]),
        )

    def _session(self, row: sqlite3.Row) -> TrainingSession:
        return TrainingSession(
            id=int(row["id"]),
            chat_id=int(row["chat_id"]),
            activity=str(row["activity"]),
            planned_date_local=str(row["planned_date_local"]),
            duration_minutes=int(row["duration_minutes"]),
            rpe=int(row["rpe"]),
            session_load=int(row["session_load"]),
            result=str(row["result"]),
            pain_after=int(row["pain_after"]),
            jumps=int(row["jumps"]) if row["jumps"] is not None else None,
            created_at_utc=str(row["created_at_utc"]),
        )
