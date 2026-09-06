#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2026.09.06-hermes-handoff.1"
HOME = Path.home()
ROOT = Path(os.environ.get("DVIZH_DEV_ROOT", str(HOME / ".hermes" / "dev" / "dvizh"))).expanduser().resolve()
WORKTREES = ROOT / "worktrees"
STATE_DIR = ROOT / "state"
JOBS_PATH = STATE_DIR / "jobs.json"
HANDOFF_DIR = STATE_DIR / "handoffs"
MAX_INLINE_PATCH = 12000
MAX_PATCH_BYTES = 2_000_000

FORBIDDEN_PATH_PATTERNS = (
    re.compile(r"(^|/)(\.env(?:\.|$)|auth\.json$|credentials?(?:\.|$)|secrets?(?:\.|$))", re.I),
    re.compile(r"\.(?:pem|key|p12|pfx)$", re.I),
    re.compile(r"(^|/)\.git(?:/|$)"),
)


class HandoffError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(args: list[str], cwd: Path, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    cp = subprocess.run(
        args,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if check and cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or b"command failed").decode("utf-8", errors="replace")[-3000:]
        raise HandoffError(detail)
    return cp


def load_job(job_id: str) -> dict[str, Any]:
    try:
        rows = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HandoffError("Hermes Dev jobs state is unavailable") from exc
    if not isinstance(rows, list):
        raise HandoffError("Hermes Dev jobs state is invalid")
    for row in reversed(rows):
        if isinstance(row, dict) and str(row.get("id") or "") == job_id:
            return row
    raise HandoffError(f"job not found: {job_id}")


def safe_worktree(job: dict[str, Any]) -> Path:
    raw = str(job.get("worktree") or "")
    if not raw:
        raise HandoffError("job has no worktree")
    wt = Path(raw).resolve()
    try:
        wt.relative_to(WORKTREES)
    except ValueError as exc:
        raise HandoffError("worktree escaped managed root") from exc
    if not (wt / ".git").exists():
        raise HandoffError("managed worktree is missing")
    branch = run(["git", "branch", "--show-current"], wt).stdout.decode().strip()
    expected = str(job.get("branch") or "")
    if branch != expected or not branch.startswith("hermes/dev/"):
        raise HandoffError("managed branch identity mismatch")
    return wt


def parse_changed_paths(raw: bytes) -> list[str]:
    text = raw.decode("utf-8", errors="replace")
    paths: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        for rel in parts[1:]:
            rel = rel.strip()
            if rel:
                paths.append(rel)
    return sorted(set(paths))


def validate_paths(paths: list[str]) -> None:
    if not paths:
        raise HandoffError("no committed changes between base and HEAD")
    for rel in paths:
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise HandoffError(f"unsafe path in committed diff: {rel}")
        if any(rx.search(rel) for rx in FORBIDDEN_PATH_PATTERNS):
            raise HandoffError(f"secret/credential-shaped path in committed diff: {rel}")


def export_handoff(job_id: str) -> dict[str, Any]:
    job = load_job(job_id)
    wt = safe_worktree(job)
    dirty = run(["git", "status", "--porcelain=v1"], wt).stdout.decode().strip()
    if dirty:
        raise HandoffError("worktree is dirty; commit all intended changes before handoff")

    base = str(job.get("base_sha") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", base):
        raise HandoffError("job base SHA is invalid")
    head = run(["git", "rev-parse", "HEAD"], wt).stdout.decode().strip()
    if head == base:
        raise HandoffError("HEAD has no commit ahead of base")

    names = run(["git", "diff", "--name-status", base, head, "--", "."], wt).stdout
    paths = parse_changed_paths(names)
    validate_paths(paths)

    commits = run(["git", "log", "--format=%H%x09%s", f"{base}..{head}"], wt).stdout.decode("utf-8", errors="replace").splitlines()
    patch = run(["git", "diff", "--binary", "--full-index", "--no-ext-diff", base, head, "--", "."], wt, timeout=180).stdout
    if not patch:
        raise HandoffError("git diff produced an empty patch")
    if len(patch) > MAX_PATCH_BYTES:
        raise HandoffError(f"handoff patch is too large ({len(patch)} bytes > {MAX_PATCH_BYTES})")

    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(HANDOFF_DIR, 0o700)
    prefix = f"{job_id}-{head[:12]}"
    patch_path = HANDOFF_DIR / f"{prefix}.patch"
    manifest_path = HANDOFF_DIR / f"{prefix}.json"
    patch_path.write_bytes(patch)
    os.chmod(patch_path, 0o600)
    digest = hashlib.sha256(patch).hexdigest()
    manifest = {
        "version": VERSION,
        "created_at_utc": now_iso(),
        "job_id": job_id,
        "problem": str(job.get("problem") or "")[:2000],
        "branch": str(job.get("branch") or ""),
        "base_branch": str(job.get("base_branch") or ""),
        "base_sha": base,
        "head_sha": head,
        "commits": commits,
        "paths": paths,
        "patch_sha256": digest,
        "patch_bytes": len(patch),
        "patch_path": str(patch_path),
        "production_status": "unchanged",
        "github_push_required_from_hermes": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)

    result = dict(manifest)
    result["manifest_path"] = str(manifest_path)
    if len(patch) <= MAX_INLINE_PATCH:
        result["patch_inline"] = patch.decode("utf-8", errors="replace")
        result["telegram_hint"] = "Patch is small enough to paste verbatim to the user for ChatGPT handoff."
    else:
        result["patch_inline"] = None
        result["telegram_hint"] = "Send/attach the generated .patch file in Telegram if supported; do not paste secrets or credentials."
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a safe local Hermes Dev commit for ChatGPT/GitHub handoff")
    parser.add_argument("job_id")
    args = parser.parse_args()
    try:
        print(json.dumps(export_handoff(args.job_id), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (HandoffError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
