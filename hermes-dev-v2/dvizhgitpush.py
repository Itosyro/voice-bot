#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "2026.09.08-dvizh-git-push-gate.1"
REPO = "Itosyro/voice-bot"
BASE_BRANCH = "codex/hermes-autopilot-v2-2026-09-08"
KEY = Path(os.environ.get("DVIZH_GIT_GATE_KEY", "/var/lib/dvizh/autopilot-github/id_ed25519"))
TEST_MODE = os.environ.get("DVIZH_GIT_GATE_TEST_MODE", "0") == "1"
TEST_HOME = os.environ.get("DVIZH_GIT_GATE_HOME", "").strip()
MAX_COMMITS = 50

ALLOWED_PREFIXES = (
    "ai-home-v2/",
    "tests/ai-home-v2/",
    "hermes-control-v1/",
    "dvizh-auth-release/",
    "dvizh-integration-v1/",
    "dvizh-telegram-v1/",
    "dvizh-weekly-v1/",
    "training-readiness-v1/",
    "web-week-v1/",
    "web-week-editor-v1/",
    "jump-goal-release/",
    "minimal-ui-v1/",
    "social-release/",
    "social-release-v2/",
    ".github/social-v1/",
)
ALLOWED_EXACT = {
    ".autopilot/release.json",
    "fix-dvizh-web-user.sh",
}
ALLOWED_ROOT_PATTERNS = (
    re.compile(r"^(?:install|diagnose|promote|recover|repair)-dvizh-[A-Za-z0-9._-]+\.sh$"),
    re.compile(r"^docs/dvizh-[A-Za-z0-9._/-]+\.md$", re.I),
    re.compile(r"^\.github/workflows/dvizh-(?!hermes-autopilot(?:-|\.)).*\.ya?ml$"),
)
CONTROL_PLANE_DENY = (
    "hermes-dev-v2/",
    "tests/hermes_autopilot/",
    "install-dvizh-hermes-autopilot.sh",
    ".github/workflows/dvizh-hermes-autopilot.yml",
    ".github/workflows/dvizh-hermes-autopilot-v2-tests.yml",
    ".github/workflows/dvizh-hermes-autopilot-installer-smoke.yml",
)
FRIEND_PROJECT_MARKERS = (
    "src/",
    "migrations/",
    "tests/test_",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.server.yml",
    "pyproject.toml",
    "alembic.ini",
    "Makefile",
    "README.md",
)


class GateError(RuntimeError):
    pass


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, timeout: int = 90, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    cp = subprocess.run(args, cwd=str(cwd) if cwd else None, env=merged, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)
    if check and cp.returncode != 0:
        raise GateError((cp.stderr or cp.stdout or "command failed").strip()[-4000:])
    return cp


def require_root() -> None:
    if not TEST_MODE and os.geteuid() != 0:
        raise GateError("dvizhgitpush must run as root")


def caller_home() -> tuple[str, Path]:
    user = os.environ.get("SUDO_USER", "").strip()
    if TEST_MODE and TEST_HOME:
        return user or "tester", Path(TEST_HOME).resolve()
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
        raise GateError("missing or invalid SUDO_USER")
    import pwd
    try:
        entry = pwd.getpwnam(user)
    except KeyError as exc:
        raise GateError("SUDO_USER does not exist") from exc
    home = Path(entry.pw_dir).resolve()
    if not home.is_dir():
        raise GateError("caller home is missing")
    return user, home


def jobs_path(home: Path) -> Path:
    return home / ".hermes/dev/dvizh/state/jobs.json"


def load_job(home: Path, job_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9a-f]{6}", job_id):
        raise GateError("invalid managed job id")
    p = jobs_path(home)
    if not p.is_file() or p.is_symlink():
        raise GateError("managed jobs state is missing")
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GateError("managed jobs state is invalid") from exc
    if not isinstance(rows, list):
        raise GateError("managed jobs state must be a list")
    matches = [r for r in rows if isinstance(r, dict) and str(r.get("id")) == job_id]
    if not matches:
        raise GateError("managed job not found")
    return matches[-1]


def git_args(wt: Path, *args: str) -> list[str]:
    return ["git", "-c", f"safe.directory={wt}", "-C", str(wt), *args]


def validate_worktree(home: Path, job_id: str, job: dict[str, Any]) -> tuple[Path, str, str]:
    managed = (home / ".hermes/dev/dvizh/worktrees").resolve()
    wt = Path(str(job.get("worktree") or "")).resolve()
    expected = (managed / job_id).resolve()
    if wt != expected or not wt.is_dir():
        raise GateError("job worktree is outside the managed DVIZH root")
    branch = run(git_args(wt, "branch", "--show-current")).stdout.strip()
    expected_prefix = f"hermes/dev/{job_id}-"
    if not branch.startswith(expected_prefix) or branch != str(job.get("branch") or ""):
        raise GateError("managed branch identity mismatch")
    dirty = run(git_args(wt, "status", "--porcelain=v1")).stdout.strip()
    if dirty:
        raise GateError("worktree must be clean before push")
    head = run(git_args(wt, "rev-parse", "HEAD")).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise GateError("invalid HEAD identity")
    return wt, branch, head


