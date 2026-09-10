#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import functools
import signal
import threading
from contextlib import contextmanager
import stat
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2026.09.09-dvizh-release-gate.2.2"
REPO = "Itosyro/voice-bot"
BACKUP_ROOT = Path(os.environ.get("DVIZH_RELEASE_BACKUP_ROOT", "/var/lib/dvizh/backups"))
APPROVAL_ROOT = Path(os.environ.get("DVIZH_RELEASE_APPROVAL_ROOT", "/var/lib/dvizh/autopilot-approvals"))
FS_ROOT = Path(os.environ.get("DVIZH_RELEASE_FS_ROOT", "/"))
SOURCE_ROOT = os.environ.get("DVIZH_RELEASE_SOURCE_ROOT", "").strip()
HTTP_BASE = os.environ.get("DVIZH_RELEASE_HTTP_BASE", "http://127.0.0.1:8000").rstrip("/")
TEST_MODE = os.environ.get("DVIZH_RELEASE_TEST_MODE", "0") == "1"
MAX_PROPOSAL = 65536
MAX_MANIFEST = 131072
MAX_FILE = 5_000_000
APPROVAL_TTL = 1800

SAFE_TARGETS = {
    "/opt/dvizh/static/index.html": "/",
    "/opt/dvizh/static/ai-home-v2.js": "/ai-home-v2.js",
    "/opt/dvizh/static/ai-home-v2.css": "/ai-home-v2.css",
}
APPROVAL_TARGETS = {
    "/opt/dvizh/static/manual.html",
    "/opt/dvizh/static/app.js",
    "/opt/dvizh/static/sync.js",
    "/opt/dvizh/static/styles.css",
    "/opt/dvizh/static/sw.js",
    "/opt/dvizh/server.py",
    "/opt/dvizh/jump_web_bridge.py",
}
APPROVAL_PREFIXES = ("/opt/dvizh-ai-home/",)
ALLOWED_RESTARTS = {"dvizh.service", "dvizh-ai-home.service", "dvizh-jump.service"}
DENY_PREFIXES = ("/var/lib/", "/etc/", "/usr/local/", "/home/", "/root/", "/boot/", "/proc/", "/sys/", "/dev/")

# v2.2 owner maintenance extension; the separate installer still pins v2.1.
PRIVILEGED_CLASS = "ai-integration-privileged"
PRIVILEGED_TARGETS = {
    "/usr/local/libexec/dvizh-context": ("hermes-control-v1/dvizh_context.py", "python-syntax"),
    "/usr/local/libexec/dvizh-proposals": ("hermes-control-v1/dvizh_proposals.py", "python-syntax"),
    "/opt/dvizh-ai-approval/proposal_bridge.py": ("hermes-control-v1/dvizh_proposal_bridge.py", "python-syntax-service"),
}
BRIDGE_SERVICE = "dvizh-ai-approval.service"
BRIDGE_TARGET = "/opt/dvizh-ai-approval/proposal_bridge.py"
PRIVILEGED_FIELDS = {"source", "target", "sha256", "release_class", "required_owner", "required_mode", "verification"}


def canonical_path(value: str, *, absolute: bool) -> bool:
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and "\0" not in value and value.startswith("/") == absolute
            and not value.startswith("//") and str(Path(value)) == value
            and ".." not in Path(value).parts)


class GateError(RuntimeError):
    pass



_STATE = threading.local()


def identity(fd: int) -> tuple[int, int]:
    st = os.fstat(fd)
    return st.st_dev, st.st_ino


class JournalCleanupError(GateError):
    pass


def trusted_directory(fd: int, path: Path) -> None:
    # TEST_MODE already substitutes the invoking UID/GID and fixture roots.
    # /tmp and the fixture's host ancestors are not privileged target ancestors.
    if TEST_MODE and not any(path == root or root in path.parents
                             for root in (FS_ROOT, APPROVAL_ROOT, BACKUP_ROOT)):
        return
    st = os.fstat(fd)
    if st.st_uid != (os.geteuid() if TEST_MODE else 0) or st.st_mode & 0o022:
        raise GateError(f"untrusted writable/non-root ancestor: {path}")


