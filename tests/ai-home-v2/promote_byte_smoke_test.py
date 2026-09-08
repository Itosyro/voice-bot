from __future__ import annotations

import http.server
import os
import shutil
import socketserver
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
PROMOTE = REPO / "promote-dvizh-ai-home-v2-byte-smoke.sh"
PINNED_RELEASE = "d6418224eae292417a645b2a73da157d939526b9"

OLD_INDEX = b'''<!doctype html>\n<html><head><link rel="stylesheet" href="./styles.css?v=dvizh-pre-ai-recovery-v1"></head><body><main id="app">manual</main><script src="./app.js?v=dvizh-pre-ai-recovery-v1"></script></body></html>\n'''


def prepare_pinned_source(parent: Path) -> Path:
    source = parent / "pinned-source"
    source.mkdir()
    for name in ("index.html", "ai-home-v2.js", "ai-home-v2.css"):
        data = subprocess.check_output(
            ["git", "show", f"{PINNED_RELEASE}:ai-home-v2/{name}"],
            cwd=REPO,
        )
        (source / name).write_bytes(data)
    return source


def prepare_root(root: Path, source: Path) -> None:
    (root / "index.html").write_bytes(OLD_INDEX)
    (root / "app.js").write_text("console.log('manual');\n", encoding="utf-8")
    (root / "styles.css").write_text("body{}\n", encoding="utf-8")
    (root / "sw.js").write_text("// stable worker\n", encoding="utf-8")
    shutil.copy2(source / "index.html", root / "ai-home-v2-preview.html")
    shutil.copy2(source / "ai-home-v2.js", root / "ai-home-v2.js")
    shutil.copy2(source / "ai-home-v2.css", root / "ai-home-v2.css")


class FixtureServer:
    def __init__(self, root: Path, mode: str = "normal") -> None:
        self.root = root
        self.mode = mode
        self.old_root = (root / "index.html").read_bytes()
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = urlsplit(self.path).path
                if path == "/manual.html" and outer.mode == "bad_manual":
                    self._reply(200, b"wrong manual body\n")
                    return
                if path in {"/", "/index.html"} and outer.mode == "stale_root":
                    self._reply(200, outer.old_root)
                    return
                if path == "/":
                    file = outer.root / "index.html"
                else:
                    file = outer.root / path.lstrip("/")
                if not file.is_file():
                    self._reply(404, b"not found\n")
                    return
                self._reply(200, file.read_bytes())

            def _reply(self, code: int, body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args) -> None:
                pass

        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FixtureServer":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def run_promote(root: Path, server: FixtureServer, source: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DVIZH_AI_HOME_V2_ROOT": str(root),
            "DVIZH_AI_HOME_V2_TEST_HTTP_BASE_URL": server.base_url,
            "DVIZH_AI_HOME_V2_TEST_SOURCE_DIR": str(source),
        }
    )
    return subprocess.run(
        ["bash", str(PROMOTE)],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


class PromoteByteSmokeTest(unittest.TestCase):
    def test_success_uses_byte_exact_live_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            root = workspace / "site"
            root.mkdir()
            source = prepare_pinned_source(workspace)
            prepare_root(root, source)
            readonly_before = {p.name: p.read_bytes() for p in root.iterdir() if p.name not in {"index.html", "manual.html"}}
            with FixtureServer(root, "normal") as server:
                result = run_promote(root, server, source)
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertEqual((root / "index.html").read_bytes(), (source / "index.html").read_bytes())
            self.assertEqual((root / "manual.html").read_bytes(), OLD_INDEX)
            self.assertIn("HTTP manual-preflight: OK (byte-exact)", result.stdout)
            self.assertIn("HTTP root: OK (byte-exact)", result.stdout)
            self.assertIn("HTTP index: OK (byte-exact)", result.stdout)
            self.assertIn("HTTP manual: OK (byte-exact)", result.stdout)
            readonly_after = {p.name: p.read_bytes() for p in root.iterdir() if p.name not in {"index.html", "manual.html"}}
            self.assertEqual(readonly_before, readonly_after)

    def test_manual_preflight_failure_never_changes_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            root = workspace / "site"
            root.mkdir()
            source = prepare_pinned_source(workspace)
            prepare_root(root, source)
            with FixtureServer(root, "bad_manual") as server:
                result = run_promote(root, server, source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / "index.html").read_bytes(), OLD_INDEX)
            self.assertFalse((root / "manual.html").exists())
            self.assertIn("body не совпадает байт-в-байт", result.stderr)
            self.assertIn("Автоматический rollback завершён", result.stderr)

    def test_root_http_failure_rolls_back_both_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            root = workspace / "site"
            root.mkdir()
            source = prepare_pinned_source(workspace)
            prepare_root(root, source)
            with FixtureServer(root, "stale_root") as server:
                result = run_promote(root, server, source)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / "index.html").read_bytes(), OLD_INDEX)
            self.assertFalse((root / "manual.html").exists())
            self.assertIn("HTTP manual-preflight: OK (byte-exact)", result.stdout)
            self.assertIn("HTTP root: body не совпадает", result.stderr)
            self.assertIn("Автоматический rollback завершён", result.stderr)


if __name__ == "__main__":
    unittest.main()
