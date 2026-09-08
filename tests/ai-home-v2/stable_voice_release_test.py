from __future__ import annotations

import hashlib
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
INSTALLER = REPO / "install-dvizh-ai-home-v2-stable-voice-release.sh"
SOURCE = REPO / "ai-home-v2"
BASE = "ba8214911f5942fdbf36269e1e992eb7607b40f8"


def git_show(path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=REPO)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def prepare_root(root: Path) -> dict[str, bytes]:
    files = {
        "index.html": git_show("ai-home-v2/index.html"),
        "ai-home-v2.js": git_show("ai-home-v2/ai-home-v2.js"),
        "ai-home-v2.css": git_show("ai-home-v2/ai-home-v2.css"),
        "manual.html": b"<!doctype html><main>manual protected</main>\n",
        "app.js": b"console.log('manual protected');\n",
        "sync.js": b"console.log('sync protected');\n",
        "sw.js": b"// worker protected\n",
        "ai-home-v2-voice-preview.html": b"preview protected\n",
        "ai-home-v2-voice.js": b"voice preview protected\n",
    }
    for name, data in files.items():
        (root / name).write_bytes(data)
    return files


class FixtureServer:
    def __init__(self, root: Path, policy: bool = True) -> None:
        self.root = root
        self.policy = policy
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = urlsplit(self.path).path
                file = outer.root / ("index.html" if path == "/" else path.lstrip("/"))
                if not file.is_file():
                    self.send_response(404)
                    self.end_headers()
                    return
                body = file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript" if path.endswith(".js") else "text/html; charset=utf-8")
                if outer.policy:
                    self.send_header(
                        "Permissions-Policy",
                        "camera=(), microphone=(self), geolocation=(), payment=()",
                    )
                else:
                    self.send_header(
                        "Permissions-Policy",
                        "camera=(), microphone=(), geolocation=(), payment=()",
                    )
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


def run_installer(root: Path, server: FixtureServer, *, fail_after_write: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DVIZH_STABLE_VOICE_ROOT": str(root),
            "DVIZH_STABLE_VOICE_HTTP_BASE": server.base_url,
            "DVIZH_STABLE_VOICE_SOURCE_DIR": str(SOURCE),
            "DVIZH_STABLE_VOICE_FAIL_AFTER_WRITE": "1" if fail_after_write else "0",
        }
    )
    return subprocess.run(
        ["bash", str(INSTALLER)],
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )


class StableVoiceReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This installer verifies an immutable historical release. Quiet Signal
        # deliberately changes the working UI; keep its historical byte contract.
        global SOURCE
        cls.source_fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.source_fixture.cleanup)
        SOURCE = Path(cls.source_fixture.name)
        for name in ["index.html", "ai-home-v2.js"]:
            data = subprocess.check_output(
                ["git", "show", f"4c74d5216e2cfcca5a14bdaf179cf520aecfd685:ai-home-v2/{name}"], cwd=REPO)
            (SOURCE / name).write_bytes(data)

    def test_success_updates_only_root_and_stable_js_then_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = prepare_root(root)
            protected = {name: data for name, data in original.items() if name not in {"index.html", "ai-home-v2.js"}}
            with FixtureServer(root, policy=True) as server:
                first = run_installer(root, server)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                self.assertEqual((root / "index.html").read_bytes(), (SOURCE / "index.html").read_bytes())
                self.assertEqual((root / "ai-home-v2.js").read_bytes(), (SOURCE / "ai-home-v2.js").read_bytes())
                for name, data in protected.items():
                    self.assertEqual((root / name).read_bytes(), data, name)
                self.assertIn("Установлен 2026.09.08-ai-home-v2-stable-voice.1", first.stdout)
                self.assertIn("microphone=(self)", first.stdout)

                second = run_installer(root, server)
                self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
                self.assertIn("Stable voice уже установлен и повторно проверен", second.stdout)
                for name, data in protected.items():
                    self.assertEqual((root / name).read_bytes(), data, name)

    def test_forced_failure_after_write_rolls_back_both_mutable_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = prepare_root(root)
            with FixtureServer(root, policy=True) as server:
                result = run_installer(root, server, fail_after_write=True)
            self.assertEqual(result.returncode, 77, result.stdout + result.stderr)
            for name, data in original.items():
                self.assertEqual((root / name).read_bytes(), data, name)
            self.assertIn("Stable voice update не подтверждён", result.stderr)
            self.assertIn("Автоматический rollback завершён", result.stderr)

    def test_missing_microphone_policy_refuses_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = prepare_root(root)
            with FixtureServer(root, policy=False) as server:
                result = run_installer(root, server)
            self.assertNotEqual(result.returncode, 0)
            for name, data in original.items():
                self.assertEqual((root / name).read_bytes(), data, name)
            self.assertIn("Prerequisite не выполнен", result.stderr)

    def test_release_is_pinned_to_accepted_hermes_assets(self) -> None:
        source_index = (SOURCE / "index.html").read_bytes()
        source_js = (SOURCE / "ai-home-v2.js").read_bytes()
        self.assertEqual(git_blob(source_index), "e27cbfedf3022525fff3d6b77a12d824055c252c")
        self.assertEqual(git_blob(source_js), "c25a48d815f4cb05b0be90d4d3c5196d60be6e6f")
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn('SOURCE_COMMIT="4c74d5216e2cfcca5a14bdaf179cf520aecfd685"', text)
        self.assertNotIn("systemctl", text)
        for protected in ["manual.html", "app.js", "sync.js", "sw.js"]:
            self.assertIn(protected, text)


if __name__ == "__main__":
    unittest.main()
