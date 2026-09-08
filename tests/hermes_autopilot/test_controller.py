from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "hermes-dev-v2" / "dvizhautopilot.py"


def load_module(tmp: str):
    old = os.environ.copy()
    os.environ["DVIZH_DEV_ROOT"] = str(Path(tmp) / "dev")
    spec = importlib.util.spec_from_file_location("dvizhautopilot_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    os.environ.clear(); os.environ.update(old)
    return module


class ControllerTests(unittest.TestCase):
    def test_profile_routing_is_narrow_and_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            m = load_module(td)
            self.assertEqual(m.test_profiles_for(["README.md"]), ["quick"])
            self.assertEqual(m.test_profiles_for(["ai-home-v2/ai-home-v2.js"]), ["quick", "ai-home-v2"])
            self.assertEqual(m.test_profiles_for(["hermes-control-v1/dvizh_context.py"]), ["quick", "hermes-control"])
            self.assertEqual(m.test_profiles_for(["dvizh-telegram-v1/telegram_bot/bot.py"]), ["quick", "telegram"])

    def test_mode_state_defaults_safe_and_roundtrips(self):
        with tempfile.TemporaryDirectory() as td:
            m = load_module(td)
            self.assertEqual(m.get_mode("missing"), "safe")
            for mode in ("inspect", "safe", "auto"):
                m.save_mode("job", mode)
                self.assertEqual(m.get_mode("job"), mode)
                self.assertEqual(oct(m.mode_path("job").stat().st_mode & 0o777), "0o600")

    def test_wait_ci_stops_on_green(self):
        with tempfile.TemporaryDirectory() as td:
            m = load_module(td)
            rows = iter([
                {"green": False, "pending": 1, "failed": 0, "runs": [{"name": "x"}]},
                {"green": True, "pending": 0, "failed": 0, "runs": [{"name": "x"}]},
            ])
            m.runs_for = lambda _: next(rows)
            m.time.sleep = lambda _: None
            result = m.wait_ci("job", 30, interval=2)
            self.assertTrue(result["green"])
            self.assertFalse(result["timed_out"])

    def test_wait_ci_stops_on_completed_failure(self):
        with tempfile.TemporaryDirectory() as td:
            m = load_module(td)
            m.runs_for = lambda _: {"green": False, "pending": 0, "failed": 1, "runs": [{"name": "x", "conclusion": "failure"}]}
            result = m.wait_ci("job", 30, interval=2)
            self.assertEqual(result["failed"], 1)
            self.assertFalse(result["timed_out"])

    def test_inspect_mode_never_creates_job(self):
        with tempfile.TemporaryDirectory() as td:
            m = load_module(td)
            result = m.new_job("inspect", "diagnose only")
            self.assertEqual(result["mode"], "inspect")
            self.assertEqual(result["production"], "read-only")


if __name__ == "__main__":
    unittest.main()
