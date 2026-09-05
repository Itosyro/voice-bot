#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PATH = ROOT / "hermes-control-v1" / "dvizh_ai_home_bridge.py"


def load_bridge():
    spec = importlib.util.spec_from_file_location("dvizh_ai_home_bridge_v2_contract", BRIDGE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load dvizh_ai_home_bridge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture:
    def __init__(self):
        self.lock = threading.Lock()
        self.revision = 7
        self.state = {
            "sentinel": {"keep": [1, 2, 3]},
            "tasks": [{"id": "t1", "title": "KEEP TASK"}],
            "proposals": [{"id": "p1", "status": "pending", "type": "task.create"}],
            "aiHomeMessages": [
                {"role": "assistant", "content": "Предыдущий ответ"},
                {"role": "user", "content": "Что у меня сегодня?"},
            ],
            "aiHomeRequests": [{
                "id": "ai2-contract-1",
                "text": "Что у меня сегодня?",
                "status": "pending",
                "createdAt": "2026-09-05T20:00:00+00:00",
            }],
            "aiHomeStatus": {"state": "queued", "requestId": "ai2-contract-1"},
        }
        self.initial_unrelated = {
            "sentinel": copy.deepcopy(self.state["sentinel"]),
            "tasks": copy.deepcopy(self.state["tasks"]),
            "proposals": copy.deepcopy(self.state["proposals"]),
        }
        self.hermes_payloads: list[dict] = []
        self.web_identity_headers: list[tuple[str, str]] = []
        self.conflict_once = True
        self.hermes_error = False


class Handler(BaseHTTPRequestHandler):
    fixture: Fixture

    def log_message(self, *_args):
        pass

    def json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def send_json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def record_identity(self):
        self.fixture.web_identity_headers.append((
            self.headers.get("X-ExeDev-UserID", ""),
            self.headers.get("X-ExeDev-Email", ""),
        ))

    def do_GET(self):
        if self.path == "/api/state":
            self.record_identity()
            with self.fixture.lock:
                self.send_json(200, {
                    "revision": self.fixture.revision,
                    "state": copy.deepcopy(self.fixture.state),
                })
            return
        self.send_json(404, {"error": "not found"})

    def do_PUT(self):
        if self.path != "/api/state":
            self.send_json(404, {"error": "not found"})
            return
        self.record_identity()
        payload = self.json_body()
        with self.fixture.lock:
            if self.fixture.conflict_once:
                self.fixture.conflict_once = False
                self.send_json(409, {"error": "intentional contract conflict"})
                return
            if payload.get("baseRevision") != self.fixture.revision:
                self.send_json(409, {"error": "revision mismatch"})
                return
            state = payload.get("state")
            if not isinstance(state, dict):
                self.send_json(400, {"error": "state missing"})
                return
            self.fixture.state = copy.deepcopy(state)
            self.fixture.revision += 1
            revision = self.fixture.revision
        self.send_json(200, {"ok": True, "revision": revision})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_json(404, {"error": "not found"})
            return
        if self.headers.get("Authorization") != "Bearer " + ("k" * 32):
            self.send_json(401, {"error": "bad auth"})
            return
        payload = self.json_body()
        self.fixture.hermes_payloads.append(copy.deepcopy(payload))
        if self.fixture.hermes_error:
            self.send_json(503, {"error": "intentional Hermes failure"})
            return
        self.send_json(200, {
            "choices": [{"message": {"content": "Контрактный ответ Hermes"}}]
        })


class BridgeContractTest(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        Handler.fixture = self.fixture
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temp = tempfile.TemporaryDirectory(prefix="dvizh-ai-home-v2-bridge-")
        self.tmp = Path(self.temp.name)
        self.bridge = load_bridge()
        base = f"http://127.0.0.1:{self.server.server_port}"
        self.bridge.WEB_API = base
        self.bridge.HERMES_API = base + "/v1"
        self.bridge.HERMES_API_KEY = "k" * 32
        self.bridge.HERMES_MODEL = "hermes-agent-contract"
        self.bridge.IDENTITY_PATH = self.tmp / "auth-identity.json"
        self.bridge.STATUS_PATH = self.tmp / "ai-home-status.json"
        self.bridge.IDENTITY_PATH.write_text(json.dumps({
            "user_id": "contract-user",
            "email": "contract@dvizh.invalid",
        }), encoding="utf-8")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def assert_unrelated_preserved(self):
        for key, value in self.fixture.initial_unrelated.items():
            self.assertEqual(self.fixture.state[key], value, key)

    def test_pending_request_round_trips_through_real_bridge_contract(self):
        result = self.bridge.sync_once()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["processed"], "ai2-contract-1")
        self.assert_unrelated_preserved()

        request = self.fixture.state["aiHomeRequests"][0]
        self.assertEqual(request["status"], "done")
        self.assertIn("startedAt", request)
        self.assertIn("finishedAt", request)
        self.assertEqual(self.fixture.state["aiHomeStatus"]["state"], "ready")

        messages = self.fixture.state["aiHomeMessages"]
        self.assertEqual(sum(m.get("content") == "Что у меня сегодня?" for m in messages), 1)
        self.assertEqual(messages[-1], {"role": "assistant", "content": "Контрактный ответ Hermes"})

        self.assertEqual(len(self.fixture.hermes_payloads), 1)
        payload = self.fixture.hermes_payloads[0]
        self.assertEqual(payload["model"], "hermes-agent-contract")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][-1], {"role": "user", "content": "Что у меня сегодня?"})
        system = payload["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn("dvizh-server", system["content"])
        self.assertIn("proposal", system["content"])
        self.assertIn("НЕ меняй напрямую", system["content"])

        self.assertTrue(self.fixture.web_identity_headers)
        self.assertTrue(all(pair == ("contract-user", "contract@dvizh.invalid")
                            for pair in self.fixture.web_identity_headers))
        status = json.loads(self.bridge.STATUS_PATH.read_text(encoding="utf-8"))
        self.assertTrue(status["ok"])
        self.assertEqual(status["model"], "hermes-agent-contract")
        self.assertEqual(status["processed"], "ai2-contract-1")

    def test_hermes_failure_is_published_without_touching_other_dvizh_data(self):
        self.fixture.conflict_once = False
        self.fixture.hermes_error = True
        result = self.bridge.sync_once()
        self.assertFalse(result["ok"], result)
        self.assert_unrelated_preserved()
        request = self.fixture.state["aiHomeRequests"][0]
        self.assertEqual(request["status"], "error")
        self.assertIn("Hermes API HTTP 503", request["error"])
        self.assertEqual(self.fixture.state["aiHomeStatus"]["state"], "error")
        self.assertNotEqual(self.fixture.state["aiHomeMessages"][-1].get("role"), "assistant")


if __name__ == "__main__":
    unittest.main(verbosity=2)
