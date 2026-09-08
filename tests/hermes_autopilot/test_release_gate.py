from __future__ import annotations

import hashlib
import http.server
import importlib.util
import json
import os
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "hermes-dev-v2" / "dvizhrelease.py"


def blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def load_gate(tmp: Path, source: Path, fsroot: Path, approvals: Path, backups: Path, http_base: str):
    keys = {
        "DVIZH_RELEASE_TEST_MODE": "1",
        "DVIZH_RELEASE_SOURCE_ROOT": str(source),
        "DVIZH_RELEASE_FS_ROOT": str(fsroot),
        "DVIZH_RELEASE_APPROVAL_ROOT": str(approvals),
        "DVIZH_RELEASE_BACKUP_ROOT": str(backups),
        "DVIZH_RELEASE_HTTP_BASE": http_base,
    }
    old = os.environ.copy(); os.environ.update(keys)
    spec = importlib.util.spec_from_file_location(f"dvizhrelease_test_{id(tmp)}", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    os.environ.clear(); os.environ.update(old)
    return module


class FixtureServer:
    def __init__(self, fsroot: Path, stale_root: bytes | None = None):
        self.fsroot = fsroot
        self.stale_root = stale_root
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlsplit(self.path).path
                if path == "/" and outer.stale_root is not None:
                    body = outer.stale_root
                elif path == "/":
                    body = (outer.fsroot / "opt/dvizh/static/index.html").read_bytes()
                else:
                    target = outer.fsroot / path.lstrip("/")
                    # Public HTTP paths map into /opt/dvizh/static.
                    if not target.is_file():
                        target = outer.fsroot / "opt/dvizh/static" / path.lstrip("/")
                    if not target.is_file():
                        self.send_response(404); self.end_headers(); return
                    body = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base(self):
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def __enter__(self):
        self.thread.start(); return self

    def __exit__(self, *exc):
        self.httpd.shutdown(); self.httpd.server_close(); self.thread.join(timeout=5)


def make_fixture(td: str, *, mode: str = "auto", target: str = "/opt/dvizh/static/index.html", http_path: str = "/"):
    root = Path(td)
    source = root / "source"; fsroot = root / "fs"; approvals = root / "approvals"; backups = root / "backups"
    source.mkdir(); (fsroot / "opt/dvizh/static").mkdir(parents=True)
    new = b"<!doctype html><p>new</p>\n"
    old = b"<!doctype html><p>old</p>\n"
    src_rel = "ai-home-v2/index.html"
    (source / "ai-home-v2").mkdir(parents=True)
    (source / src_rel).write_bytes(new)
    target_path = fsroot / target.lstrip("/")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(old)
    manifest = {
        "schema": 1,
        "name": "test",
        "operations": [{"source": src_rel, "target": target, "http_path": http_path}],
        "restarts": [],
    }
    manifest_raw = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    (source / ".autopilot").mkdir()
    (source / ".autopilot/release.json").write_bytes(manifest_raw)
    proposal = {
        "schema": 1,
        "id": "release-test",
        "job_id": "job",
        "mode": mode,
        "repo": "Itosyro/voice-bot",
        "branch": "hermes/dev/test",
        "commit": "a" * 40,
        "manifest": ".autopilot/release.json",
        "manifest_blob": blob(manifest_raw),
    }
    proposal_path = root / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    return root, source, fsroot, approvals, backups, proposal_path, target_path, old, new


class ReleaseGateTests(unittest.TestCase):
    def test_auto_safe_release_applies_and_backups(self):
        with tempfile.TemporaryDirectory() as td:
            f = make_fixture(td)
            _, source, fsroot, approvals, backups, proposal, target, old, new = f
            with FixtureServer(fsroot) as server:
                g = load_gate(Path(td), source, fsroot, approvals, backups, server.base)
                planned = g.plan_release(str(proposal))
                self.assertFalse(planned["approval_required"])
                self.assertEqual(planned["risk"], "safe")
                result = g.apply(str(proposal), None)
            self.assertTrue(result["ok"])
            self.assertEqual(target.read_bytes(), new)
            backup = Path(result["backup"])
            self.assertTrue(backup.is_dir())
            self.assertTrue(any(p.read_bytes() == old for p in backup.iterdir() if p.is_file()))

    def test_safe_mode_requires_explicit_approval(self):
        with tempfile.TemporaryDirectory() as td:
            f = make_fixture(td, mode="safe")
            _, source, fsroot, approvals, backups, proposal, target, old, new = f
            with FixtureServer(fsroot) as server:
                g = load_gate(Path(td), source, fsroot, approvals, backups, server.base)
                planned = g.plan_release(str(proposal))
                self.assertTrue(planned["approval_required"])
                with self.assertRaises(g.GateError):
                    g.apply(str(proposal), None)
                result = g.apply(str(proposal), planned["approval_token"])
            self.assertTrue(result["ok"])
            self.assertEqual(target.read_bytes(), new)

    def test_approval_target_requires_token_even_in_auto(self):
        with tempfile.TemporaryDirectory() as td:
            f = make_fixture(td, target="/opt/dvizh/static/manual.html", http_path="/manual.html")
            _, source, fsroot, approvals, backups, proposal, target, old, new = f
            with FixtureServer(fsroot) as server:
                g = load_gate(Path(td), source, fsroot, approvals, backups, server.base)
                planned = g.plan_release(str(proposal))
                self.assertEqual(planned["risk"], "approval")
                self.assertTrue(planned["approval_required"])
                result = g.apply(str(proposal), planned["approval_token"])
            self.assertTrue(result["ok"])
            self.assertEqual(target.read_bytes(), new)

    def test_denied_target_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as td:
            f = make_fixture(td, target="/etc/passwd", http_path="")
            _, source, fsroot, approvals, backups, proposal, target, old, new = f
            with FixtureServer(fsroot) as server:
                g = load_gate(Path(td), source, fsroot, approvals, backups, server.base)
                with self.assertRaises(g.GateError):
                    g.plan_release(str(proposal))
            self.assertEqual(target.read_bytes(), old)

    def test_http_verification_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            f = make_fixture(td)
            _, source, fsroot, approvals, backups, proposal, target, old, new = f
            with FixtureServer(fsroot, stale_root=old) as server:
                g = load_gate(Path(td), source, fsroot, approvals, backups, server.base)
                with self.assertRaises(g.GateError):
                    g.apply(str(proposal), None)
            self.assertEqual(target.read_bytes(), old)

    def test_approval_is_digest_bound_and_one_time(self):
        with tempfile.TemporaryDirectory() as td:
            f = make_fixture(td, mode="safe")
            _, source, fsroot, approvals, backups, proposal, target, old, new = f
            with FixtureServer(fsroot) as server:
                g = load_gate(Path(td), source, fsroot, approvals, backups, server.base)
                planned = g.plan_release(str(proposal))
                token = planned["approval_token"]
                # Mutating proposal after challenge invalidates the digest.
                data = json.loads(proposal.read_text())
                data["id"] = "release-mutated"
                proposal.write_text(json.dumps(data))
                with self.assertRaises(g.GateError):
                    g.apply(str(proposal), token)


if __name__ == "__main__":
    unittest.main()
