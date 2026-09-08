#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2026.09.08-hermes-autopilot.1"
REPO_FULL_NAME = os.environ.get("DVIZH_DEV_REPO_FULL_NAME", "Itosyro/voice-bot").strip()
BASE_BRANCH = os.environ.get("DVIZH_AUTOPILOT_BASE_BRANCH", "codex/hermes-autopilot-v2-2026-09-08").strip()
HOME = Path.home()
ROOT = Path(os.environ.get("DVIZH_DEV_ROOT", str(HOME / ".hermes" / "dev" / "dvizh"))).expanduser().resolve()
REPO = ROOT / "repo"
STATE = ROOT / "state" / "autopilot"
KEY = Path(os.environ.get("DVIZH_AUTOPILOT_GITHUB_KEY", str(ROOT / "github" / "id_ed25519"))).expanduser().resolve()
CTL = Path(os.environ.get("DVIZH_DEV_CTL", "/usr/local/bin/dvizhdevctl"))
RELEASE = Path(os.environ.get("DVIZH_RELEASE_CTL", "/usr/local/sbin/dvizhrelease"))
MODES = {"inspect", "safe", "auto"}
MAX_OUTPUT = 16000


class AutoError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run(args: list[str], *, check: bool = True, timeout: int = 180, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["DVIZH_DEV_BASE_BRANCH"] = BASE_BRANCH
    merged["GIT_TERMINAL_PROMPT"] = "0"
    if env:
        merged.update(env)
    cp = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout, env=merged)
    if check and cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "command failed").strip()[-5000:]
        raise AutoError(f"command failed ({' '.join(args[:3])}): {detail}")
    return cp


def ctl(*args: str, check: bool = True, timeout: int = 180) -> dict[str, Any]:
    if not CTL.is_file():
        raise AutoError(f"dvizhdevctl not installed: {CTL}")
    cp = run([str(CTL), *args], check=check, timeout=timeout)
    if not cp.stdout.strip():
        if check:
            raise AutoError((cp.stderr or "empty dvizhdevctl response").strip())
        return {"returncode": cp.returncode, "stdout": cp.stdout, "stderr": cp.stderr}
    try:
        value = json.loads(cp.stdout)
    except json.JSONDecodeError as exc:
        raise AutoError(f"invalid dvizhdevctl JSON: {cp.stdout[-2000:]}") from exc
    if not isinstance(value, dict):
        raise AutoError("unexpected dvizhdevctl response type")
    return value


def ensure_state() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    try:
        STATE.chmod(0o700)
    except OSError:
        pass


def mode_path(job_id: str) -> Path:
    return STATE / f"{job_id}.json"


