from __future__ import annotations

import importlib.util
import json
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "bridge.py"
spec = importlib.util.spec_from_file_location("dvizh_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader
import sys
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)


def create_web_db(path: Path, state: dict) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE user_states(user_id TEXT PRIMARY KEY,email TEXT,revision INTEGER,state_json TEXT,updated_at TEXT)"
        )
        db.execute(
            "INSERT INTO user_states VALUES(?,?,?,?,?)",
            ("exe-user-1", "owner@example.com", 1, json.dumps(state), datetime.now(timezone.utc).isoformat()),
        )


def create_telegram_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE users(chat_id INTEGER PRIMARY KEY, telegram_user_id INTEGER, username TEXT, first_name TEXT,
              timezone TEXT, quiet_start TEXT, quiet_end TEXT, authorized INTEGER, pending_occurrence_id INTEGER,
              created_at_utc TEXT, updated_at_utc TEXT);
            CREATE TABLE checkins(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,energy INTEGER,body INTEGER,stress INTEGER,created_at_utc TEXT);
            CREATE TABLE recurring_tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,title TEXT,microstep TEXT,area TEXT,
              weekdays_mask INTEGER,time_local TEXT,min_minutes INTEGER,normal_minutes INTEGER,energy_cost INTEGER,enabled INTEGER,
              created_at_utc TEXT,updated_at_utc TEXT);
            CREATE TABLE occurrences(id INTEGER PRIMARY KEY AUTOINCREMENT,recurring_task_id INTEGER,chat_id INTEGER,due_date_local TEXT,
              title TEXT,microstep TEXT,area TEXT,scheduled_at_utc TEXT,min_minutes INTEGER,normal_minutes INTEGER,energy_cost INTEGER,
              status TEXT,snoozed_until_utc TEXT,reminder_sent_at_utc TEXT,followup_sent_at_utc TEXT,completed_at_utc TEXT,created_at_utc TEXT);
            CREATE TABLE focus_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,occurrence_id INTEGER,source TEXT,
              planned_minutes INTEGER,started_at_utc TEXT,due_at_utc TEXT,finished_at_utc TEXT,result TEXT,result_prompt_sent_at_utc TEXT);
            CREATE TABLE event_log(id INTEGER PRIMARY KEY AUTOINCREMENT,chat_id INTEGER,event_type TEXT,payload_json TEXT,created_at_utc TEXT);
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        day = datetime.now(timezone.utc).date().isoformat()
        db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?,?,?,?,?)", (123, 123, "u", "U", "UTC", "23:00", "09:00", 1, None, now, now))
        db.execute("INSERT INTO checkins(chat_id,energy,body,stress,created_at_utc) VALUES(?,?,?,?,?)", (123, 2, 1, 0, now))
        db.execute("INSERT INTO recurring_tasks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (1, 123, "ПДД", "3 вопроса", "pdd", 127, "12:18", 5, 20, 0, 1, now, now))
        db.execute("INSERT INTO occurrences VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (1, 1, 123, day, "ПДД", "3 вопроса", "pdd", now, 5, 20, 0, "done", None, now, None, now, now))
        db.execute("INSERT INTO focus_sessions VALUES(?,?,?,?,?,?,?,?,?,?)", (1, 123, 1, "reminder", 8, now, now, now, "done", now))
        db.execute("INSERT INTO event_log(chat_id,event_type,payload_json,created_at_utc) VALUES(?,?,?,?)", (123, "focus_finished", "{}", now))


class StateServer:
    def __init__(self, state: dict):
        self.state = state
        self.revision = 1
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def send_json(self, payload, status=200):
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                assert self.headers["X-ExeDev-UserID"] == "exe-user-1"
                if self.path == "/api/health":
                    self.send_json({"ok": True, "app": "dvizh"})
                elif self.path == "/api/state":
                    self.send_json({"ok": True, "revision": owner.revision, "state": owner.state})
                else:
                    self.send_json({"ok": False}, 404)

            def do_PUT(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                if payload["baseRevision"] != owner.revision:
                    self.send_json({"ok": False, "revision": owner.revision}, 409)
                    return
                owner.state = payload["state"]
                owner.revision += 1
                self.send_json({"ok": True, "revision": owner.revision})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()


def test_sync(tmp_path: Path):
    state = {"version": 1, "tasks": [], "sessions": [], "proofs": [], "checkins": {}, "plans": {}, "ladder": {}}
    web_db = tmp_path / "web.db"
    telegram_db = tmp_path / "telegram.db"
    status = tmp_path / "status.json"
    create_web_db(web_db, state)
    create_telegram_db(telegram_db)

    with StateServer(state) as server:
        config = bridge.Config(
            telegram_db=str(telegram_db),
            web_db=str(web_db),
            web_api=server.url,
            web_user_id="",
            web_user_email="",
            interval_seconds=20,
            lookback_days=30,
            status_path=str(status),
            sync_signal_path=str(tmp_path / "signal"),
            timeout_seconds=3,
        )
        identity = bridge.discover_identity(config)
        assert identity.user_id == "exe-user-1"
        result = bridge.sync_once(config)
        assert result["ok"] is True
        assert result["changed"] is True
        assert server.state["tasks"][0]["title"] == "ПДД"
        assert server.state["tasks"][0]["done"] is True
        assert server.state["sessions"][0]["minutes"] == 8
        assert server.state["proofs"][0]["source"] == "telegram"
        assert server.state["checkins"]

        second = bridge.sync_once(config)
        assert second["changed"] is False


def test_web_completion_import(tmp_path: Path):
    state = {
        "version": 1,
        "tasks": [{"id": "tg-occ-123-1", "title": "ПДД", "done": True}],
        "sessions": [],
        "proofs": [],
        "checkins": {},
        "plans": {},
        "ladder": {},
    }
    web_db = tmp_path / "web.db"
    telegram_db = tmp_path / "telegram.db"
    create_web_db(web_db, state)
    create_telegram_db(telegram_db)
    with sqlite3.connect(telegram_db) as db:
        db.execute("UPDATE occurrences SET status='pending',completed_at_utc=NULL WHERE id=1")

    with StateServer(state) as server:
        config = bridge.Config(str(telegram_db), str(web_db), server.url, "", "", 20, 30, str(tmp_path / "s"), str(tmp_path / "sig"), 3)
        result = bridge.sync_once(config)
        assert result["webDoneImported"] == 1
    with sqlite3.connect(telegram_db) as db:
        assert db.execute("SELECT status FROM occurrences WHERE id=1").fetchone()[0] == "done"
