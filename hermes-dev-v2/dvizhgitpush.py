#!/usr/bin/python3 -I
from __future__ import annotations

import argparse
import tempfile
import pwd
import contextlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "2026.09.11-dvizh-git-push-gate.2.3.2"
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
    clean = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1",
             "GIT_TERMINAL_PROMPT": "0"}
    if env:
        clean.update(env)
    identity = {}
    # All -C operations outside our private bare boundary are caller reads.
    if "-C" in args and str(Path(args[args.index("-C")+1])) not in TRUSTED_REPOS and os.geteuid() == 0:
        uid, gid = invoking_identity()
        identity = dict(user=uid, group=gid, extra_groups=[])
    cp = subprocess.run(args, cwd=str(cwd or Path("/")), env=clean, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                        timeout=timeout, **identity)
    if check and cp.returncode != 0:
        raise GateError((cp.stderr or cp.stdout or "command failed").strip()[-4000:])
    return cp


def require_root() -> None:
    if os.geteuid() == 0 and (TEST_MODE or TEST_HOME or KEY != Path("/var/lib/dvizh/autopilot-github/id_ed25519")):
        raise GateError("root cannot use fixture overrides")
    if not TEST_MODE and os.geteuid() != 0:
        raise GateError("dvizhgitpush must run as root")


def caller_home() -> tuple[str, Path]:
    user = os.environ.get("SUDO_USER", "").strip()
    if TEST_MODE and TEST_HOME:
        return user or "tester", Path(TEST_HOME).resolve()
    if not re.fullmatch(r"[a-z_][a-z0-9_-]*", user):
        raise GateError("missing or invalid SUDO_USER")
    invoking_identity()
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
    return ["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "credential.helper=", "-c", "core.sshCommand=/bin/false",
            "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never",
            "-c", "core.attributesFile=/dev/null", "-c", "diff.external=",
            "-C", str(wt), *args]


def validate_worktree(home: Path, job_id: str, job: dict[str, Any]) -> tuple[Path, str, str]:
    managed = (home / ".hermes/dev/dvizh/worktrees").resolve()
    wt = Path(str(job.get("worktree") or "")).resolve()
    expected = (managed / job_id).resolve()
    if wt != expected or not wt.is_dir():
        raise GateError("job worktree is outside the managed DVIZH root")
    branch = run(git_args(wt, "branch", "--show-current")).stdout.strip()
    expected_prefix = f"hermes/dev/{job_id}-"
    if not re.fullmatch(r"hermes/dev/[0-9]{8}-[0-9]{6}-[0-9a-f]{6}-[A-Za-z0-9_-]+", branch) or not branch.startswith(expected_prefix) or branch != str(job.get("branch") or ""):
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
    return owner_manifest()["base"]


def ensure_commit(wt: Path, sha: str) -> None:
    if run(git_args(wt, "cat-file", "-e", f"{sha}^{{commit}}"), check=False).returncode == 0:
        return
    raise GateError("trusted base commit is absent from caller export")


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
    commits = run(git_args(wt, "rev-list", f"{merge}..{head}")).stdout.split()
    raw = "".join(run(git_args(wt, "diff-tree", "--no-commit-id", "--no-renames", "--name-only", "-r", "-z", sha+"^", sha)).stdout for sha in commits)
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
    return {"GIT_SSH_COMMAND": f"/usr/bin/ssh -F /dev/null -i {KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes", "GIT_TERMINAL_PROMPT": "0"}


def doctor() -> dict[str, Any]:
    require_root()
    # Use the same external authorization contract as the production gate.
    # Report status only: never return manifest bytes or validation exceptions.
    try:
        owner_manifest()
        owner_authorized = True
    except GateError:
        owner_authorized = False
    key_ok = KEY.is_file() and not KEY.is_symlink()
    authorized = False
    detail = "key missing"
    if key_ok:
        cp = run(["git", "ls-remote", f"git@github.com:{REPO}.git", "HEAD"], check=False, timeout=30, env=ssh_env())
        authorized = cp.returncode == 0
        detail = "transport authorized" if authorized else "transport authorization failed"
    return {"ok": owner_authorized and key_ok and authorized, "owner_authorized": owner_authorized, "version": VERSION, "repo": REPO, "base_branch": BASE_BRANCH, "key_present": key_ok, "authorized": authorized, "detail": detail}


def push(job_id: str) -> dict[str, Any]:
    require_root()
    _, home = caller_home()
    job = load_job(home, job_id)
    wt, branch, head = validate_worktree(home, job_id, job)
    base = public_base_sha()
    ensure_commit(wt, base)
    paths = changed_paths(wt, base, head)
    with immutable_export(wt, head) as boundary:
        paths = changed_paths(boundary, base, head)
        if TEST_MODE:
            return {"ok": True, "status": "validated-test", "branch": branch, "head": head, "base": base, "paths": paths}
        verify_local_pins(boundary, base, head)
        cp = run(git_args(boundary, "-c", "core.sshCommand="+ssh_env()["GIT_SSH_COMMAND"],
                          "push", "--porcelain", f"git@github.com:{REPO}.git",
                          f"{head}:refs/heads/{branch}"), check=False, timeout=180)
        if cp.returncode != 0:
            raise GateError("guarded push failed: " + (cp.stderr or cp.stdout).strip()[-3000:])
    return {"ok": True, "status": "pushed", "branch": branch, "head": head, "base": base, "paths": paths}


