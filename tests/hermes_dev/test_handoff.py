from __future__ import annotations

import hashlib
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
HANDOFF = REPO_ROOT / "hermes-dev-v1" / "dvizhdevhandoff.py"


class HermesHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="dvizh-hermes-handoff-test."))
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

    def run_py(self, script: pathlib.Path, *args: str, check: bool = True, timeout: int = 360) -> subprocess.CompletedProcess[str]:
        cp = subprocess.run(
            [sys.executable, str(script), *args],
            cwd=str(REPO_ROOT),
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if check and cp.returncode != 0:
            self.fail(f"{script.name} {' '.join(args)} failed\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
        return cp

    def json_ctl(self, *args: str):
        return json.loads(self.run_py(CTL, *args).stdout)

    def test_clean_local_commit_exports_exact_patch_without_github_auth(self) -> None:
        self.json_ctl("init")
        job = self.json_ctl("new", "handoff fixture")
        wt = pathlib.Path(job["worktree"])
        readme = wt / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\n<!-- handoff-fixture -->\n", encoding="utf-8")
        committed = self.json_ctl("commit", job["id"], "Handoff fixture commit")

        result = json.loads(self.run_py(HANDOFF, job["id"]).stdout)
        self.assertEqual(result["job_id"], job["id"])
        self.assertEqual(result["base_sha"], job["base_sha"])
        self.assertEqual(result["head_sha"], committed["commit"])
        self.assertEqual(result["github_push_required_from_hermes"], False)
        self.assertEqual(result["production_status"], "unchanged")
        self.assertIn("README.md", result["paths"])
        self.assertIn("handoff-fixture", result["patch_inline"])

        patch_path = pathlib.Path(result["patch_path"])
        manifest_path = pathlib.Path(result["manifest_path"])
        self.assertTrue(patch_path.is_file())
        self.assertTrue(manifest_path.is_file())
        data = patch_path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), result["patch_sha256"])
        self.assertEqual(len(data), result["patch_bytes"])

    def test_handoff_rejects_secret_shaped_path_even_if_committed_outside_controller(self) -> None:
        self.json_ctl("init")
        job = self.json_ctl("new", "secret handoff fixture")
        wt = pathlib.Path(job["worktree"])
        secret_dir = wt / "fixture"
        secret_dir.mkdir()
        secret = secret_dir / "auth.json"
        secret.write_text('{"token":"DO_NOT_EXPORT"}\n', encoding="utf-8")
        subprocess.run(["git", "add", "-f", "fixture/auth.json"], cwd=wt, check=True)
        subprocess.run(["git", "commit", "-m", "unsafe fixture"], cwd=wt, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        denied = self.run_py(HANDOFF, job["id"], check=False)
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("credential-shaped", denied.stderr)
        self.assertNotIn("DO_NOT_EXPORT", denied.stdout + denied.stderr)

    def test_handoff_source_has_no_network_push_or_production_mutation(self) -> None:
        text = HANDOFF.read_text(encoding="utf-8")
        self.assertNotIn("git push", text)
        self.assertNotIn("urllib", text)
        self.assertNotRegex(text, r"systemctl[^\n]*(restart|start|stop|enable|disable)")
        self.assertNotRegex(text, r"subprocess[^\n]*sudo")
        self.assertNotIn("/opt/dvizh", text)
        self.assertIn("git", text)
        self.assertIn("diff", text)


if __name__ == "__main__":
    unittest.main()
