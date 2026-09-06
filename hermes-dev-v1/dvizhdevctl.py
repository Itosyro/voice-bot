#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2026.09.06-hermes-dev.1"
REPO_FULL_NAME = os.environ.get("DVIZH_DEV_REPO_FULL_NAME", "Itosyro/voice-bot").strip()
REPO_URL = os.environ.get("DVIZH_DEV_REPO_URL", f"https://github.com/{REPO_FULL_NAME}.git").strip()
BASE_BRANCH = os.environ.get("DVIZH_DEV_BASE_BRANCH", "codex/dvizh-ai-home-v2-2026-09-05").strip()
HOME = Path.home()
ROOT = Path(os.environ.get("DVIZH_DEV_ROOT", str(HOME / ".hermes" / "dev" / "dvizh"))).expanduser().resolve()
REPO = ROOT / "repo"
WORKTREES = ROOT / "worktrees"
STATE_DIR = ROOT / "state"
JOBS_PATH = STATE_DIR / "jobs.json"
LOCK_PATH = STATE_DIR / ".lock"
PROPOSALS_DIR = STATE_DIR / "deploy-proposals"
MAX_CAPTURE = 60000

FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)(\.env(?:\.|$)|auth\.json$|credentials?(?:\.|$)|secrets?(?:\.|$))", re.I),
    re.compile(r"\.(?:pem|key|p12|pfx)$", re.I),
    re.compile(r"(^|/)\.git(?:/|$)"),
)

TEST_PROFILES: dict[str, list[list[str]]] = {
    "quick": [
        ["git", "diff", "--check"],
    ],
    "ai-home-v2": [
        ["git", "diff", "--check"],
        ["node", "--check", "ai-home-v2/ai-home-v2.js"],
        ["node", "--test", "tests/ai-home-v2"],
        ["python3", "tests/ai-home-v2/bridge_contract_test.py"],
    ],
    "hermes-control": [
        ["git", "diff", "--check"],
        ["python3", "-m", "py_compile", "hermes-control-v1/dvizh_context.py", "hermes-control-v1/dvizh_proposals.py", "hermes-control-v1/dvizh_ai_home_bridge.py"],
        ["bash", "-n", "hermes-control-v1/dvizhctl"],
    ],
    "telegram": [
        ["git", "diff", "--check"],
        ["python3", "-m", "compileall", "-q", "dvizh-telegram-v1/telegram_bot"],
    ],
    "hermes-dev": [
        ["git", "diff", "--check"],
        ["python3", "-m", "py_compile", "hermes-dev-v1/dvizhdevctl.py"],
        ["python3", "-m", "unittest", "-v", "tests.hermes_dev.test_dvizhdevctl"],
    ],
}


class DevError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def out_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, env: dict[str, str] | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    cp = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "command failed").strip()[-4000:]
        raise DevError(f"command failed ({' '.join(args[:3])}): {detail}")
    return cp


def ensure_dirs() -> None:
    for path in (ROOT, WORKTREES, STATE_DIR, PROPOSALS_DIR):
        path.mkdir(parents=True, exist_ok=True)
        try:
            path.chmod(0o700)
        except OSError:
            pass


def locked_jobs(mutator=None):
    ensure_dirs()
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            rows = json.loads(JOBS_PATH.read_text(encoding="utf-8")) if JOBS_PATH.exists() else []
        except Exception:
            rows = []
        if not isinstance(rows, list):
            rows = []
        if mutator is None:
            return rows
        result = mutator(rows)
        tmp = JOBS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows[-200:], ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, JOBS_PATH)
        return result


def normalize_remote(url: str) -> str:
    value = url.strip().removesuffix(".git")
    value = value.replace("git@github.com:", "https://github.com/")
    value = value.replace("ssh://git@github.com/", "https://github.com/")
    return value.rstrip("/")