# Owner approval is installed independently of candidate source and CI.
# The base contains the approved workflows/validators; it does not contain its
# own digest. No candidate branch or environment can select this manifest.
OWNER_APPROVAL = Path('/var/lib/dvizh-release-gate/owner-approval.json')
PIN_PATHS = {
    '.github/workflows/dvizh-hermes-autopilot.yml',
    '.github/workflows/dvizh-hermes-autopilot-v2-tests.yml',
    '.github/workflows/dvizh-hermes-autopilot-installer-smoke.yml',
    'hermes-dev-v2/dvizhgitpush.py',
    'hermes-dev-v2/dvizhrelease.py',
}


def owner_manifest():
    import stat
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in OWNER_APPROVAL.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
            st=os.fstat(fd)
            if st.st_uid != 0 or st.st_gid != 0 or st.st_mode & 0o022:
                raise GateError('untrusted owner approval directory')
        child=os.open(OWNER_APPROVAL.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(child,'rb') as stream:
            st=os.fstat(stream.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_gid != 0 or st.st_mode & 0o022 or st.st_nlink != 1:
                raise GateError('unsafe owner approval file')
            raw=stream.read(65537)
            if len(raw)>65536: raise GateError('oversized owner approval')
        def unique(pairs):
            out={}
            for k,v in pairs:
                if k in out: raise GateError('duplicate approval field')
                out[k]=v
            return out
        d=json.loads(raw,object_pairs_hook=unique)
        if (not isinstance(d, dict) or set(d) != {'schema','version','base','pins'} or d['schema'] != 1 or d['version'] != '2.3.2'
            or not re.fullmatch('[0-9a-f]{40}', d['base']) or not isinstance(d['pins'], dict) or set(d['pins']) != PIN_PATHS
            or any(not re.fullmatch('[0-9a-f]{40}',v) for v in d['pins'].values())):
            raise GateError('invalid owner approval contract')
        return d
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise GateError('owner approval unavailable or invalid') from exc
    finally:
        os.close(fd)


TRUSTED_REPOS: set[str] = set()


def invoking_identity():
    """sudo's authenticated numeric caller identity, cross-checked with passwd.

    The installed sudo command must retain its normal env_reset contract.
    Root-direct use with no unprivileged invoking identity is rejected.
    """
    try:
        uid = int(os.environ['SUDO_UID'])
        gid = int(os.environ['SUDO_GID'])
        entry = pwd.getpwuid(uid)
    except (KeyError, ValueError) as exc:
        raise GateError('authenticated invoking identity missing') from exc
    if uid <= 0 or gid != entry.pw_gid or os.environ.get('SUDO_USER') != entry.pw_name:
        raise GateError('invoking identity mismatch')
    return uid, gid


@contextlib.contextmanager
def immutable_export(wt, head):
    """Only opaque pack bytes cross from caller Git to a fresh private bare repo.

    No config, hooks, alternates, refs, shallow files or worktree files are copied.
    An attacker can replace the pack, but cannot change validated SHA identities.
    """
    import resource
    if not re.fullmatch('[0-9a-f]{40}', head):
        raise GateError('invalid export commit')
    with tempfile.TemporaryDirectory(prefix='dvizh-push-', dir='/tmp') as td:
        boundary = Path(td)/'objects.git'
        env = {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'LANG':'C.UTF-8',
               'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
               'GIT_CONFIG_SYSTEM':'/dev/null', 'GIT_NO_REPLACE_OBJECTS':'1',
               'GIT_TERMINAL_PROMPT':'0'}
        identity = {}
        if os.geteuid() == 0:
            uid,gid=invoking_identity()
            identity=dict(user=uid,group=gid,extra_groups=[])
        def limits():
            resource.setrlimit(resource.RLIMIT_FSIZE,(100_000_000,100_000_000))
        with tempfile.TemporaryFile(dir=td) as pack:
            cp=subprocess.run(git_args(wt,'pack-objects','--stdout','--revs'),
                              input=(head+'\n').encode(), stdout=pack, stderr=subprocess.PIPE,
                              cwd='/', env=env, timeout=120, preexec_fn=limits, **identity)
            if cp.returncode:
                raise GateError('caller export failed')
            run(['/usr/bin/git','init','--bare','--template=',str(boundary)])
            TRUSTED_REPOS.add(str(boundary))
            try:
                pack.seek(0)
                cp=subprocess.run(git_args(boundary,'index-pack','--stdin','--strict'),
                                  stdin=pack,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                  cwd='/',env=env,timeout=120)
                if cp.returncode:
                    raise GateError('invalid exported objects')
                run(git_args(boundary,'cat-file','-e',head+'^{commit}'))
                yield boundary
            finally:
                TRUSTED_REPOS.discard(str(boundary))


def verify_local_pins(wt, base, head):
    approval=owner_manifest()
    if base != approval['base']:
        raise GateError('unapproved base')
    for rev in (base,head):
        for name,sha in approval['pins'].items():
            actual=run(git_args(wt,'rev-parse',rev+':'+name)).stdout.strip()
            if actual != sha:
                raise GateError('owner-pinned blob mismatch: '+name)


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
