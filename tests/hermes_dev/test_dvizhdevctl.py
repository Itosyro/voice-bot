from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CTL = REPO_ROOT / "hermes-dev-v1" / "dvizhdevctl.py"


class HermesDevCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dvizh-hermes-dev-test."))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.dev_root = self.tmp / "dev"
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "DVIZH_DEV_ROOT": str(self.dev_root),
                "GIT_TERMINAL_PROMPT": "0",
            }
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_ctl(self, *args: str, check: bool = True, timeout: int = 360) -> subprocess.CompletedProcess[str]:
        cp = subprocess.run(
            [sys.executable, str(CTL), *args],
            cwd=str(REPO_ROOT),
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if check and cp.returncode != 0:
            self.fail(f"dvizhdevctl {' '.join(args)} failed\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        return cp

    def json_ctl(self, *args: str, timeout: int = 360):
        cp = self.run_ctl(*args, timeout=timeout)
        return json.loads(cp.stdout)

    def test_config_has_no_deploy_apply_capability(self) -> None:
        cfg = self.json_ctl("config")
        self.assertEqual(cfg["repo_full_name"], "Itosyro/voice-bot")
        self.assertIn("proposal-only", cfg["deploy_capability"])
        self.assertIn("quick", cfg["test_profiles"])

    def test_managed_worktree_commit_and_secret_guard(self) -> None:
        self.json_ctl("init", timeout=360)
        job = self.json_ctl("new", "CI fixture safe worktree test", timeout=360)
        self.assertTrue(job["branch"].startswith("hermes/dev/"))
        wt = pathlib.Path(job["worktree"])
        self.assertTrue((wt / ".git").exists())
        self.assertEqual(self.json_ctl("where", job["id"])["worktree"], str(wt.resolve()))

        readme = wt / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n<!-- hermes-dev-test -->\n", encoding="utf-8")
        quick = self.json_ctl("test", job["id"], "quick")
        self.assertTrue(quick["ok"])
        diff = self.json_ctl("diff", job["id"])
        self.assertIn("README.md", diff["stat"])

        secret_dir = wt / "fixture"
        secret_dir.mkdir()
        secret_file = secret_dir / "auth.json"
        secret_file.write_text('{"token":"SHOULD_NOT_BE_COMMITTED"}\n', encoding="utf-8")
        denied = self.run_ctl("commit", job["id"], "Should refuse secret", check=False)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("forbidden", denied.stderr.lower())
        secret_file.unlink()
        secret_dir.rmdir()

        committed = self.json_ctl("commit", job["id"], "Test safe Hermes dev commit")
        self.assertEqual(committed["branch"], job["branch"])
        self.assertIn("README.md", committed["paths"])
        status = self.json_ctl("status", job["id"])
        self.assertEqual(status["ahead_commits"], 1)
        self.assertEqual(status["dirty"], [])

        # CI runners do not have push credentials for the nested anonymous clone.
        # The important contract is that push fails without prompting or force-pushing.
        pushed = self.run_ctl("push", job["id"], check=False, timeout=120)
        self.assertNotEqual(pushed.returncode, 0)
        self.assertIn("push failed", pushed.stderr.lower())

        closed = self.json_ctl("close", job["id"])
        self.assertEqual(closed["status"], "closed")
        self.assertFalse(wt.exists())

    def test_live_snapshot_is_read_only_when_dvizh_is_absent(self) -> None:
        payload = self.json_ctl("live-snapshot")
        self.assertEqual(payload["version"], "2026.09.06-hermes-dev.1")
        paths = {row["path"]: row for row in payload["files"]}
        self.assertIn("/opt/dvizh/static/app.js", paths)

    def test_source_has_no_root_deploy_or_force_push_path(self) -> None:
        text = CTL.read_text(encoding="utf-8")
        self.assertNotRegex(text, r"sub\.add_parser\([\"']deploy[\"']\)")
        self.assertNotIn("git push --force", text)
        self.assertNotRegex(text, r"systemctl[^\n]*(restart|start|stop|enable|disable)")
        self.assertNotRegex(text, r"subprocess[^\n]*sudo")
        self.assertIn("deploy-propose", text)
        self.assertIn("GIT_TERMINAL_PROMPT", text)


if __name__ == "__main__":
    unittest.main()
