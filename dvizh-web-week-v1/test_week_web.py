from __future__ import annotations

import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from week_web import WeekStore, WeekWeb, inject_main_entry

SCHEMA = '''
CREATE TABLE users(chat_id INTEGER PRIMARY KEY, timezone TEXT, authorized INTEGER);
CREATE TABLE schedule_items (
 id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER NOT NULL,title TEXT NOT NULL,kind TEXT NOT NULL,
 recurrence TEXT NOT NULL,date_local TEXT,weekdays_mask INTEGER,start_local TEXT NOT NULL,duration_minutes INTEGER NOT NULL,
 reminder_minutes INTEGER NOT NULL DEFAULT 30,enabled INTEGER NOT NULL DEFAULT 1,created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL
);
CREATE TABLE schedule_occurrences (
 id INTEGER PRIMARY KEY AUTOINCREMENT,schedule_item_id INTEGER NOT NULL,chat_id INTEGER NOT NULL,due_date_local TEXT NOT NULL,
 title TEXT NOT NULL,kind TEXT NOT NULL,start_at_utc TEXT NOT NULL,end_at_utc TEXT NOT NULL,reminder_minutes INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending',reminder_sent_at_utc TEXT,snoozed_until_utc TEXT,completed_at_utc TEXT,created_at_utc TEXT NOT NULL,
 UNIQUE(schedule_item_id,due_date_local),FOREIGN KEY(schedule_item_id) REFERENCES schedule_items(id) ON DELETE CASCADE
);
'''


def test_shared_week_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as td:
        dbp = Path(td) / 'telegram.db'
        with sqlite3.connect(dbp) as db:
            db.executescript(SCHEMA)
            db.execute("INSERT INTO users VALUES(123,'Europe/Moscow',1)")

        store = WeekStore(str(dbp))
        store.ensure_schema()
        user = store.user()
        today = date(2026, 8, 29)
        once_id = store.add_item(user, {
            'title': 'Встреча', 'kind': 'friend', 'recurrence': 'once', 'date_local': '2026-08-29',
            'weekdays': '', 'time_local': '18:30', 'duration': '60', 'reminder': '30'
        }, today)
        weekly_id = store.add_item(user, {
            'title': 'Зал верх', 'kind': 'gym', 'recurrence': 'weekly', 'date_local': '',
            'weekdays': 'пн чт', 'time_local': '19:00', 'duration': '90', 'reminder': '60'
        }, today)
        assert once_id and weekly_id
        store.ensure_range(user, today, 7)
        occs = store.occurrences(user, today, 7)
        assert any(row['title'] == 'Встреча' for row in occs)
        assert any(row['title'] == 'Зал верх' for row in occs)

        first = int(occs[0]['id'])
        store.occurrence_action(user, first, 'done')
        assert store.occurrences(user, today, 7)[0]['status'] == 'done'
        store.item_action(user, weekly_id, 'pause')
        assert [row for row in store.items(user) if row['id'] == weekly_id][0]['enabled'] == 0

        injected = inject_main_entry(b'<html><body>app</body></html>', 'text/html; charset=utf-8', '/')
        assert b'dvizh-week-shortcut' in injected and b'/week' in injected
        page = WeekWeb(str(dbp)).page(SimpleNamespace(csrf_token='csrf'), today)
        assert 'Встреча'.encode() in page
        assert 'Зал верх'.encode() in page