def ensure_repo() -> None:
    ensure_dirs()
    if not (REPO / ".git").exists():
        if REPO.exists() and any(REPO.iterdir()):
            raise DevError(f"repo path is not an empty git clone: {REPO}")
        REPO.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--origin", "origin", REPO_URL, str(REPO)], timeout=300)
    remote = run(["git", "remote", "get-url", "origin"], cwd=REPO).stdout.strip()
    expected = f"https://github.com/{REPO_FULL_NAME}"
    if normalize_remote(remote).lower() != expected.lower():
        raise DevError(f"unexpected origin remote: {remote}")
    run(["git", "fetch", "origin", "--prune"], cwd=REPO, timeout=180)
    run(["git", "show-ref", "--verify", f"refs/remotes/origin/{BASE_BRANCH}"], cwd=REPO)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "-", text.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-_")
    if not s:
        s = "fix"
    # Git ref names are easier to handle portably when the slug itself is ASCII.
    asciiish = "".join(ch for ch in s if ord(ch) < 128)
    return (asciiish or "fix")[:36].strip("-_") or "fix"


def new_job(problem: str) -> dict[str, Any]:
    problem = problem.strip()
    if not 3 <= len(problem) <= 2000:
        raise DevError("problem must be 3..2000 chars")
    ensure_repo()
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    branch = f"hermes/dev/{job_id}-{slugify(problem)}"
    worktree = (WORKTREES / job_id).resolve()
    if worktree.exists():
        raise DevError("worktree collision")
    base_ref = f"origin/{BASE_BRANCH}"
    base_sha = run(["git", "rev-parse", base_ref], cwd=REPO).stdout.strip()
    run(["git", "worktree", "add", "-b", branch, str(worktree), base_ref], cwd=REPO, timeout=180)
    run(["git", "config", "user.name", "Hermes Dev"], cwd=worktree)
    run(["git", "config", "user.email", "hermes-dev@dvizh.invalid"], cwd=worktree)
    job = {
        "id": job_id,
        "problem": problem,
        "branch": branch,
        "base_branch": BASE_BRANCH,
        "base_sha": base_sha,
        "worktree": str(worktree),
        "status": "working",
        "created_at_utc": now_iso(),
        "updated_at_utc": now_iso(),
        "last_test": None,
        "last_push_sha": None,
    }
    def mut(rows):
        rows.append(job)
        return job
    return locked_jobs(mut)


def get_job(job_id: str) -> dict[str, Any]:
    rows = locked_jobs()
    exact = [r for r in rows if isinstance(r, dict) and str(r.get("id")) == job_id]
    if not exact:
        raise DevError(f"job not found: {job_id}")
    return exact[-1]


def update_job(job_id: str, **changes: Any) -> dict[str, Any]:
    def mut(rows):
        for row in reversed(rows):
            if isinstance(row, dict) and str(row.get("id")) == job_id:
                row.update(changes)
                row["updated_at_utc"] = now_iso()
                return dict(row)
        raise DevError(f"job not found: {job_id}")
    return locked_jobs(mut)


def job_worktree(job: dict[str, Any]) -> Path:
    path = Path(str(job.get("worktree") or "")).resolve()
    try:
        path.relative_to(WORKTREES)
    except ValueError as exc:
        raise DevError("job worktree escaped the managed root") from exc
    if not (path / ".git").exists():
        raise DevError(f"worktree missing: {path}")
    branch = run(["git", "branch", "--show-current"], cwd=path).stdout.strip()
    if branch != job.get("branch") or not branch.startswith("hermes/dev/"):
        raise DevError("worktree branch identity mismatch")
    return path


def status(job_id: str | None) -> Any:
    if not job_id:
        rows = locked_jobs()
        return [
            {k: row.get(k) for k in ("id", "problem", "branch", "status", "created_at_utc", "updated_at_utc", "last_push_sha")}
            for row in rows[-20:] if isinstance(row, dict)
        ]
    job = get_job(job_id)
    wt = job_worktree(job)
    dirty = run(["git", "status", "--porcelain=v1"], cwd=wt).stdout.splitlines()
    head = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
    ahead = int(run(["git", "rev-list", "--count", f"{job['base_sha']}..HEAD"], cwd=wt).stdout.strip() or "0")
    return {**job, "head_sha": head, "ahead_commits": ahead, "dirty": dirty[:100]}


