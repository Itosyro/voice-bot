from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from dvizh_training_test.training_store import TrainingStore


def make_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE users(
              chat_id INTEGER PRIMARY KEY,telegram_user_id INTEGER,username TEXT,first_name TEXT,
              timezone TEXT,quiet_start TEXT,quiet_end TEXT,authorized INTEGER,pending_occurrence_id INTEGER,
              created_at_utc TEXT,updated_at_utc TEXT
            );
            CREATE TABLE checkins(
              id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,energy INTEGER,body INTEGER,stress INTEGER,created_at_utc TEXT
            );
            CREATE TABLE schedule_items(
              id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,
              recurrence TEXT NOT NULL,date_local TEXT,weekdays_mask INTEGER,start_local TEXT NOT NULL,
              duration_minutes INTEGER NOT NULL,reminder_minutes INTEGER NOT NULL,enabled INTEGER NOT NULL,
              created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE schedule_occurrences(
              id INTEGER PRIMARY KEY AUTOINCREMENT,schedule_item_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,
              due_date_local TEXT NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,start_at_utc TEXT NOT NULL,
              end_at_utc TEXT NOT NULL,reminder_minutes INTEGER NOT NULL,status TEXT NOT NULL,
              reminder_sent_at_utc TEXT,snoozed_until_utc TEXT,completed_at_utc TEXT,created_at_utc TEXT NOT NULL,
              UNIQUE(schedule_item_id,due_date_local)
            );
            """
        )
        db.execute(
            "INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (7, 7, "u", "U", "Europe/Moscow", "23:00", "09:00", 1, None, "2026-08-30T00:00:00+00:00", "2026-08-30T00:00:00+00:00"),
        )


def test_default_plan_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "telegram.db"
    make_db(db_path)
    store = TrainingStore(str(db_path))
    first = store.ensure_default_plan(7)
    second = store.ensure_default_plan(7)
    assert len(first) == 4
    assert len(second) == 4
    with store.conn() as db:
        assert db.execute("SELECT COUNT(*) FROM training_plan_slots WHERE chat_id=7").fetchone()[0] == 4
        assert db.execute("SELECT COUNT(*) FROM schedule_items WHERE chat_id=7 AND kind='gym'").fetchone()[0] == 4
        assert db.execute("SELECT plan_enabled FROM training_profiles WHERE chat_id=7").fetchone()[0] == 1


def test_readiness_and_session_load(tmp_path: Path):
    db_path = tmp_path / "telegram.db"
    make_db(db_path)
    store = TrainingStore(str(db_path))
    day = date(2026, 8, 30)
    readiness = store.save_readiness(
        chat_id=7,
        local_day=day,
        sleep_hours=8,
        sleep_quality=3,
        energy=3,
        soreness=0,
        pain=0,
        stress=0,
        illness="none",
        red_flag=False,
    )
    assert readiness.status == "green"
    saved = store.readiness_for_day(7, day)
    assert saved is not None
    assert saved["result"]["score"] == readiness.score

    session_id = store.log_session(
        chat_id=7,
        local_day=day,
        activity="volleyball",
        duration_minutes=60,
        rpe=7,
        result="done",
        pain_after=1,
        jumps=50,
    )
    assert session_id > 0
    recent = store.recent_sessions(7)
    assert recent[0].session_load == 420
    assert recent[0].jumps == 50
    loads = store.load_summary(7)
    assert loads["load_7d"] == 420
    assert loads["lower_load_36h"] == 420


def test_plan_pause_drops_only_future_pending(tmp_path: Path):
    db_path = tmp_path / "telegram.db"
    make_db(db_path)
    store = TrainingStore(str(db_path))
    slots = store.ensure_default_plan(7)
    item_id = slots[0].schedule_item_id
    assert item_id is not None
    with store.conn() as db:
        db.execute(
            """
            INSERT INTO schedule_occurrences(
              schedule_item_id,chat_id,due_date_local,title,kind,start_at_utc,end_at_utc,
              reminder_minutes,status,created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (item_id, 7, "2026-08-31", "Силовая · Верх A", "gym", "2026-08-31T16:00:00+00:00", "2026-08-31T17:15:00+00:00", 60, "pending", "2026-08-30T00:00:00+00:00"),
        )
        db.execute(
            """
            INSERT INTO schedule_occurrences(
              schedule_item_id,chat_id,due_date_local,title,kind,start_at_utc,end_at_utc,
              reminder_minutes,status,completed_at_utc,created_at_utc
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (item_id, 7, "2026-08-24", "Силовая · Верх A", "gym", "2026-08-24T16:00:00+00:00", "2026-08-24T17:15:00+00:00", 60, "done", "2026-08-24T17:15:00+00:00", "2026-08-24T00:00:00+00:00"),
        )
    store.set_plan_enabled(7, False)
    with store.conn() as db:
        assert db.execute("SELECT COUNT(*) FROM schedule_occurrences WHERE status='pending'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM schedule_occurrences WHERE status='done'").fetchone()[0] == 1