def save_mode(job_id: str, mode: str) -> None:
    ensure_state()
    p = mode_path(job_id)
    p.write_text(json.dumps({"job_id": job_id, "mode": mode, "updated_at_utc": now_iso()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(p, 0o600)


def get_mode(job_id: str) -> str:
    p = mode_path(job_id)
    if not p.is_file():
        return "safe"
    try:
        mode = str(json.loads(p.read_text(encoding="utf-8")).get("mode") or "safe")
    except Exception:
        mode = "safe"
    return mode if mode in MODES else "safe"


def ssh_command() -> str:
    return f"ssh -i {KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"


def configure_git_remote() -> dict[str, Any]:
    ctl("init")
    if not REPO.is_dir():
        raise AutoError(f"managed repo missing: {REPO}")
    if not KEY.is_file():
        raise AutoError(f"GitHub deploy key missing: {KEY}")
    run(["git", "-C", str(REPO), "remote", "set-url", "origin", f"git@github.com:{REPO_FULL_NAME}.git"])
    run(["git", "-C", str(REPO), "config", "core.sshCommand", ssh_command()])
    probe = run(["git", "-C", str(REPO), "ls-remote", "origin", "HEAD"], check=False, timeout=30)
    return {
        "ok": probe.returncode == 0,
        "remote": f"git@github.com:{REPO_FULL_NAME}.git",
        "key": str(KEY),
        "public_key": str(KEY) + ".pub",
        "detail": (probe.stderr or probe.stdout).strip()[-2000:],
    }


def api_json(url: str, timeout: int = 20) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"DVIZH-Hermes-Autopilot/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AutoError(f"GitHub API HTTP {exc.code}: {url}") from exc
    except Exception as exc:
        raise AutoError(f"GitHub API unavailable: {type(exc).__name__}") from exc


def new_job(mode: str, problem: str) -> dict[str, Any]:
    if mode not in MODES:
        raise AutoError(f"unknown mode: {mode}")
    if mode == "inspect":
        return {"mode": mode, "production": "read-only", "instruction": "Use read-only diagnostics; do not create a worktree unless code changes are requested."}
    job = ctl("new", problem, timeout=300)
    job_id = str(job.get("id") or "")
    if not job_id:
        raise AutoError("new job response has no id")
    save_mode(job_id, mode)
    return {**job, "mode": mode, "autopilot_base": BASE_BRANCH}


def changed_files(job_id: str) -> list[str]:
    status = ctl("status", job_id)
    wt = Path(str(status.get("worktree") or ""))
    if not wt.is_dir():
        raise AutoError("managed worktree missing")
    base = str(status.get("base_sha") or "")
    head = str(status.get("head_sha") or "")
    if not base or not head:
        raise AutoError("job lacks base/head identity")
    cp = run(["git", "-C", str(wt), "diff", "--name-only", base, head, "--", "."], check=False)
    if cp.returncode != 0:
        raise AutoError((cp.stderr or "git diff failed").strip())
    return [line.strip() for line in cp.stdout.splitlines() if line.strip()]


def test_profiles_for(paths: list[str]) -> list[str]:
    profiles = ["quick"]
    if any(p.startswith("ai-home-v2/") or p.startswith("tests/ai-home-v2/") for p in paths):
        profiles.append("ai-home-v2")
    if any(p.startswith("hermes-control-v1/") for p in paths):
        profiles.append("hermes-control")
    if any(p.startswith("dvizh-telegram-v1/") for p in paths):
        profiles.append("telegram")
    return profiles


def run_profiles(job_id: str) -> dict[str, Any]:
    status = ctl("status", job_id)
    wt = Path(str(status.get("worktree") or ""))
    dirty = status.get("dirty") or []
    if dirty:
        cp = run(["git", "-C", str(wt), "status", "--porcelain=v1"], check=False)
        paths = []
        for line in cp.stdout.splitlines():
            raw = line[3:] if len(line) >= 4 else line
            if " -> " in raw:
                raw = raw.split(" -> ", 1)[1]
            if raw:
                paths.append(raw)
    else:
        paths = changed_files(job_id)
    profiles = test_profiles_for(paths)
    results = []
    for profile in profiles:
        payload = ctl("test", job_id, profile, timeout=900)
        results.append(payload)
        if not payload.get("ok"):
            return {"ok": False, "profiles": profiles, "results": results, "paths": paths}
    return {"ok": True, "profiles": profiles, "results": results, "paths": paths}


def push(job_id: str) -> dict[str, Any]:
    auth = configure_git_remote()
    if not auth["ok"]:
        raise AutoError("GitHub write deploy key is not authorized for the repository")
    status = ctl("status", job_id)
    wt = Path(str(status.get("worktree") or ""))
    run(["git", "-C", str(wt), "remote", "set-url", "origin", f"git@github.com:{REPO_FULL_NAME}.git"])
    run(["git", "-C", str(wt), "config", "core.sshCommand", ssh_command()])
    return ctl("push", job_id, timeout=300)


def runs_for(job_id: str) -> dict[str, Any]:
    return ctl("ci", job_id)


def wait_ci(job_id: str, timeout: int, interval: int = 8) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    seen = False
    while time.monotonic() < deadline:
        last = runs_for(job_id)
        if last.get("runs"):
            seen = True
        if last.get("green"):
            return {**last, "waited": True, "timed_out": False}
        if seen and int(last.get("pending") or 0) == 0 and int(last.get("failed") or 0) > 0:
            return {**last, "waited": True, "timed_out": False}
        time.sleep(max(2, interval))
    return {**last, "waited": True, "timed_out": True}


def ci_failures(job_id: str) -> dict[str, Any]:
    ci = runs_for(job_id)
    rows = [r for r in ci.get("runs", []) if isinstance(r, dict) and r.get("conclusion") not in (None, "success")]
    details = []
    for row in rows[:8]:
        url = str(row.get("html_url") or "")
        run_id = ""
        m = __import__("re").search(r"/actions/runs/(\d+)", url)
        if m:
            run_id = m.group(1)
        jobs = []
        if run_id:
            try:
                payload = api_json(f"https://api.github.com/repos/{REPO_FULL_NAME}/actions/runs/{run_id}/jobs?per_page=100")
                for j in (payload.get("jobs") or []) if isinstance(payload, dict) else []:
                    if not isinstance(j, dict):
                        continue
                    jobs.append({
                        "name": j.get("name"),
                        "status": j.get("status"),
                        "conclusion": j.get("conclusion"),
                        "html_url": j.get("html_url"),
                        "failed_steps": [s.get("name") for s in (j.get("steps") or []) if isinstance(s, dict) and s.get("conclusion") == "failure"],
                    })
            except AutoError:
                jobs = []
        details.append({"workflow": row, "jobs": jobs})
    return {"id": job_id, "green": ci.get("green"), "failures": details}


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def release_propose(job_id: str, manifest_rel: str) -> dict[str, Any]:
    mode = get_mode(job_id)
    if mode == "inspect":
        raise AutoError("inspect mode cannot create releases")
    status = ctl("status", job_id)
    if status.get("dirty"):
        raise AutoError("worktree must be clean before release proposal")
    wt = Path(str(status.get("worktree") or ""))
    branch = str(status.get("branch") or "")
    head = str(status.get("head_sha") or "")
    if not branch.startswith("hermes/dev/"):
        raise AutoError("release proposals require a managed Hermes branch")
    rel = Path(manifest_rel)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".json":
        raise AutoError("release manifest must be a relative .json file")
    manifest = (wt / rel).resolve()
    try:
        manifest.relative_to(wt)
    except ValueError as exc:
        raise AutoError("release manifest escaped worktree") from exc
    if not manifest.is_file():
        raise AutoError("release manifest not found")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AutoError("invalid release manifest JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise AutoError("release manifest schema must equal 1")
    if str(payload.get("commit") or "") not in ("", head):
        raise AutoError("manifest commit does not match current HEAD")
    tracked = run(["git", "-C", str(wt), "ls-files", "--error-unmatch", str(rel)], check=False)
    if tracked.returncode != 0:
        raise AutoError("release manifest must be committed")
    remote = run(["git", "-C", str(wt), "ls-remote", "origin", f"refs/heads/{branch}"], check=False, timeout=60)
    remote_sha = (remote.stdout.split() or [""])[0]
    if remote.returncode != 0 or remote_sha != head:
        raise AutoError("current HEAD is not confirmed on origin")
    ci = runs_for(job_id)
    if not ci.get("green"):
        raise AutoError("CI must be fully green before release proposal")
    ensure_state()
    proposal_id = f"release-{job_id}-{head[:10]}"
    proposal = {
        "schema": 1,
        "id": proposal_id,
        "job_id": job_id,
        "mode": mode,
        "repo": REPO_FULL_NAME,
        "branch": branch,
        "commit": head,
        "manifest": str(rel),
        "manifest_blob": git_blob(manifest),
        "created_at_utc": now_iso(),
    }
    p = STATE / f"{proposal_id}.json"
    p.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(p, 0o600)
    return {**proposal, "proposal_path": str(p), "ci": ci}


def release_call(action: str, proposal: str, approval: str | None = None) -> dict[str, Any]:
    if not RELEASE.is_file():
        raise AutoError(f"release gate not installed: {RELEASE}")
    args = ["sudo", "-n", str(RELEASE), action, proposal]
    if approval:
        args.extend(["--approval", approval])
    cp = run(args, check=False, timeout=300)
    text = cp.stdout.strip()
    try:
        payload = json.loads(text) if text else {}
    except Exception:
        payload = {"raw": text[-MAX_OUTPUT:]}
    if cp.returncode != 0:
        payload.update({"ok": False, "returncode": cp.returncode, "stderr": cp.stderr.strip()[-5000:]})
    return payload


def doctor() -> dict[str, Any]:
    result: dict[str, Any] = {"version": VERSION, "base_branch": BASE_BRANCH, "repo": REPO_FULL_NAME}
    try:
        result["git"] = configure_git_remote()
    except Exception as exc:
        result["git"] = {"ok": False, "error": str(exc)}
    try:
        api_json(f"https://api.github.com/repos/{REPO_FULL_NAME}")
        result["github_api"] = {"ok": True}
    except Exception as exc:
        result["github_api"] = {"ok": False, "error": str(exc)}
    gate = run(["sudo", "-n", str(RELEASE), "doctor"], check=False, timeout=20) if RELEASE.is_file() else None
    result["release_gate"] = {
        "ok": bool(gate and gate.returncode == 0),
        "stdout": gate.stdout.strip()[-3000:] if gate else "",
        "stderr": gate.stderr.strip()[-3000:] if gate else "not installed",
    }
    result["ok"] = bool(result.get("git", {}).get("ok") and result.get("github_api", {}).get("ok") and result.get("release_gate", {}).get("ok"))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes DVIZH Autopilot v2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    sub.add_parser("doctor")
    p_new = sub.add_parser("new"); p_new.add_argument("mode", choices=sorted(MODES)); p_new.add_argument("problem")
    p_mode = sub.add_parser("mode"); p_mode.add_argument("job_id")
    p_tests = sub.add_parser("test-auto"); p_tests.add_argument("job_id")
    p_push = sub.add_parser("push"); p_push.add_argument("job_id")
    p_wait = sub.add_parser("wait-ci"); p_wait.add_argument("job_id"); p_wait.add_argument("--timeout", type=int, default=1200)
    p_fail = sub.add_parser("ci-failures"); p_fail.add_argument("job_id")
    p_prop = sub.add_parser("release-propose"); p_prop.add_argument("job_id"); p_prop.add_argument("manifest")
    p_plan = sub.add_parser("release-plan"); p_plan.add_argument("proposal")
    p_apply = sub.add_parser("release-apply"); p_apply.add_argument("proposal"); p_apply.add_argument("--approval")
    args = parser.parse_args()
    try:
        if args.cmd == "version":
            print(VERSION); return 0
        if args.cmd == "doctor": result = doctor()
        elif args.cmd == "new": result = new_job(args.mode, args.problem)
        elif args.cmd == "mode": result = {"job_id": args.job_id, "mode": get_mode(args.job_id)}
        elif args.cmd == "test-auto": result = run_profiles(args.job_id)
        elif args.cmd == "push": result = push(args.job_id)
        elif args.cmd == "wait-ci": result = wait_ci(args.job_id, max(30, min(args.timeout, 3600)))
        elif args.cmd == "ci-failures": result = ci_failures(args.job_id)
        elif args.cmd == "release-propose": result = release_propose(args.job_id, args.manifest)
        elif args.cmd == "release-plan": result = release_call("plan", args.proposal)
        elif args.cmd == "release-apply": result = release_call("apply", args.proposal, args.approval)
        else: raise AutoError("unsupported command")
        emit(result)
        return 0 if result.get("ok", True) is not False else 2
    except (AutoError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