def diff(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    wt = job_worktree(job)
    stat = run(["git", "diff", "--stat", "--", "."], cwd=wt).stdout
    staged_stat = run(["git", "diff", "--cached", "--stat", "--", "."], cwd=wt).stdout
    text = run(["git", "diff", "--no-ext-diff", "--", "."], cwd=wt).stdout
    if len(text) > MAX_CAPTURE:
        text = text[:MAX_CAPTURE] + "\n... diff truncated ...\n"
    return {"id": job_id, "branch": job["branch"], "stat": stat, "staged_stat": staged_stat, "diff": text}


def run_test_profile(job_id: str, profile: str) -> dict[str, Any]:
    if profile not in TEST_PROFILES:
        raise DevError(f"unknown test profile: {profile}; allowed={','.join(sorted(TEST_PROFILES))}")
    job = get_job(job_id)
    wt = job_worktree(job)
    results = []
    ok = True
    for base_args in TEST_PROFILES[profile]:
        args = list(base_args)
        if profile == "ai-home-v2" and args[:3] == ["node", "--test", "tests/ai-home-v2"]:
            args = ["node", "--test", *[str(p.relative_to(wt)) for p in sorted((wt / "tests/ai-home-v2").glob("*.test.cjs"))]]
        try:
            cp = run(args, cwd=wt, check=False, timeout=600)
        except FileNotFoundError as exc:
            raise DevError(f"required test tool missing: {args[0]}") from exc
        combined = ((cp.stdout or "") + (cp.stderr or ""))[-12000:]
        results.append({"command": args, "returncode": cp.returncode, "output": combined})
        if cp.returncode != 0:
            ok = False
            break
    payload = {"profile": profile, "ok": ok, "at": now_iso(), "results": results}
    update_job(job_id, last_test={"profile": profile, "ok": ok, "at": payload["at"]})
    return payload


def changed_paths(wt: Path) -> list[str]:
    cp = run(["git", "status", "--porcelain=v1", "-z"], cwd=wt)
    parts = cp.stdout.split("\0")
    out = []
    for entry in parts:
        if not entry:
            continue
        path = entry[3:] if len(entry) >= 4 else entry
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        out.append(path)
    return sorted(set(out))


def validate_changed_paths(wt: Path) -> list[str]:
    paths = changed_paths(wt)
    if not paths:
        raise DevError("no changes to commit")
    for rel in paths:
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise DevError(f"unsafe changed path: {rel}")
        if any(rx.search(rel) for rx in FORBIDDEN_PATH_PATTERNS):
            raise DevError(f"secret/credential-shaped path is forbidden: {rel}")
        p = (wt / rel).resolve()
        try:
            p.relative_to(wt)
        except ValueError as exc:
            raise DevError(f"changed path escaped worktree: {rel}") from exc
        if p.exists() and p.is_file() and p.stat().st_size > 5_000_000:
            raise DevError(f"changed file too large for dev mode: {rel}")
    return paths


def commit(job_id: str, message: str) -> dict[str, Any]:
    message = re.sub(r"[\r\n]+", " ", message).strip()
    if not 3 <= len(message) <= 160:
        raise DevError("commit message must be 3..160 chars")
    job = get_job(job_id)
    wt = job_worktree(job)
    paths = validate_changed_paths(wt)
    run(["git", "diff", "--check"], cwd=wt)
    run(["git", "add", "-A", "--", "."], cwd=wt)
    run(["git", "diff", "--cached", "--check"], cwd=wt)
    run(["git", "commit", "-m", message], cwd=wt, timeout=180)
    sha = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
    update_job(job_id, status="committed", last_commit_sha=sha)
    return {"id": job_id, "branch": job["branch"], "commit": sha, "paths": paths}


def push(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    wt = job_worktree(job)
    dirty = run(["git", "status", "--porcelain=v1"], cwd=wt).stdout.strip()
    if dirty:
        raise DevError("worktree is dirty; commit before push")
    head = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
    if head == job.get("base_sha"):
        raise DevError("nothing committed ahead of base")
    env = {"GIT_TERMINAL_PROMPT": "0"}
    cp = run(["git", "push", "--porcelain", "--set-upstream", "origin", f"HEAD:refs/heads/{job['branch']}"], cwd=wt, check=False, env=env, timeout=180)
    if cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "push failed").strip()[-3000:]
        raise DevError("push failed without prompting for credentials: " + detail)
    update_job(job_id, status="pushed", last_push_sha=head)
    return {"id": job_id, "branch": job["branch"], "pushed_sha": head, "output": (cp.stdout + cp.stderr)[-5000:]}


def github_runs_for_branch(branch: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"branch": branch, "per_page": 30})
    url = f"https://api.github.com/repos/{REPO_FULL_NAME}/actions/runs?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"DVIZH-Hermes-Dev/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise DevError(f"GitHub Actions status unavailable: {type(exc).__name__}") from exc
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    return [r for r in runs if isinstance(r, dict)] if isinstance(runs, list) else []


