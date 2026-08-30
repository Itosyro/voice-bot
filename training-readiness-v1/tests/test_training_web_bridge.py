from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dvizh_training_test import training_web_bridge as bridge


def make_db(path: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
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
            (7, 7, "u", "U", "UTC", "23:00", "09:00", 1, None, now, now),
        )


class StateServer:
    def __init__(self, state: dict):
        self.state = state
        self.revision = 1
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def send_json(self, payload: dict, status: int = 200) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                assert self.headers.get("X-ExeDev-UserID") == "local-user-1"
                if self.path == "/api/health":
                    self.send_json({"ok": True})
                elif self.path == "/api/state":
                    self.send_json({"ok": True, "revision": owner.revision, "state": owner.state})
                else:
                    self.send_json({"ok": False}, 404)

            def do_PUT(self):
                size = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(size))
                if payload["baseRevision"] != owner.revision:
                    self.send_json({"ok": False, "revision": owner.revision}, 409)
                    return
                owner.state = payload["state"]
                owner.revision += 1
                self.send_json({"ok": True, "revision": owner.revision})

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.http.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.http.shutdown()
        self.thread.join(timeout=2)
        self.http.server_close()


def base_state(commands: list[dict]) -> dict:
    return {
        "version": 1,
        "tasks": [],
        "sessions": [],
        "proofs": [],
        "checkins": {},
        "plans": {},
        "ladder": {},
        "trainingHub": {"webCommands": commands},
    }


def test_web_commands_create_plan_readiness_and_session(tmp_path: Path):
    db_path = tmp_path / "telegram.db"
    identity_path = tmp_path / "auth-identity.json"
    make_db(db_path)
    identity_path.write_text(json.dumps({"user_id": "local-user-1", "email": "u@example.com"}), encoding="utf-8")
    commands = [
        {"id": "cmd-plan", "action": "plan_enable"},
        {
            "id": "cmd-ready",
            "action": "readiness_save",
            "sleepHours": 8,
            "sleepQuality": 3,
            "energy": 3,
            "soreness": 0,
            "pain": 0,
            "stress": 0,
            "illness": "none",
            "redFlag": False,
        },
        {
            "id": "cmd-session",
            "action": "session_log",
            "activity": "volleyball",
            "durationMinutes": 60,
            "rpe": 7,
            "result": "done",
            "painAfter": 1,
            "jumps": 45,
        },
    ]
    with StateServer(base_state(commands)) as server:
        config = bridge.Config(
            telegram_db=str(db_path),
            web_api=server.url,
            bridge_env=str(tmp_path / "missing.env"),
            identity_json=str(identity_path),
            status_path=str(tmp_path / "status.json"),
            interval_seconds=5,
            timeout_seconds=3,
        )
        first = bridge.sync_once(config)
        assert first["ok"] is True
        assert first["changed"] is True
        hub = server.state["trainingHub"]
        assert hub["profile"]["planEnabled"] is True
        assert len(hub["planSlots"]) == 4
        assert hub["readiness"]["result"]["status"] == "green"
        assert hub["sessions"][0]["load"] == 420
        assert hub["sessions"][0]["jumps"] == 45
        assert hub["webCommands"] == []
        assert {row["id"] for row in hub["commandResults"]} == {"cmd-plan", "cmd-ready", "cmd-session"}

        with sqlite3.connect(db_path) as db:
            assert db.execute("SELECT COUNT(*) FROM training_plan_slots").fetchone()[0] == 4
            assert db.execute("SELECT COUNT(*) FROM training_sessions").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM training_web_commands").fetchone()[0] == 3

        # One settling pass may remove transient command results; after that the
        # projection must be stable and commands must never replay.
        bridge.sync_once(config)
        stable = bridge.sync_once(config)
        assert stable["ok"] is True
        assert stable["changed"] is False
        with sqlite3.connect(db_path) as db:
            assert db.execute("SELECT COUNT(*) FROM training_sessions").fetchone()[0] == 1
            assert db.execute("SELECT COUNT(*) FROM schedule_items WHERE kind='gym'").fetchone()[0] == 4


def test_duplicate_command_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "telegram.db"
    identity_path = tmp_path / "auth-identity.json"
    make_db(db_path)
    identity_path.write_text(json.dumps({"user_id": "local-user-1"}), encoding="utf-8")
    command = {
        "id": "same-command",
        "action": "session_log",
        "activity": "upper_a",
        "durationMinutes": 45,
        "rpe": 6,
        "result": "done",
        "painAfter": 0,
    }
    with StateServer(base_state([command])) as server:
        config = bridge.Config(str(db_path), server.url, str(tmp_path / "none"), str(identity_path), str(tmp_path / "status"), 5, 3)
        bridge.sync_once(config)
        # Put the exact same command back into web state as if a stale browser retried it.
        server.state["trainingHub"]["webCommands"] = [command]
        server.revision += 1
        bridge.sync_once(config)
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM training_sessions").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM training_web_commands WHERE command_id='same-command'").fetchone()[0] == 1