@contextmanager
def transaction():
    require_root()
    if getattr(_STATE, "locked", False):
        yield
        return
    # Fixed control-state directory; no caller-selected journal/recovery paths.
    parent = walk_parent(APPROVAL_ROOT / "transaction.lock", create=True, trusted=True)
    fd = None
    try:
        fd = os.open("transaction.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != (os.geteuid() if TEST_MODE else 0) or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1:
            raise GateError("unsafe transaction lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        if os.stat("transaction.lock", dir_fd=parent, follow_symlinks=False).st_ino != st.st_ino:
            raise GateError("transaction lock identity changed")
        canonical_parent(APPROVAL_ROOT / "transaction.lock", parent)
        os.fsync(fd)
        os.fsync(parent)
        _STATE.locked = True
        _STATE.parents = {}
        _STATE.rolling_back = False
        _STATE.privileged_paths = set()
        handlers = {}
        try:
            if threading.current_thread() is threading.main_thread():
                def terminate(signum, frame):
                    if not _STATE.rolling_back:
                        _STATE.rolling_back = True
                        raise GateError(f"termination signal {signum}")
                for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                    handlers[sig] = signal.signal(sig, terminate)
            if os.path.lexists(APPROVAL_ROOT / "pending.json"):
                raise GateError("interrupted pending transaction; owner recovery required before plan/apply")
            yield
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
            for handle in _STATE.parents.values():
                os.close(handle)
            _STATE.parents = {}
            _STATE.locked = False
            _STATE.rolling_back = False
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def serialized(fn):
    @functools.wraps(fn)
    def call(*args, **kwargs):
        with transaction():
            return fn(*args, **kwargs)
    return call


def journal_clear(journal) -> None:
    try:
        parent = open_parent(APPROVAL_ROOT / "pending.json")
        try:
            os.unlink("pending.json", dir_fd=parent)
            os.fsync(parent)
        finally:
            os.close(parent)
    except BaseException as failure:
        with rollback_signals():
            errors = [f"journal cleanup unconfirmed: {failure}"]
            try:
                atomic_write(APPROVAL_ROOT / "pending.json", json.dumps(journal, sort_keys=True).encode(),
                             {"uid": os.geteuid(), "gid": os.getegid(), "mode": 0o600})
            except BaseException as exc:
                errors.append(f"cannot re-arm pending journal: {exc}")
            raise JournalCleanupError(f"CRITICAL: journal cleanup unconfirmed; backup={journal['backup']}; errors={errors}") from failure


@contextmanager
def rollback_signals():
    # A second catchable termination must not interrupt restoration.
    handlers = {}
    _STATE.rolling_back = True
    try:
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                handlers[sig] = signal.signal(sig, signal.SIG_IGN)
        yield
    finally:
        # Keep the transaction handler nonthrowing through final reporting.
        for sig, handler in handlers.items():
            signal.signal(sig, handler)

def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise GateError("duplicate JSON field")
        value[key] = item
    return value


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run(args: list[str], *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=timeout)
    if check and cp.returncode != 0:
        raise GateError((cp.stderr or cp.stdout or "command failed").strip()[-4000:])
    return cp


def require_root() -> None:
    if os.geteuid() == 0 and (TEST_MODE or SOURCE_ROOT or FS_ROOT != Path("/") or BACKUP_ROOT != Path("/var/lib/dvizh/backups") or APPROVAL_ROOT != Path("/var/lib/dvizh/autopilot-approvals") or HTTP_BASE != "http://127.0.0.1:8000"):
        raise GateError("root execution cannot use fixture environment overrides")
    if not TEST_MODE and os.geteuid() != 0:
        raise GateError("dvizhrelease must run as root")


def fs_path(target: str) -> Path:
    if not target.startswith("/"):
        raise GateError(f"target must be absolute: {target}")
    if FS_ROOT == Path("/"):
        return Path(target)
    return FS_ROOT / target.lstrip("/")


def safe_json_file(path: str) -> tuple[Path, bytes, dict[str, Any]]:
    if not canonical_path(path, absolute=True):
        raise GateError("proposal path must be canonical and absolute")
    p = Path(path)
    checked_path(p)
    if not p.is_file() or p.is_symlink():
        raise GateError("proposal must be a regular non-symlink file")
    if p.stat().st_size > MAX_PROPOSAL:
        raise GateError("proposal file is too large")
    if not TEST_MODE:
        text = str(p)
        if not re.fullmatch(r"/home/[a-z_][a-z0-9_-]*/\.hermes/dev/dvizh/state/autopilot/release-[^/]+\.json", text):
            raise GateError("proposal is outside the Hermes autopilot state directory")
    raw = read_regular(p)[0]
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except Exception as exc:
        raise GateError("proposal is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise GateError("proposal must be a JSON object")
    return p, raw, value


def api_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"DVIZH-Release-Gate/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise GateError(f"GitHub API unavailable: {type(exc).__name__}") from exc


def fetch_bytes(commit: str, rel: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise GateError("invalid commit SHA")
    rel_path = Path(rel)
    if not canonical_path(rel, absolute=False):
        raise GateError(f"unsafe source path: {rel}")
    if SOURCE_ROOT:
        p = Path(SOURCE_ROOT) / rel
        checked_path(p)
        if not p.is_file() or p.is_symlink():
            raise GateError(f"fixture source missing: {rel}")
        data = read_regular(p)[0]
    else:
        quoted = "/".join(urllib.parse.quote(part) for part in rel_path.parts)
        url = f"https://raw.githubusercontent.com/{REPO}/{commit}/{quoted}"
        req = urllib.request.Request(url, headers={"User-Agent": f"DVIZH-Release-Gate/{VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read(MAX_FILE + 1)
        except Exception as exc:
            raise GateError(f"cannot fetch immutable source {rel}: {type(exc).__name__}") from exc
    if len(data) > MAX_FILE:
        raise GateError(f"source file too large: {rel}")
    return data


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def validate_branch(proposal: dict[str, Any]) -> None:
    if set(proposal) - {"schema", "id", "job_id", "mode", "repo", "branch", "commit", "manifest", "manifest_blob", "created_at_utc"}:
        raise GateError("proposal contains unsupported keys")
    if proposal.get("schema") != 1 or proposal.get("repo") != REPO:
        raise GateError("unsupported proposal schema/repository")
    approval_file(proposal.get("id"))
    branch = str(proposal.get("branch") or "")
    commit = str(proposal.get("commit") or "")
    if not branch.startswith("hermes/dev/") or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise GateError("proposal branch/commit is not a managed Hermes identity")
    if TEST_MODE:
        return
    payload = api_json(f"https://api.github.com/repos/{REPO}/branches/{urllib.parse.quote(branch, safe='')}")
    remote_sha = str((((payload or {}).get("commit") or {}).get("sha")) or "") if isinstance(payload, dict) else ""
    if remote_sha != commit:
        raise GateError("proposal commit is no longer the branch HEAD")


def load_manifest(proposal: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    commit = str(proposal.get("commit") or "")
    rel = str(proposal.get("manifest") or "")
    raw = fetch_bytes(commit, rel)
    if len(raw) > MAX_MANIFEST:
        raise GateError("release manifest is too large")
    expected = str(proposal.get("manifest_blob") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", expected) or git_blob(raw) != expected:
        raise GateError("release manifest blob mismatch")
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except Exception as exc:
        raise GateError("release manifest is invalid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise GateError("release manifest schema must equal 1")
    declared = str(manifest.get("commit") or "")
    if declared and declared != commit:
        raise GateError("release manifest commit does not match proposal")
    return manifest, raw


def target_risk(target: str) -> str:
    if not canonical_path(target, absolute=True):
        return "deny"
    if target in PRIVILEGED_TARGETS:
        return PRIVILEGED_CLASS
    if target in SAFE_TARGETS:
        return "safe"
    if target in APPROVAL_TARGETS or any(target.startswith(prefix) for prefix in APPROVAL_PREFIXES):
        return "approval"
    if any(target.startswith(prefix) for prefix in DENY_PREFIXES):
        return "deny"
    return "deny"


def validate_manifest(proposal: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    if set(manifest) - {"schema", "name", "commit", "operations", "restarts", "restart_reason"}:
        raise GateError("manifest contains unsupported keys")
    operations = manifest.get("operations")
    restarts = manifest.get("restarts", [])
    if not isinstance(operations, list) or not operations or len(operations) > 20:
        raise GateError("manifest operations must contain 1..20 entries")
    if not isinstance(restarts, list) or len(restarts) > 5:
        raise GateError("manifest restarts must be a short list")
    seen_targets: set[str] = set()
    normalized = []
    risk = "safe"
    for row in operations:
        if not isinstance(row, dict):
            raise GateError("operation contains unsupported keys")
        source = str(row.get("source") or "")
        target = str(row.get("target") or "")
        http_path = str(row.get("http_path") or "")
        if not canonical_path(source, absolute=False):
            raise GateError(f"unsafe source path: {source}")
        if not canonical_path(target, absolute=True):
            raise GateError(f"unsafe target: {target}")
        if target in seen_targets:
            raise GateError(f"duplicate target: {target}")
        seen_targets.add(target)
        row_risk = target_risk(target)
        if row_risk == "deny":
            raise GateError(f"target is outside the release allowlist: {target}")
        if row_risk == PRIVILEGED_CLASS:
            if (set(row) != PRIVILEGED_FIELDS
                    or (source, row.get("verification")) != PRIVILEGED_TARGETS[target]
                    or row.get("release_class") != PRIVILEGED_CLASS
                    or row.get("required_owner") != "root:root"
                    or row.get("required_mode") != "0755"
                    or not isinstance(row.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
                raise GateError("invalid privileged operation policy")
            risk = PRIVILEGED_CLASS
        elif set(row) - {"source", "target", "http_path"}:
            raise GateError("operation contains unsupported keys")
        elif row_risk == "approval" and risk != PRIVILEGED_CLASS:
            risk = "approval"
        expected_http = SAFE_TARGETS.get(target)
        if row_risk == "safe":
            if http_path != expected_http:
                raise GateError(f"safe static target requires http_path={expected_http}: {target}")
        elif http_path and not http_path.startswith("/"):
            raise GateError("http_path must start with /")
        normalized.append({**row, "source": source, "target": target, "http_path": http_path, "risk": row_risk})
    if risk == PRIVILEGED_CLASS and any(op["risk"] != PRIVILEGED_CLASS for op in normalized):
        raise GateError("privileged manifest contains extra files outside its exact class")
    if len(set(str(x) for x in restarts)) != len(restarts):
        raise GateError("duplicate restart")
    bridge_changed = BRIDGE_TARGET in seen_targets
    if bridge_changed:
        if BRIDGE_SERVICE not in restarts or not isinstance(manifest.get("restart_reason"), str) or not manifest["restart_reason"].strip():
            raise GateError("bridge update requires declared restart and justification")
    elif BRIDGE_SERVICE in restarts or "restart_reason" in manifest:
        raise GateError("bridge restart requires a bridge update")
    if risk == PRIVILEGED_CLASS and any(service != BRIDGE_SERVICE for service in restarts):
        raise GateError("privileged class permits only its approval bridge restart")
    for service in restarts:
        if not isinstance(service, str) or (service not in ALLOWED_RESTARTS and not (bridge_changed and service == BRIDGE_SERVICE)):
            raise GateError(f"service restart is outside allowlist: {service}")
        if risk != PRIVILEGED_CLASS:
            risk = "approval"
    mode = str(proposal.get("mode") or "safe")
    if mode not in {"safe", "auto"}:
        raise GateError("proposal mode is unsupported")
    approval_required = risk != "safe" or mode != "auto"
    return {"operations": normalized, "restarts": list(restarts), "risk": risk, "mode": mode, "approval_required": approval_required}


def proposal_digest(raw: bytes, manifest_raw: bytes) -> str:
    h = hashlib.sha256()
    h.update(raw); h.update(b"\0"); h.update(manifest_raw)
    return h.hexdigest()


def approval_file(proposal_id: str) -> Path:
    if not isinstance(proposal_id, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,160}", proposal_id):
        raise GateError("invalid proposal id")
    if proposal_id.lower() in {"pending", "pending.json", "transaction", "transaction.lock", ".", "..", "challenges"}:
        raise GateError("reserved proposal id")
    return APPROVAL_ROOT / "challenges" / f"{proposal_id}.json"


@serialized
def create_approval(proposal: dict[str, Any], digest: str) -> dict[str, Any]:
    p = approval_file(proposal.get("id"))
    parent = walk_parent(p, create=True, trusted=True)
    os.close(parent)
    token = secrets.token_hex(4).upper()
    value = {"proposal_id": proposal.get("id"), "digest": digest, "token_sha256": hashlib.sha256(token.encode()).hexdigest(), "created": time.time(), "created_at_utc": now_iso()}
    atomic_write(p, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
                 {"uid": os.geteuid(), "gid": os.getegid(), "mode": 0o600})
    return {"approval_token": token, "approval_phrase": f"APPROVE {proposal.get('id')} {token}", "expires_in_seconds": APPROVAL_TTL}


@serialized
def consume_approval(proposal: dict[str, Any], digest: str, token: str) -> None:
    p = approval_file(proposal.get("id"))
    if not p.is_file() or p.is_symlink():
        raise GateError("approval challenge not found; run release-plan again")
    try:
        value = json.loads(read_regular(p)[0], object_pairs_hook=unique_object)
    except Exception as exc:
        raise GateError("approval challenge is corrupted") from exc
    if str(value.get("proposal_id")) != str(proposal.get("id")) or str(value.get("digest")) != digest:
        raise GateError("approval challenge does not match this exact proposal")
    created = float(value.get("created") or 0)
    if not 0 <= time.time() - created <= APPROVAL_TTL:
        raise GateError("approval challenge expired")
    if not token or not secrets.compare_digest(str(value.get("token_sha256") or ""), hashlib.sha256(token.encode()).hexdigest()):
        raise GateError("approval token is invalid")
    # Validation and durable removal are an atomic claim under transaction flock.
    parent = open_parent(p)
    try:
        os.unlink(p.name, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def http_get(path: str) -> bytes:
    url = HTTP_BASE + path
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": f"DVIZH-Release-Gate/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status != 200:
                raise GateError(f"HTTP {path} returned {response.status}")
            return response.read(MAX_FILE + 1)
    except GateError:
        raise
    except Exception as exc:
        raise GateError(f"HTTP verification failed for {path}: {type(exc).__name__}") from exc


def service_active(name: str) -> bool:
    if TEST_MODE:
        return True
    return run(["systemctl", "is-active", "--quiet", name], check=False, timeout=15).returncode == 0


def restart_service(name: str) -> None:
    if TEST_MODE:
        return
    run(["systemctl", "restart", name], timeout=60)
    if not service_active(name):
        raise GateError(f"service did not become active: {name}")


def walk_parent(path: Path, *, create: bool = False, trusted: bool = False) -> int:
    if not path.is_absolute():
        raise GateError("filesystem path must be absolute")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    current = Path("/")
    try:
        if trusted:
            trusted_directory(fd, current)
        for part in path.parent.parts[1:]:
            current = current / part
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                # mkdir relative to the already opened no-follow parent.
                try: os.mkdir(part, 0o755, dir_fd=fd)
                except FileExistsError: pass
                os.fsync(fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            if trusted:
                trusted_directory(fd, current)
        return fd
    except BaseException:
        os.close(fd)
        raise


def canonical_parent(path: Path, fd: int) -> None:
    fresh = walk_parent(path, trusted=path in getattr(_STATE, "privileged_paths", set()))
    try:
        if identity(fresh) != identity(fd):
            raise GateError(f"canonical parent identity changed: {path}")
    finally:
        os.close(fresh)


def open_parent(path: Path) -> int:
    pinned = getattr(_STATE, "parents", {}).get(path)
    if pinned is not None:
        if not getattr(_STATE, "rolling_back", False):
            canonical_parent(path, pinned)
        return os.dup(pinned)
    return walk_parent(path)


def read_regular(path: Path) -> tuple[bytes, dict[str, int]]:
    parent = open_parent(path)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, "rb") as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE:
                raise GateError(f"unsafe or oversized file: {path}")
            data = f.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise GateError("oversized file")
            return data, {"uid": st.st_uid, "gid": st.st_gid, "mode": stat.S_IMODE(st.st_mode)}
    finally:
        os.close(parent)


def atomic_write(path: Path, data: bytes, metadata: dict[str, int] | None = None) -> None:
    if not getattr(_STATE, "rolling_back", False):
        checked_path(path, missing=True)
    if metadata is None:
        metadata = read_regular(path)[1] if path.exists() else {"uid": os.geteuid(), "gid": os.getegid(), "mode": 0o644}
    parent = open_parent(path)
    name = f".{path.name}.autopilot.{secrets.token_hex(12)}"
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fchown(f.fileno(), metadata["uid"], metadata["gid"])
            os.fchmod(f.fileno(), metadata["mode"])
            os.fsync(f.fileno())
        if not getattr(_STATE, "rolling_back", False):
            canonical_parent(path, parent)
        os.replace(name, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(name, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)
    verify_file(path, hashlib.sha256(data).hexdigest(), metadata)


def verify_file(path: Path, sha256: str, metadata: dict[str, int]) -> None:
    data, actual = read_regular(path)
    if hashlib.sha256(data).hexdigest() != sha256 or any(actual[k] != metadata[k] for k in ("uid", "gid", "mode")):
        raise GateError(f"file SHA/owner/group/mode verification failed: {path}")


def privileged_metadata() -> dict[str, int]:
    # Fixtures run unprivileged and cannot chown files to root.
    return {"uid": os.geteuid() if TEST_MODE else 0, "gid": os.getegid() if TEST_MODE else 0, "mode": 0o755}


def check_health(plan: dict[str, Any]) -> None:
    services = {"dvizh.service", "dvizh-auth.service", "dvizh-ai-home.service", *plan["restarts"]}
    for service in sorted(services):
        if not service_active(service):
            raise GateError(f"service is not active: {service}")
    if not TEST_MODE or plan["risk"] == PRIVILEGED_CLASS:
        try:
            http_get("/api/health")
        except GateError:
            if plan["risk"] != "safe":
                raise


@serialized
def apply_release(proposal: dict[str, Any], raw: bytes, manifest: dict[str, Any], manifest_raw: bytes, plan: dict[str, Any]) -> dict[str, Any]:
    commit = str(proposal.get("commit"))
    privileged = plan["risk"] == PRIVILEGED_CLASS
    tree = source_tree(commit) if privileged else None
    if privileged:
        verify_blob(tree, proposal["manifest"], manifest_raw)
        verify_ci(proposal)
    sources = []
    for op in plan["operations"]:
        data = fetch_bytes(commit, op["source"])
        if tree is not None:
            verify_blob(tree, op["source"], data)
        if op["risk"] == PRIVILEGED_CLASS:
            if hashlib.sha256(data).hexdigest() != op["sha256"]:
                raise GateError("privileged source SHA256 mismatch")
            try:
                compile(data, op["source"], "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as exc:
                raise GateError("Python syntax verification failed") from exc
        sources.append((op, data))
    check_health(plan)
    backup_parent = walk_parent(BACKUP_ROOT / "placeholder", create=True, trusted=True)
    try:
        os.fchmod(backup_parent, 0o700)
        backup_dir = Path(tempfile.mkdtemp(prefix="autopilot.", dir=str(BACKUP_ROOT)))
        os.fsync(backup_parent)
    finally:
        os.close(backup_parent)
    _STATE.privileged_paths = {fs_path(op["target"]) for op, _ in sources if op["risk"] == PRIVILEGED_CLASS}
    records = []
    # Phase one completes and verifies EVERY backup and its durable mapping.
    # Failure here must never enter rollback or touch any destination.
    for idx, (op, data) in enumerate(sources):
        target = fs_path(op["target"])
        checked_path(target, missing=not privileged)
        # Pin the correct directory object through success or restoration. Only
        # the existing AI Home prefix permits creation of missing ancestors.
        create = any(op["target"].startswith(prefix) for prefix in APPROVAL_PREFIXES)
        _STATE.parents[target] = walk_parent(target, create=create, trusted=privileged)
        canonical_parent(target, _STATE.parents[target])
        parent_device, parent_inode = identity(_STATE.parents[target])
        record = {"target": op["target"], "existed": target.exists(), "backup": None,
                  "parent_device": parent_device, "parent_inode": parent_inode}
        if record["existed"]:
            old, metadata = read_regular(target)
            if op["risk"] == PRIVILEGED_CLASS and metadata != privileged_metadata():
                raise GateError("privileged target metadata does not match root:root 0755 policy")
            bp = backup_dir / f"{idx:02d}-{target.name}"
            record.update(metadata, backup=str(bp), sha256=hashlib.sha256(old).hexdigest())
            atomic_write(bp, old, metadata)
            verify_file(bp, record["sha256"], metadata)
        else:
            record.update(uid=os.geteuid(), gid=os.getegid(), mode=0o644, sha256=None)
        records.append(record)
    mapping = json.dumps(records, indent=2, sort_keys=True).encode() + b"\n"
    mapping_metadata = {"uid": os.geteuid(), "gid": os.getegid(), "mode": 0o600}
    atomic_write(backup_dir / "mapping.json", mapping, mapping_metadata)
    for record in records:
        if record["existed"]:
            verify_file(Path(record["backup"]), record["sha256"], record)
            verify_file(fs_path(record["target"]), record["sha256"], record)
    verify_file(backup_dir / "mapping.json", hashlib.sha256(mapping).hexdigest(), mapping_metadata)
    journal = {"schema": 1, "backup": str(backup_dir), "mapping_sha256": hashlib.sha256(mapping).hexdigest(),
               "commit": commit, "restarts": plan["restarts"], "state": "pending"}
    atomic_write(APPROVAL_ROOT / "pending.json", json.dumps(journal, sort_keys=True).encode(), mapping_metadata)
    try:
        for (op, data), record in zip(sources, records):
            target = fs_path(op["target"])
            atomic_write(target, data, record)
            verify_file(target, hashlib.sha256(data).hexdigest(), record)
        for service in plan["restarts"]:
            restart_service(service)
        for op, data in sources:
            path = op.get("http_path") or ""
            if path and http_get(path) != data:
                raise GateError(f"HTTP byte verification failed: {path}")
        check_health(plan)
        for (op, data), record in zip(sources, records):
            verify_file(fs_path(op["target"]), hashlib.sha256(data).hexdigest(), record)
        journal_clear(journal)
        return {"ok": True, "status": "deployed", "risk": plan["risk"], "mode": plan["mode"], "commit": commit, "backup": str(backup_dir), "operations": [o for o, _ in sources], "restarts": plan["restarts"]}
    except BaseException as failure:
        with rollback_signals():
            # A signal/fsync failure at successful journal removal can arrive
            # before the return. Re-arm the marker before any restoration writes.
            journal_errors = [str(failure)] if isinstance(failure, JournalCleanupError) else []
            if not os.path.lexists(APPROVAL_ROOT / "pending.json"):
                try:
                    atomic_write(APPROVAL_ROOT / "pending.json", json.dumps(journal, sort_keys=True).encode(), mapping_metadata)
                except BaseException as exc:
                    journal_errors.append(f"cannot re-arm pending journal: {exc}")
            return rollback_release(sources, records, plan, backup_dir, failure, journal_errors, journal)


def rollback_release(sources, records, plan, backup_dir, failure, errors, journal):
    for record in reversed(records):
        try:
            target = fs_path(record["target"])
            if record["existed"]:
                bp = Path(record["backup"])
                verify_file(bp, record["sha256"], record)
                atomic_write(target, read_regular(bp)[0], record)
                verify_file(target, record["sha256"], record)
            else:
                parent = open_parent(target)
                try:
                    try: os.unlink(target.name, dir_fd=parent)
                    except FileNotFoundError: pass
                    os.fsync(parent)
                finally:
                    os.close(parent)
                if target.exists() or target.is_symlink():
                    raise GateError("rollback removal not confirmed")
        except BaseException as exc:
            errors.append(str(exc))
    # Include the service whose first restart failed: it may have loaded new bytes.
    for service in plan["restarts"]:
        try: restart_service(service)
        except BaseException as exc: errors.append(str(exc))
    try:
        check_health(plan)
        for (op, _), record in zip(sources, records):
            if op.get("http_path") and record["existed"]:
                if hashlib.sha256(http_get(op["http_path"])).hexdigest() != record["sha256"]:
                    raise GateError("rollback HTTP bytes mismatch")
    except BaseException as exc:
        errors.append(str(exc))
    for record in records:
        try:
            target = fs_path(record["target"])
            canonical_parent(target, _STATE.parents[target])
            if record["existed"]:
                verify_file(target, record["sha256"], record)
            else:
                parent = open_parent(target)
                try:
                    try: os.stat(target.name, dir_fd=parent, follow_symlinks=False)
                    except FileNotFoundError: pass
                    else: raise GateError("rollback removal not confirmed")
                finally:
                    os.close(parent)
        except BaseException as exc:
            errors.append(str(exc))
    if errors:
        raise GateError(f"CRITICAL: rollback unconfirmed; backup={backup_dir}; errors={errors}; original={failure}") from failure
    try:
        journal_clear(journal)
    except JournalCleanupError as exc:
        raise GateError(f"CRITICAL: rollback unconfirmed; backup={backup_dir}; errors={[str(exc)]}; original={failure}") from failure
    raise GateError(f"release failed; rollback confirmed; backup={backup_dir}; original={failure}") from failure


def checked_path(path: Path, *, missing: bool = False) -> None:
    """lstat every component before opening; never resolve away a symlink."""
    for item in [*reversed(path.parents), path]:
        try:
            st = item.lstat()
        except FileNotFoundError:
            if missing:
                continue
            raise GateError(f"missing path: {item}")
        if stat.S_ISLNK(st.st_mode):
            raise GateError(f"symlink forbidden: {item}")
        if item != path and not stat.S_ISDIR(st.st_mode):
            raise GateError(f"non-directory parent: {item}")
        if item == path and not stat.S_ISREG(st.st_mode):
            raise GateError(f"nonregular file: {item}")


def source_tree(commit: str) -> dict[str, dict[str, Any]]:
    payload = api_json(f"https://api.github.com/repos/{REPO}/git/trees/{commit}?recursive=1")
    if not isinstance(payload, dict) or payload.get("truncated") is not False or not isinstance(payload.get("tree"), list):
        raise GateError("immutable source tree unavailable or truncated")
    return {row["path"]: row for row in payload["tree"]}


def verify_blob(tree: dict[str, Any], source: str, data: bytes) -> None:
    row = tree.get(source, {})
    if row.get("type") != "blob" or row.get("mode") not in {"100644", "100755"} or row.get("sha") != git_blob(data):
        raise GateError(f"immutable regular git blob mismatch: {source}")
    for parent in Path(source).parents:
        row = tree.get(str(parent))
        if row and (row.get("type") != "tree" or row.get("mode") != "040000"):
            raise GateError("unsafe git source parent")


def verify_ci(proposal: dict[str, Any]) -> None:
    commit = proposal["commit"]
    payload = api_json(f"https://api.github.com/repos/{REPO}/actions/runs?head_sha={commit}&per_page=100")
    runs = payload.get("workflow_runs", []) if isinstance(payload, dict) else []
    if not runs or payload.get("total_count") != len(runs):
        raise GateError("CI missing or incomplete")
    required = ".github/workflows/dvizh-hermes-autopilot.yml"
    if not any(r.get("path") == required and r.get("event") == "push" for r in runs):
        raise GateError("required managed CI missing")
    if any(r.get("head_sha") != commit or r.get("head_branch") != proposal["branch"] or r.get("status") != "completed" or r.get("conclusion") != "success" for r in runs):
        raise GateError("CI must be fully green for the exact commit")


def verify_privileged_sources(proposal: dict[str, Any], manifest_raw: bytes, plan: dict[str, Any]) -> None:
    tree = source_tree(proposal["commit"])
    verify_blob(tree, proposal["manifest"], manifest_raw)
    for op in plan["operations"]:
        data = fetch_bytes(proposal["commit"], op["source"])
        verify_blob(tree, op["source"], data)
        if op["risk"] == PRIVILEGED_CLASS:
            if hashlib.sha256(data).hexdigest() != op["sha256"]:
                raise GateError("privileged source SHA256 mismatch")
            try:
                compile(data, op["source"], "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as exc:
                raise GateError("Python syntax verification failed") from exc
        checked_path(fs_path(op["target"]))
        parent = walk_parent(fs_path(op["target"]), trusted=True)
        os.close(parent)
        if op["risk"] == PRIVILEGED_CLASS and read_regular(fs_path(op["target"]))[1] != privileged_metadata():
            raise GateError("privileged target metadata does not match root:root 0755 policy")
    verify_ci(proposal)


def load_and_plan(proposal_path: str) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, dict[str, Any], str]:
    _, raw, proposal = safe_json_file(proposal_path)
    validate_branch(proposal)
    manifest, manifest_raw = load_manifest(proposal)
    plan = validate_manifest(proposal, manifest)
    if plan["risk"] == PRIVILEGED_CLASS:
        verify_privileged_sources(proposal, manifest_raw, plan)
    digest = proposal_digest(raw, manifest_raw)
    return proposal, raw, manifest, manifest_raw, plan, digest


def doctor() -> dict[str, Any]:
    require_root()
    tools = {name: bool(shutil.which(name)) for name in ("python3", "curl", "systemctl")}
    return {"ok": all(tools.values()), "version": VERSION, "repo": REPO, "tools": tools, "safe_targets": sorted(SAFE_TARGETS), "approval_targets": sorted(APPROVAL_TARGETS), "allowed_restarts": sorted(ALLOWED_RESTARTS)}


@serialized
def plan_release(path: str) -> dict[str, Any]:
    require_root()
    proposal, raw, manifest, manifest_raw, plan, digest = load_and_plan(path)
    result = {"ok": True, "status": "planned", "proposal_id": proposal.get("id"), "commit": proposal.get("commit"), "mode": plan["mode"], "risk": plan["risk"], "approval_required": plan["approval_required"], "operations": plan["operations"], "restarts": plan["restarts"], "digest": digest}
    if plan["approval_required"]:
        result.update(create_approval(proposal, digest))
    return result


@serialized
def apply(path: str, approval: str | None) -> dict[str, Any]:
    require_root()
    proposal, raw, manifest, manifest_raw, plan, digest = load_and_plan(path)
    if plan["risk"] == PRIVILEGED_CLASS:
        match = re.fullmatch(r"APPROVE " + re.escape(str(proposal.get("id"))) + r" ([0-9A-F]{8})", approval or "")
        if not match:
            raise GateError("exact later owner APPROVE phrase required")
        approval = match.group(1)
    if plan["approval_required"]:
        consume_approval(proposal, digest, approval or "")
    elif approval:
        raise GateError("approval token was supplied for an auto-safe release")
    result = apply_release(proposal, raw, manifest, manifest_raw, plan)
    result["proposal_id"] = proposal.get("id")
    result["digest"] = digest
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Root-owned allowlisted DVIZH release gate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    p_plan = sub.add_parser("plan"); p_plan.add_argument("proposal")
    p_apply = sub.add_parser("apply"); p_apply.add_argument("proposal"); p_apply.add_argument("--approval")
    args = parser.parse_args()
    try:
        if args.cmd == "doctor": result = doctor()
        elif args.cmd == "plan": result = plan_release(args.proposal)
        elif args.cmd == "apply": result = apply(args.proposal, args.approval)
        else: raise GateError("unsupported command")
        emit(result); return 0
    except (GateError, subprocess.TimeoutExpired) as exc:
        emit({"ok": False, "error": str(exc), "version": VERSION})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