def ci_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    wt = job_worktree(job)
    head = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
    rows = [r for r in github_runs_for_branch(job["branch"]) if str(r.get("head_sha") or "") == head]
    compact = [
        {
            "name": r.get("name"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "html_url": r.get("html_url"),
            "event": r.get("event"),
        }
        for r in rows[:20]
    ]
    completed = [r for r in rows if r.get("status") == "completed"]
    pending = [r for r in rows if r.get("status") != "completed"]
    failed = [r for r in completed if r.get("conclusion") != "success"]
    green = bool(rows) and not pending and not failed
    return {"id": job_id, "head_sha": head, "green": green, "pending": len(pending), "failed": len(failed), "runs": compact}


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def deploy_propose(job_id: str, script_rel: str) -> dict[str, Any]:
    job = get_job(job_id)
    wt = job_worktree(job)
    rel = Path(script_rel)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".sh":
        raise DevError("deploy script must be a relative .sh path inside the worktree")
    script = (wt / rel).resolve()
    try:
        script.relative_to(wt)
    except ValueError as exc:
        raise DevError("deploy script escaped worktree") from exc
    if not script.is_file():
        raise DevError("deploy script not found")
    tracked = run(["git", "ls-files", "--error-unmatch", str(rel)], cwd=wt, check=False)
    if tracked.returncode != 0:
        raise DevError("deploy script must be tracked by git")
    run(["bash", "-n", str(script)], cwd=wt)
    dirty = run(["git", "status", "--porcelain=v1"], cwd=wt).stdout.strip()
    if dirty:
        raise DevError("worktree must be clean before deploy proposal")
    head = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
    remote = run(["git", "ls-remote", "origin", f"refs/heads/{job['branch']}"], cwd=wt, env={"GIT_TERMINAL_PROMPT": "0"}, check=False, timeout=60)
    remote_sha = (remote.stdout.split() or [""])[0]
    if remote.returncode != 0 or remote_sha != head:
        raise DevError("branch HEAD is not confirmed on origin")
    ci = ci_status(job_id)
    if not ci["green"]:
        raise DevError("CI is not fully green for the current HEAD")
    proposal_id = "deploy-" + secrets.token_hex(5)
    url = f"https://raw.githubusercontent.com/{REPO_FULL_NAME}/{head}/{urllib.parse.quote(str(rel))}"
    proposal = {
        "id": proposal_id,
        "job_id": job_id,
        "status": "pending-user-approval",
        "created_at_utc": now_iso(),
        "branch": job["branch"],
        "commit": head,
        "script": str(rel),
        "git_blob": git_blob_sha(script),
        "url": url,
        "command": f"curl -fsSL {url} | sudo bash",
        "ci": ci,
        "note": "INERT proposal only. dvizhdevctl has no deploy/apply command.",
    }
    ensure_dirs()
    target = PROPOSALS_DIR / f"{proposal_id}.json"
    target.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    update_job(job_id, status="deploy-proposed", deploy_proposal=proposal_id)
    return proposal


def live_snapshot() -> dict[str, Any]:
    files = [
        "/opt/dvizh/static/index.html",
        "/opt/dvizh/static/manual.html",
        "/opt/dvizh/static/app.js",
        "/opt/dvizh/static/styles.css",
        "/opt/dvizh/static/sw.js",
        "/opt/dvizh/server.py",
    ]
    rows = []
    for raw in files:
        p = Path(raw)
        if not p.is_file() or p.is_symlink():
            rows.append({"path": raw, "present": False})
            continue
        try:
            data = p.read_bytes()
            rows.append({"path": raw, "present": True, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        except PermissionError:
            rows.append({"path": raw, "present": True, "readable": False})
    services = {}
    if shutil.which("systemctl"):
        for name in ("dvizh.service", "dvizh-auth.service", "dvizh-ai-home.service", "dvizh-telegram.service"):
            cp = run(["systemctl", "is-active", name], check=False, timeout=10)
            services[name] = cp.stdout.strip() or f"rc={cp.returncode}"
    return {"version": VERSION, "at": now_iso(), "files": rows, "services": services}


def close_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    wt = job_worktree(job)
    if run(["git", "status", "--porcelain=v1"], cwd=wt).stdout.strip():
        raise DevError("refusing to close a dirty worktree")
    run(["git", "worktree", "remove", str(wt)], cwd=REPO, timeout=120)
    update_job(job_id, status="closed", closed_at_utc=now_iso())
    return {"id": job_id, "status": "closed", "branch": job["branch"]}


def config() -> dict[str, Any]:
    return {
        "version": VERSION,
        "repo_full_name": REPO_FULL_NAME,
        "repo_url": REPO_URL,
        "base_branch": BASE_BRANCH,
        "root": str(ROOT),
        "repo": str(REPO),
        "worktrees": str(WORKTREES),
        "test_profiles": sorted(TEST_PROFILES),
        "deploy_capability": "proposal-only; no apply/deploy command exists",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe worktree controller for Hermes DVIZH development")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    sub.add_parser("config")
    sub.add_parser("init")
    p_new = sub.add_parser("new"); p_new.add_argument("problem")
    p_status = sub.add_parser("status"); p_status.add_argument("job_id", nargs="?")
    p_where = sub.add_parser("where"); p_where.add_argument("job_id")
    p_diff = sub.add_parser("diff"); p_diff.add_argument("job_id")
    p_test = sub.add_parser("test"); p_test.add_argument("job_id"); p_test.add_argument("profile", choices=sorted(TEST_PROFILES))
    p_commit = sub.add_parser("commit"); p_commit.add_argument("job_id"); p_commit.add_argument("message")
    p_push = sub.add_parser("push"); p_push.add_argument("job_id")
    p_ci = sub.add_parser("ci"); p_ci.add_argument("job_id")
    p_deploy = sub.add_parser("deploy-propose"); p_deploy.add_argument("job_id"); p_deploy.add_argument("script")
    sub.add_parser("live-snapshot")
    p_close = sub.add_parser("close"); p_close.add_argument("job_id")
    args = parser.parse_args()
    try:
        if args.cmd == "version":
            print(VERSION); return 0
        if args.cmd == "config": result = config()
        elif args.cmd == "init": ensure_repo(); result = {"ok": True, **config()}
        elif args.cmd == "new": result = new_job(args.problem)
        elif args.cmd == "status": result = status(args.job_id)
        elif args.cmd == "where": result = {"id": args.job_id, "worktree": str(job_worktree(get_job(args.job_id)))}
        elif args.cmd == "diff": result = diff(args.job_id)
        elif args.cmd == "test": result = run_test_profile(args.job_id, args.profile)
        elif args.cmd == "commit": result = commit(args.job_id, args.message)
        elif args.cmd == "push": result = push(args.job_id)
        elif args.cmd == "ci": result = ci_status(args.job_id)
        elif args.cmd == "deploy-propose": result = deploy_propose(args.job_id, args.script)
        elif args.cmd == "live-snapshot": result = live_snapshot()
        elif args.cmd == "close": result = close_job(args.job_id)
        else: raise DevError("unsupported command")
        out_json(result)
        return 0
    except (DevError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
