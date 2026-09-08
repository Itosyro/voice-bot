from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "hermes-dev-v2" / "dvizhgitpush.py"
JOB_ID = "20260908-120000-abc123"


def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(repo), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return cp.stdout.strip()


def load_gate(home: Path, base_sha: str):
    old = os.environ.copy()
    os.environ.update({
        "DVIZH_GIT_GATE_TEST_MODE": "1",
        "DVIZH_GIT_GATE_HOME": str(home),
        "DVIZH_GIT_GATE_BASE_SHA": base_sha,
        "SUDO_USER": "tester",
    })
    spec = importlib.util.spec_from_file_location(f"dvizhgitpush_test_{id(home)}", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    os.environ.clear(); os.environ.update(old)
    return module


def fixture(td: str):
    root = Path(td)
    home = root / "home"
    wt = home / ".hermes/dev/dvizh/worktrees" / JOB_ID
    state = home / ".hermes/dev/dvizh/state"
    wt.mkdir(parents=True)
    state.mkdir(parents=True)
    git(wt, "init")
    git(wt, "config", "user.name", "Test")
    git(wt, "config", "user.email", "test@example.invalid")
    (wt / "ai-home-v2").mkdir()
    (wt / "ai-home-v2/index.html").write_text("base\n", encoding="utf-8")
    (wt / "src").mkdir()
    (wt / "src/friend.py").write_text("friend base\n", encoding="utf-8")
    git(wt, "add", ".")
    git(wt, "commit", "-m", "base")
    base = git(wt, "rev-parse", "HEAD")
    branch = f"hermes/dev/{JOB_ID}-test"
    git(wt, "checkout", "-b", branch)
    jobs = [{"id": JOB_ID, "branch": branch, "worktree": str(wt), "status": "committed"}]
    (state / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
    return home, wt, base, branch


class GitPushGateTests(unittest.TestCase):
    def test_static_allowlist_accepts_dvizh_and_rejects_friend_project(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            g = load_gate(home, base)
            self.assertTrue(g.path_allowed("ai-home-v2/ai-home-v2.js"))
            self.assertTrue(g.path_allowed("tests/ai-home-v2/client.test.cjs"))
            self.assertTrue(g.path_allowed("install-dvizh-example.sh"))
            self.assertFalse(g.path_allowed("src/services/llm.py"))
            self.assertFalse(g.path_allowed("migrations/versions/x.py"))
            self.assertFalse(g.path_allowed("tests/test_voice_chunking.py"))
            self.assertFalse(g.path_allowed("Dockerfile"))
            self.assertFalse(g.path_allowed("README.md"))

    def test_autopilot_control_plane_is_self_protected(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            g = load_gate(home, base)
            self.assertFalse(g.path_allowed("hermes-dev-v2/dvizhgitpush.py"))
            self.assertFalse(g.path_allowed("tests/hermes_autopilot/test_git_push_gate.py"))
            self.assertFalse(g.path_allowed("install-dvizh-hermes-autopilot.sh"))
            self.assertFalse(g.path_allowed(".github/workflows/dvizh-hermes-autopilot.yml"))

    def test_managed_allowed_commit_is_validated_for_push(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            (wt / "ai-home-v2/index.html").write_text("new dvizh\n", encoding="utf-8")
            git(wt, "add", ".")
            git(wt, "commit", "-m", "dvizh change")
            g = load_gate(home, base)
            result = g.push(JOB_ID)
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "validated-test")
            self.assertEqual(result["paths"], ["ai-home-v2/index.html"])

    def test_friend_project_change_is_rejected_before_push(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            (wt / "src/friend.py").write_text("friend changed\n", encoding="utf-8")
            git(wt, "add", ".")
            git(wt, "commit", "-m", "bad friend change")
            g = load_gate(home, base)
            with self.assertRaises(g.GateError) as ctx:
                g.push(JOB_ID)
            self.assertIn("friend-project/out-of-scope", str(ctx.exception))

    def test_mixed_dvizh_and_friend_change_is_rejected_whole_branch(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            (wt / "ai-home-v2/index.html").write_text("new dvizh\n", encoding="utf-8")
            (wt / "src/friend.py").write_text("friend changed\n", encoding="utf-8")
            git(wt, "add", ".")
            git(wt, "commit", "-m", "mixed change")
            g = load_gate(home, base)
            with self.assertRaises(g.GateError):
                g.push(JOB_ID)

    def test_merge_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            home, wt, base, branch = fixture(td)
            git(wt, "checkout", "-b", "side")
            (wt / "ai-home-v2/side.txt").write_text("side\n", encoding="utf-8")
            git(wt, "add", ".")
            git(wt, "commit", "-m", "side")
            git(wt, "checkout", branch)
            (wt / "ai-home-v2/index.html").write_text("main branch change\n", encoding="utf-8")
            git(wt, "add", ".")
            git(wt, "commit", "-m", "main")
            git(wt, "merge", "--no-ff", "side", "-m", "merge")
            g = load_gate(home, base)
            with self.assertRaises(g.GateError) as ctx:
                g.push(JOB_ID)
            self.assertIn("merge commits", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