def public_base_sha() -> str:
    if TEST_MODE:
        value = os.environ.get("DVIZH_GIT_GATE_BASE_SHA", "").strip()
        if re.fullmatch(r"[0-9a-f]{40}", value):
            return value
        raise GateError("test base SHA is missing")
    url = f"https://api.github.com/repos/{REPO}/branches/{BASE_BRANCH.replace('/', '%2F')}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"DVIZH-Git-Push-Gate/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise GateError(f"cannot resolve trusted DVIZH base: {type(exc).__name__}") from exc
    sha = str((((payload or {}).get("commit") or {}).get("sha")) or "") if isinstance(payload, dict) else ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GateError("trusted DVIZH base returned invalid SHA")
    return sha


def ensure_commit(wt: Path, sha: str) -> None:
    if run(git_args(wt, "cat-file", "-e", f"{sha}^{{commit}}"), check=False).returncode == 0:
        return
    if TEST_MODE:
        raise GateError("trusted base commit is absent from fixture")
    cp = run(git_args(wt, "fetch", "--no-tags", "--quiet", f"https://github.com/{REPO}.git", sha), check=False, timeout=120)
    if cp.returncode != 0 or run(git_args(wt, "cat-file", "-e", f"{sha}^{{commit}}"), check=False).returncode != 0:
        raise GateError("cannot fetch trusted DVIZH base commit")


def path_allowed(path: str) -> bool:
    if not path or path.startswith("/") or ".." in Path(path).parts or "\\" in path:
        return False
    if path in CONTROL_PLANE_DENY or any(path.startswith(p) for p in CONTROL_PLANE_DENY if p.endswith("/")):
        return False
    if path in ALLOWED_EXACT or any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return True
    return any(rx.fullmatch(path) for rx in ALLOWED_ROOT_PATTERNS)


def changed_paths(wt: Path, base: str, head: str) -> list[str]:
    if run(git_args(wt, "merge-base", "--is-ancestor", base, head), check=False).returncode != 0:
        raise GateError("managed branch is not descended from the trusted DVIZH base")
    merge = run(git_args(wt, "merge-base", base, head)).stdout.strip()
    count = int(run(git_args(wt, "rev-list", "--count", f"{merge}..{head}")).stdout.strip() or "0")
    if count < 1 or count > MAX_COMMITS:
        raise GateError(f"unexpected autonomous commit count: {count}")
    if run(git_args(wt, "rev-list", "--merges", f"{merge}..{head}"), check=False).stdout.strip():
        raise GateError("merge commits are not allowed in autonomous Hermes branches")
    raw = run(git_args(wt, "diff", "--name-only", "-z", merge, head, "--", ".")).stdout
    paths = sorted({p for p in raw.split("\0") if p})
    if not paths:
        raise GateError("nothing changed relative to the trusted DVIZH base")
    denied = [p for p in paths if not path_allowed(p)]
    if denied:
        friend = [p for p in denied if p in FRIEND_PROJECT_MARKERS or any(p.startswith(x) for x in FRIEND_PROJECT_MARKERS if x.endswith("/"))]
        label = "friend-project/out-of-scope paths" if friend else "out-of-scope paths"
        raise GateError(f"{label} are forbidden: {', '.join(denied[:20])}")
    return paths


def ssh_env() -> dict[str, str]:
    if not KEY.is_file() or KEY.is_symlink():
        raise GateError("root-owned GitHub deploy key is missing")
    st = KEY.stat()
    if not TEST_MODE and (st.st_uid != 0 or (st.st_mode & 0o077) != 0):
        raise GateError("GitHub deploy key permissions are unsafe")
    return {"GIT_SSH_COMMAND": f"ssh -i {KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new", "GIT_TERMINAL_PROMPT": "0"}


def doctor() -> dict[str, Any]:
    require_root()
    key_ok = KEY.is_file() and not KEY.is_symlink()
    authorized = False
    detail = "key missing"
    if key_ok:
        cp = run(["git", "ls-remote", f"git@github.com:{REPO}.git", "HEAD"], check=False, timeout=30, env=ssh_env())
        authorized = cp.returncode == 0
        detail = (cp.stderr or cp.stdout).strip()[-1500:]
    return {"ok": key_ok and authorized, "version": VERSION, "repo": REPO, "base_branch": BASE_BRANCH, "key_present": key_ok, "authorized": authorized, "detail": detail}


def push(job_id: str) -> dict[str, Any]:
    require_root()
    _, home = caller_home()
    job = load_job(home, job_id)
    wt, branch, head = validate_worktree(home, job_id, job)
    base = public_base_sha()
    ensure_commit(wt, base)
    paths = changed_paths(wt, base, head)
    if TEST_MODE:
        return {"ok": True, "status": "validated-test", "branch": branch, "head": head, "base": base, "paths": paths}
    cp = run(git_args(wt, "push", "--porcelain", f"git@github.com:{REPO}.git", f"HEAD:refs/heads/{branch}"), check=False, timeout=180, env=ssh_env())
    if cp.returncode != 0:
        raise GateError("guarded push failed: " + (cp.stderr or cp.stdout).strip()[-3000:])
    return {"ok": True, "status": "pushed", "branch": branch, "head": head, "base": base, "paths": paths, "output": (cp.stdout + cp.stderr)[-3000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Root-owned DVIZH-only Git push gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    p = sub.add_parser("push"); p.add_argument("job_id")
    args = parser.parse_args()
    try:
        result = doctor() if args.cmd == "doctor" else push(args.job_id)
        emit(result)
        return 0 if result.get("ok") else 2
    except (GateError, subprocess.TimeoutExpired) as exc:
        emit({"ok": False, "error": str(exc), "version": VERSION})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
