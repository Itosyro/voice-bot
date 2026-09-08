#!/usr/bin/env python3
from __future__ import annotations

import argparse
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

VERSION = "2026.09.08-dvizh-release-gate.1"
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


class GateError(RuntimeError):
    pass


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
    if not TEST_MODE and os.geteuid() != 0:
        raise GateError("dvizhrelease must run as root")


def fs_path(target: str) -> Path:
    if not target.startswith("/"):
        raise GateError(f"target must be absolute: {target}")
    if FS_ROOT == Path("/"):
        return Path(target)
    return FS_ROOT / target.lstrip("/")


def safe_json_file(path: str) -> tuple[Path, bytes, dict[str, Any]]:
    p = Path(path).expanduser().resolve()
    if not p.is_file() or p.is_symlink():
        raise GateError("proposal must be a regular non-symlink file")
    if p.stat().st_size > MAX_PROPOSAL:
        raise GateError("proposal file is too large")
    if not TEST_MODE:
        text = str(p)
        if not re.fullmatch(r"/home/[a-z_][a-z0-9_-]*/\.hermes/dev/dvizh/state/autopilot/release-[^/]+\.json", text):
            raise GateError("proposal is outside the Hermes autopilot state directory")
    raw = p.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
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
    if rel_path.is_absolute() or ".." in rel_path.parts or not rel or "\\" in rel:
        raise GateError(f"unsafe source path: {rel}")
    if SOURCE_ROOT:
        p = Path(SOURCE_ROOT) / rel
        if not p.is_file() or p.is_symlink():
            raise GateError(f"fixture source missing: {rel}")
        data = p.read_bytes()
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
    if proposal.get("schema") != 1 or proposal.get("repo") != REPO:
        raise GateError("unsupported proposal schema/repository")
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
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise GateError("release manifest is invalid JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise GateError("release manifest schema must equal 1")
    declared = str(manifest.get("commit") or "")
    if declared and declared != commit:
        raise GateError("release manifest commit does not match proposal")
    return manifest, raw


def target_risk(target: str) -> str:
    if target in SAFE_TARGETS:
        return "safe"
    if target in APPROVAL_TARGETS or any(target.startswith(prefix) for prefix in APPROVAL_PREFIXES):
        return "approval"
    if any(target.startswith(prefix) for prefix in DENY_PREFIXES):
        return "deny"
    return "deny"


def validate_manifest(proposal: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
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
        if not isinstance(row, dict) or set(row) - {"source", "target", "http_path"}:
            raise GateError("operation contains unsupported keys")
        source = str(row.get("source") or "")
        target = str(row.get("target") or "")
        http_path = str(row.get("http_path") or "")
        src = Path(source)
        if not source or src.is_absolute() or ".." in src.parts or "\\" in source:
            raise GateError(f"unsafe source path: {source}")
        if not target.startswith("/") or ".." in Path(target).parts:
            raise GateError(f"unsafe target: {target}")
        if target in seen_targets:
            raise GateError(f"duplicate target: {target}")
        seen_targets.add(target)
        row_risk = target_risk(target)
        if row_risk == "deny":
            raise GateError(f"target is outside the release allowlist: {target}")
        if row_risk == "approval":
            risk = "approval"
        expected_http = SAFE_TARGETS.get(target)
        if row_risk == "safe":
            if http_path != expected_http:
                raise GateError(f"safe static target requires http_path={expected_http}: {target}")
        elif http_path and not http_path.startswith("/"):
            raise GateError("http_path must start with /")
        normalized.append({"source": source, "target": target, "http_path": http_path, "risk": row_risk})
    for service in restarts:
        if not isinstance(service, str) or service not in ALLOWED_RESTARTS:
            raise GateError(f"service restart is outside allowlist: {service}")
        risk = "approval"
    mode = str(proposal.get("mode") or "safe")
    if mode not in {"safe", "auto"}:
        raise GateError("proposal mode is unsupported")
    approval_required = risk == "approval" or mode != "auto"
    return {"operations": normalized, "restarts": list(restarts), "risk": risk, "mode": mode, "approval_required": approval_required}


def proposal_digest(raw: bytes, manifest_raw: bytes) -> str:
    h = hashlib.sha256()
    h.update(raw); h.update(b"\0"); h.update(manifest_raw)
    return h.hexdigest()


def approval_file(proposal_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", proposal_id)[:160]
    return APPROVAL_ROOT / f"{safe}.json"


def create_approval(proposal: dict[str, Any], digest: str) -> dict[str, Any]:
    APPROVAL_ROOT.mkdir(parents=True, exist_ok=True)
    try: APPROVAL_ROOT.chmod(0o700)
    except OSError: pass
    token = secrets.token_hex(4).upper()
    p = approval_file(str(proposal.get("id") or "proposal"))
    value = {"proposal_id": proposal.get("id"), "digest": digest, "token_sha256": hashlib.sha256(token.encode()).hexdigest(), "created": time.time(), "created_at_utc": now_iso()}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)
    return {"approval_token": token, "approval_phrase": f"APPROVE {proposal.get('id')} {token}", "expires_in_seconds": APPROVAL_TTL}


def consume_approval(proposal: dict[str, Any], digest: str, token: str) -> None:
    p = approval_file(str(proposal.get("id") or ""))
    if not p.is_file() or p.is_symlink():
        raise GateError("approval challenge not found; run release-plan again")
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GateError("approval challenge is corrupted") from exc
    if str(value.get("proposal_id")) != str(proposal.get("id")) or str(value.get("digest")) != digest:
        raise GateError("approval challenge does not match this exact proposal")
    created = float(value.get("created") or 0)
    if time.time() - created > APPROVAL_TTL:
        raise GateError("approval challenge expired")
    if not token or not secrets.compare_digest(str(value.get("token_sha256") or ""), hashlib.sha256(token.encode()).hexdigest()):
        raise GateError("approval token is invalid")
    p.unlink(missing_ok=True)


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


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o644
    uid = gid = None
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise GateError(f"unsafe target type: {path}")
        st = path.stat(); mode = st.st_mode & 0o777; uid = st.st_uid; gid = st.st_gid
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.autopilot.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chmod(tmp_name, mode)
        if uid is not None and gid is not None and os.geteuid() == 0:
            os.chown(tmp_name, uid, gid)
        os.replace(tmp_name, path)
    finally:
        try: os.unlink(tmp_name)
        except FileNotFoundError: pass


def apply_release(proposal: dict[str, Any], raw: bytes, manifest: dict[str, Any], manifest_raw: bytes, plan: dict[str, Any]) -> dict[str, Any]:
    commit = str(proposal.get("commit"))
    sources: list[tuple[dict[str, Any], bytes]] = []
    for op in plan["operations"]:
        data = fetch_bytes(commit, op["source"])
        sources.append((op, data))
    if not TEST_MODE:
        for service in ("dvizh.service", "dvizh-auth.service", "dvizh-ai-home.service"):
            if not service_active(service):
                raise GateError(f"preflight service is not active: {service}")
        try:
            http_get("/api/health")
        except GateError:
            # Some historical backend builds expose health differently; static
            # byte checks below remain authoritative for frontend-only releases.
            if plan["risk"] != "safe":
                raise
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    try: BACKUP_ROOT.chmod(0o700)
    except OSError: pass
    backup_dir = Path(tempfile.mkdtemp(prefix=f"autopilot.{proposal.get('job_id','job')}.", dir=str(BACKUP_ROOT)))
    try: backup_dir.chmod(0o700)
    except OSError: pass
    records = []
    restarted: list[str] = []
    try:
        for idx, (op, data) in enumerate(sources):
            target = fs_path(op["target"])
            record = {"target": op["target"], "existed": target.is_file() and not target.is_symlink(), "backup": None}
            if target.exists() and (target.is_symlink() or not target.is_file()):
                raise GateError(f"unsafe existing target: {op['target']}")
            if record["existed"]:
                bp = backup_dir / f"{idx:02d}-{target.name}"
                shutil.copy2(target, bp)
                record["backup"] = str(bp)
            records.append(record)
            atomic_write(target, data)
            if target.read_bytes() != data:
                raise GateError(f"post-write bytes mismatch: {op['target']}")
        for service in plan["restarts"]:
            restart_service(service); restarted.append(service)
        for op, data in sources:
            path = op.get("http_path") or ""
            if path:
                sep = "&" if "?" in path else "?"
                live = http_get(f"{path}{sep}_dvizh_autopilot={int(time.time()*1000)}")
                if live != data:
                    raise GateError(f"HTTP byte verification failed: {path}")
        return {"ok": True, "status": "deployed", "risk": plan["risk"], "mode": plan["mode"], "commit": commit, "backup": str(backup_dir), "operations": [o for o, _ in sources], "restarts": restarted}
    except Exception:
        for record in reversed(records):
            target = fs_path(str(record["target"]))
            if record["existed"] and record["backup"]:
                atomic_write(target, Path(str(record["backup"])).read_bytes())
            elif target.exists() and not target.is_symlink():
                target.unlink(missing_ok=True)
        for service in restarted:
            try: restart_service(service)
            except Exception: pass
        raise


def load_and_plan(proposal_path: str) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, dict[str, Any], str]:
    _, raw, proposal = safe_json_file(proposal_path)
    validate_branch(proposal)
    manifest, manifest_raw = load_manifest(proposal)
    plan = validate_manifest(proposal, manifest)
    digest = proposal_digest(raw, manifest_raw)
    return proposal, raw, manifest, manifest_raw, plan, digest


def doctor() -> dict[str, Any]:
    require_root()
    tools = {name: bool(shutil.which(name)) for name in ("python3", "curl", "systemctl")}
    return {"ok": all(tools.values()), "version": VERSION, "repo": REPO, "tools": tools, "safe_targets": sorted(SAFE_TARGETS), "approval_targets": sorted(APPROVAL_TARGETS), "allowed_restarts": sorted(ALLOWED_RESTARTS)}


def plan_release(path: str) -> dict[str, Any]:
    require_root()
    proposal, raw, manifest, manifest_raw, plan, digest = load_and_plan(path)
    result = {"ok": True, "status": "planned", "proposal_id": proposal.get("id"), "commit": proposal.get("commit"), "mode": plan["mode"], "risk": plan["risk"], "approval_required": plan["approval_required"], "operations": plan["operations"], "restarts": plan["restarts"], "digest": digest}
    if plan["approval_required"]:
        result.update(create_approval(proposal, digest))
    return result


def apply(path: str, approval: str | None) -> dict[str, Any]:
    require_root()
    proposal, raw, manifest, manifest_raw, plan, digest = load_and_plan(path)
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
