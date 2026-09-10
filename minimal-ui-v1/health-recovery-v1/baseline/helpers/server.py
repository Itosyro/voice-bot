#!/usr/bin/env python3
"""DVIZH single-node server.

Serves the PWA and keeps one synchronized JSON state per exe.dev user in SQLite.
Only Python's standard library is required.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import mimetypes
import os
import pathlib
import posixpath
import sqlite3
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

APP_VERSION = "2026.08.28-sync.1"
MAX_BODY_BYTES = 2 * 1024 * 1024
LOG = logging.getLogger("dvizh")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


class StateStore:
    def __init__(self, db_path: pathlib.Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_state (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS state_history (
                    user_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, revision)
                );

                CREATE INDEX IF NOT EXISTS idx_state_history_user_revision
                ON state_history(user_id, revision DESC);
                """
            )

    def get(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT email, revision, state_json, updated_at FROM user_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "email": row["email"],
            "revision": int(row["revision"]),
            "state": json.loads(row["state_json"]),
            "updatedAt": row["updated_at"],
        }

    def put(
        self,
        user_id: str,
        email: str,
        state: dict[str, Any],
        base_revision: int,
        force: bool = False,
    ) -> tuple[bool, dict[str, Any]]:
        state_json = compact_json(state)
        now = utc_now()
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT email, revision, state_json, updated_at FROM user_state WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                current_revision = int(row["revision"]) if row else 0

                if row is not None and not force and base_revision != current_revision:
                    conn.execute("ROLLBACK")
                    return False, {
                        "email": row["email"],
                        "revision": current_revision,
                        "state": json.loads(row["state_json"]),
                        "updatedAt": row["updated_at"],
                    }

                if row is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO state_history(user_id, revision, state_json, created_at) VALUES (?, ?, ?, ?)",
                        (user_id, current_revision, row["state_json"], now),
                    )

                next_revision = current_revision + 1
                conn.execute(
                    """
                    INSERT INTO user_state(user_id, email, revision, state_json, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        email = excluded.email,
                        revision = excluded.revision,
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (user_id, email or "", next_revision, state_json, now),
                )
                # Keep a compact rolling history per user.
                conn.execute(
                    """
                    DELETE FROM state_history
                    WHERE user_id = ? AND revision NOT IN (
                        SELECT revision FROM state_history
                        WHERE user_id = ? ORDER BY revision DESC LIMIT 100
                    )
                    """,
                    (user_id, user_id),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        return True, {
            "email": email or "",
            "revision": next_revision,
            "state": state,
            "updatedAt": now,
        }

    def delete(self, user_id: str) -> None:
        with self._write_lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT revision, state_json FROM user_state WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row is not None:
                    conn.execute(
                        "INSERT OR IGNORE INTO state_history(user_id, revision, state_json, created_at) VALUES (?, ?, ?, ?)",
                        (user_id, int(row["revision"]), row["state_json"], utc_now()),
                    )
                    conn.execute("DELETE FROM user_state WHERE user_id = ?", (user_id,))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            users = int(conn.execute("SELECT COUNT(*) FROM user_state").fetchone()[0])
            history = int(conn.execute("SELECT COUNT(*) FROM state_history").fetchone()[0])
        return {"users": users, "historySnapshots": history}


class DVIZHServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler], *, store: StateStore, static_dir: pathlib.Path):
        super().__init__(server_address, handler)
        self.store = store
        self.static_dir = static_dir.resolve()
        self.started_at = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    server: DVIZHServer
    protocol_version = "HTTP/1.1"
    server_version = "DVIZH"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def _json(self, status: int, payload: Any, *, extra_headers: dict[str, str] | None = None) -> None:
        body = compact_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(self), geolocation=(), payment=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; manifest-src 'self'; worker-src 'self';",
        )

    def _user(self) -> tuple[str, str] | None:
        user_id = (self.headers.get("X-ExeDev-UserID") or "").strip()
        email = (self.headers.get("X-ExeDev-Email") or "").strip()
        if not user_id:
            return None
        return user_id[:256], email[:320]

    def _require_user(self) -> tuple[str, str] | None:
        user = self._user()
        if user is None:
            self._json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "ok": False,
                    "error": "authentication_required",
                    "message": "Откройте приложение через приватный адрес exe.dev и войдите в аккаунт.",
                },
            )
            return None
        return user

    def _read_json(self) -> Any:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("missing_content_length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid_content_length") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise OverflowError("body_too_large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_json") from exc

    @staticmethod
    def _validate_state(state: Any) -> dict[str, Any]:
        if not isinstance(state, dict):
            raise ValueError("state_must_be_object")
        if state.get("version") != 1:
            raise ValueError("unsupported_state_version")
        tasks = state.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("tasks_must_be_array")
        # Keep malformed or runaway clients from filling the disk.
        if len(tasks) > 10000:
            raise ValueError("too_many_tasks")
        return state

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/health":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            return
        self._serve_static(parsed.path, head_only=True)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        if path == "/api/health":
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "app": "dvizh",
                    "version": APP_VERSION,
                    "uptimeSeconds": int(time.monotonic() - self.server.started_at),
                    **self.server.store.stats(),
                },
            )
            return
        if path == "/api/me":
            user = self._require_user()
            if user is None:
                return
            user_id, email = user
            self._json(HTTPStatus.OK, {"ok": True, "userId": user_id, "email": email})
            return
        if path == "/api/state":
            user = self._require_user()
            if user is None:
                return
            user_id, email = user
            record = self.server.store.get(user_id)
            if record is None:
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "state": None, "revision": 0, "email": email, "serverTime": utc_now()},
                )
            else:
                self._json(HTTPStatus.OK, {"ok": True, **record, "serverTime": utc_now()})
            return
        if path == "/api/export":
            user = self._require_user()
            if user is None:
                return
            user_id, _email = user
            record = self.server.store.get(user_id)
            if record is None:
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "no_state"})
                return
            body = json.dumps(record["state"], ensure_ascii=False, indent=2).encode("utf-8")
            date = dt.date.today().isoformat()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="dvizh-server-backup-{date}.json"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        self._serve_static(path)

    def do_PUT(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/state":
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        user = self._require_user()
        if user is None:
            return
        user_id, email = user
        try:
            payload = self._read_json()
            if not isinstance(payload, dict):
                raise ValueError("payload_must_be_object")
            state = self._validate_state(payload.get("state"))
            base_revision = int(payload.get("baseRevision", 0))
            if base_revision < 0:
                raise ValueError("invalid_base_revision")
            force = bool(payload.get("force", False))
        except OverflowError:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "body_too_large"})
            return
        except (ValueError, TypeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        accepted, record = self.server.store.put(user_id, email, state, base_revision, force=force)
        status = HTTPStatus.OK if accepted else HTTPStatus.CONFLICT
        self._json(status, {"ok": accepted, **record, "serverTime": utc_now()})

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/state":
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        user = self._require_user()
        if user is None:
            return
        user_id, _email = user
        self.server.store.delete(user_id)
        self._json(HTTPStatus.OK, {"ok": True, "revision": 0, "serverTime": utc_now()})

    def do_POST(self) -> None:  # noqa: N802
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "method_not_allowed"})

    def _serve_static(self, request_path: str, *, head_only: bool = False) -> None:
        decoded = urllib.parse.unquote(request_path)
        normalized = posixpath.normpath(decoded)
        if normalized.startswith("../") or "/../" in normalized:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return
        relative = normalized.lstrip("/")
        if not relative or relative.endswith("/"):
            relative = posixpath.join(relative, "index.html")
        candidate = (self.server.static_dir / relative).resolve()
        try:
            candidate.relative_to(self.server.static_dir)
        except ValueError:
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        # SPA fallback for clean paths, while preserving real 404s for assets.
        if not candidate.is_file() and "." not in pathlib.PurePosixPath(relative).name:
            candidate = self.server.static_dir / "index.html"
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
            return

        data = candidate.read_bytes()
        mime, _ = mimetypes.guess_type(candidate.name)
        if candidate.suffix == ".webmanifest":
            mime = "application/manifest+json"
        mime = mime or "application/octet-stream"
        etag = '"' + hashlib.sha256(data).hexdigest()[:24] + '"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self._security_headers()
            self.end_headers()
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith("text/") or mime in {"application/javascript", "application/manifest+json"} else mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        if candidate.name in {"index.html", "app.js", "styles.css", "sw.js", "manifest.webmanifest"}:
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=604800, immutable")
        if candidate.name == "sw.js":
            self.send_header("Service-Worker-Allowed", "/")
        self._security_headers()
        self.end_headers()
        if not head_only:
            self.wfile.write(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve DVIZH and its sync API")
    parser.add_argument("--host", default=os.getenv("DVIZH_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DVIZH_PORT", "8000")))
    parser.add_argument("--db", type=pathlib.Path, default=pathlib.Path(os.getenv("DVIZH_DB", "/var/lib/dvizh/dvizh.db")))
    parser.add_argument("--static", type=pathlib.Path, default=pathlib.Path(os.getenv("DVIZH_STATIC", "/opt/dvizh/static")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=os.getenv("DVIZH_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not args.static.is_dir():
        raise SystemExit(f"Static directory does not exist: {args.static}")
    store = StateStore(args.db)
    server = DVIZHServer((args.host, args.port), Handler, store=store, static_dir=args.static)
    LOG.info("DVIZH %s listening on http://%s:%s", APP_VERSION, args.host, args.port)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
