#!/usr/bin/env python3
"""Bounded, read-only migration discovery. NOT a backup, transfer or installer.

Only prints OS/resource metadata, path metadata, unit names, Docker mount paths
and hashes of fixed DVIZH source files. Never dumps environments, private keys,
process command lines, database rows, or agent conversations. Only network call:
a bounded GET to the fixed local DVIZH /api/health. No service changes.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request

VERSION = "2026-09-15.migration-inventory.1"
SAFE_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C", "SYSTEMD_PAGER": "cat"}
DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")
SKIP_SCAN = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", "site-packages", "dist-packages"}
MAX_ENTRIES = 60000
MAX_SECONDS = 20
EXPECTED_FRONTEND = {
    "sync.js": "58991ea1a0d95facbe21402792e7607d6c4ff55603234b808f646cd8b5f5c12e",
    "app.js": "41cd3d0683eabdf649c47878ad214408af1acb9c93352fe1c12302adc248b84e",
    "ai-home-v2.js": "b8538939f48be484d21eaa56c991fc237b20188f917eed3c65ae07cb25baaf76",
    "index.html": "41bc4d1509c5818675d488164f01e35bf8dcdb35c15d660c38fde72f7a77ee02",
    "manual.html": "9a0847bc1e9b0bcd2c775974c94994d8c49979fb5316ce6372e408c283fee514",
}


def clean(value: object) -> str:
    """Make diagnostic identifiers safe to render in terminals, never shell-eval."""
    s = str(value)
    s = re.sub(r"[\x00-\x1f\x7f-\x9f]", "?", s)
    s = re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})", "[REDACTED]", s)
    return s[:400]


def run(args: list[str], timeout: int = 8) -> tuple[int, str]:
    try:
        p = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, text=True, errors="replace",
                           env=SAFE_ENV, timeout=timeout, check=False)
        if len(p.stdout) > 2_000_000:
            return 99, ""
        return p.returncode, p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return 99, ""


def metadata(path: Path) -> dict:
    try:
        st = path.lstat()
        result = {"path": clean(path), "uid": st.st_uid, "gid": st.st_gid,
                  "mode": format(stat.S_IMODE(st.st_mode), "04o"), "bytes": st.st_size}
        result["kind"] = "symlink" if stat.S_ISLNK(st.st_mode) else "directory" if stat.S_ISDIR(st.st_mode) else "file" if stat.S_ISREG(st.st_mode) else "special"
        if stat.S_ISLNK(st.st_mode):
            result["link_target"] = clean(os.readlink(path))
        return result
    except FileNotFoundError:
        return {"path": clean(path), "kind": "absent"}
    except OSError as exc:
        return {"path": clean(path), "kind": "unreadable", "error": type(exc).__name__}


def read_fixed(path: Path, limit: int = 2_000_000) -> bytes:
    """Reject symlinks in ALL components; only bounded single-link files."""
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("absolute fixed path required")
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for item in path.parts[1:-1]:
            nxt = os.open(item, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = nxt
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise ValueError("not a bounded single-link regular file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(limit + 1)
            after = os.fstat(fd)
            if len(data) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("file changed or oversized")
            return data
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def fingerprint(path: Path) -> dict:
    try:
        data = read_fixed(path)
        return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    except (OSError, ValueError) as exc:
        return {"error": type(exc).__name__}


def os_info() -> dict:
    try:
        # /etc/os-release is often a symlink; use its fixed vendor source instead.
        p = Path("/usr/lib/os-release") if Path("/usr/lib/os-release").exists() else Path("/etc/os-release")
        text = read_fixed(p, 16384).decode("utf-8", "replace")
        values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#"))
        values = {k: clean(values[k].strip('"\'')) for k in ("ID", "VERSION_ID", "PRETTY_NAME") if k in values}
    except (OSError, ValueError):
        values = {"error": "os-release unreadable"}
    values.update(architecture=platform.machine(), python=platform.python_version(), cpus=os.cpu_count())
    try:
        mem = Path("/proc/meminfo").read_text()
        values["ram_bytes"] = int(re.search(r"^MemTotal:\s+(\d+)", mem, re.M)[1]) * 1024
    except (OSError, TypeError, ValueError):
        pass
    return values


def scan(roots: list[Path], max_entries: int = MAX_ENTRIES, max_seconds: int = MAX_SECONDS) -> dict:
    """Metadata only. Explicitly scoped and bounded, never presented as full backup."""
    start = time.monotonic()
    pending = list(reversed(roots))
    db, links, project_roots, errors = [], [], [], []
    count = 0
    while pending:
        if count >= max_entries or time.monotonic() - start >= max_seconds:
            errors.append("scan_limit_reached")
            break
        directory = pending.pop()
        meta = metadata(directory)
        if meta["kind"] == "symlink":
            links.append(meta)
            continue
        if meta["kind"] != "directory":
            if meta["kind"] == "unreadable": errors.append("unreadable_directory")
            continue
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    count += 1
                    if count > max_entries or time.monotonic() - start >= max_seconds:
                        errors.append("scan_limit_reached")
                        break
                    p = Path(entry.path)
                    if entry.is_symlink():
                        if entry.name not in SKIP_SCAN:
                            if len(links) < 60: links.append(metadata(p))
                            else: errors.append("symlink_list_limit")
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name == ".git": project_roots.append(clean(directory))
                        if entry.name not in SKIP_SCAN: pending.append(p)
                    elif entry.is_file(follow_symlinks=False) and entry.name.endswith(DB_SUFFIXES):
                        if len(db) < 200: db.append(metadata(p))
                        else: errors.append("database_list_limit")
        except OSError:
            errors.append("unreadable_directory")
    return {"roots": [clean(p) for p in roots], "database_candidates": db,
            "project_roots": sorted(set(project_roots)), "symlinks_not_followed": links,
            "entries_inspected": count, "omitted_directory_names": sorted(SKIP_SCAN),
            "limited_or_unreadable": sorted(set(errors)), "is_complete_server_inventory": False}


def units() -> dict:
    records, errors = [], []
    rc, out = run(["/usr/bin/systemctl", "list-units", "--all", "--no-legend", "--no-pager", "--plain", "--type=service,timer,socket"])
    if rc: return {"units": [], "error": "systemctl unavailable"}
    names = []
    for line in out.splitlines():
        fields = line.split()
        if fields and re.fullmatch(r"[A-Za-z0-9_.@:\\-]+\.(service|timer|socket)", fields[0]): names.append(fields[0])
    if len(names) > 700: errors.append("unit_list_limit")
    props = "Id,ActiveState,SubState,FragmentPath,User,Group,WorkingDirectory,StateDirectory,EnvironmentFiles,UnitFileState"
    # Read only these properties, NOT Environment or ExecStart/command lines.
    rc, text = run(["/usr/bin/systemctl", "show", "--no-pager", "--property=" + props, *names[:700]]) if names else (0, "")
    if rc: errors.append("unit_properties_unavailable")
    for block in text.strip().split("\n\n"):
        item = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        name = item.get("Id", "")
        custom = item.get("FragmentPath", "").startswith(("/etc/systemd/", "/usr/local/", "/opt/", "/home/"))
        if custom or re.search(r"dvizh|hermes|docker|containerd|nginx|caddy|postgres|mysql|redis|cron|podman", name, re.I):
            records.append({k: clean(v) for k, v in item.items()})
    return {"units": records, "errors": errors, "user_managers_not_queried": True}


def docker_metadata() -> dict:
    binary = shutil.which("docker", path=SAFE_ENV["PATH"])
    if not binary: return {"status": "command_absent"}
    cmd = [binary, "--host", "unix:///var/run/docker.sock"]
    rc, out = run(cmd + ["ps", "-aq", "--no-trunc"])
    if rc: return {"status": "local_engine_unavailable"}
    ids = [x for x in out.split() if re.fullmatch(r"[0-9a-f]{12,64}", x)]
    rows, errors = [], []
    fmt = '{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Config.Image}},"running":{{json .State.Running}},"mounts":{{json .Mounts}}}'
    for cid in ids[:50]:
        rc, raw = run(cmd + ["inspect", "--type=container", "--format", fmt, cid], 5)
        try:
            x = json.loads(raw) if rc == 0 else None
            if not isinstance(x, dict): raise ValueError()
            # Never include Config.Env, volume Options, process args or labels.
            mounts = [{k: clean(m[k]) for k in ("Type", "Name", "Source", "Destination", "Driver") if k in m} for m in x.get("mounts", []) if isinstance(m, dict)]
            rows.append({"name": clean(x.get("name", "")), "image": clean(x.get("image", "")), "running": x.get("running") is True, "mounts": mounts})
        except (ValueError, TypeError): errors.append("container_metadata_unavailable")
    rc, root = run(cmd + ["info", "--format", "{{.DockerRootDir}}"], 5)
    if len(ids) > 50: errors.append("container_list_limit")
    return {"status": "ok", "containers": rows, "root": clean(root.strip()) if not rc else None, "errors": errors,
            "unattached_volumes_not_enumerated": True, "rootless_engines_not_queried": True}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def health() -> dict:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(urllib.request.Request("http://127.0.0.1:8000/api/health", headers={"Accept": "application/json", "Cache-Control": "no-cache"}), timeout=4) as response:
            b = response.read(16385)
            if response.status != 200 or len(b) > 16384 or response.headers.get_content_type() != "application/json": raise ValueError()
        d = json.loads(b)
        return {"ok": isinstance(d, dict) and d.get("ok") is True and d.get("app") == "dvizh"}
    except Exception:
        return {"ok": False, "error": "local_health_not_confirmed"}


def collect() -> dict:
    roots = [Path("/home"), Path("/opt"), Path("/srv"), Path("/root")]
    for parent in (Path("/var/lib"), Path("/etc")):
        try:
            roots += [p for p in parent.iterdir() if p.name.startswith(("dvizh", "hermes"))]
        except OSError: pass
    s = scan(roots)
    known = ["/opt", "/home", "/srv", "/root", "/usr/local", "/var/lib/docker", "/var/lib/containerd", "/var/lib/postgresql", "/var/lib/mysql", "/var/lib/redis", "/etc/dvizh", "/etc/systemd/system", "/var/spool/cron", "/etc/cron.d", "/home/exedev/.hermes", "/home/exedev/.config/systemd/user", "/home/exedev/.config/gh", "/home/exedev/.claude", "/home/exedev/.codex", "/etc/nginx", "/etc/caddy"]
    control = {p: fingerprint(Path(p)) for p in ("/opt/dvizh/server.py", "/usr/local/bin/dvizhautopilot", "/usr/local/sbin/dvizhgitpush", "/usr/local/sbin/dvizhrelease")}
    frontend = {n: fingerprint(Path("/opt/dvizh/static") / n) for n in EXPECTED_FRONTEND}
    for n, f in frontend.items(): f["matches_last_reported_release"] = f.get("sha256") == EXPECTED_FRONTEND[n]
    disk = shutil.disk_usage("/")
    rc, mount_json = run(["/usr/bin/findmnt", "--json", "--list", "--output", "TARGET,FSTYPE", "--real"])
    try: mounts = json.loads(mount_json).get("filesystems", []) if not rc else []
    except ValueError: mounts = []
    return {"version": VERSION, "type": "READ_ONLY_MIGRATION_INVENTORY_NOT_BACKUP", "utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "root_privileges": os.geteuid() == 0, "os": os_info(),
            "accounts": [{"name": clean(x.pw_name), "uid": x.pw_uid, "gid": x.pw_gid, "home": clean(x.pw_dir), "shell": clean(x.pw_shell)} for x in pwd.getpwall() if x.pw_uid == 0 or 1000 <= x.pw_uid < 65534 or x.pw_name.startswith(("dvizh", "hermes"))], "disk_root": {"total": disk.total, "used": disk.used, "free": disk.free},
            "mounts": [{"target": clean(x.get("target", "")), "fstype": clean(x.get("fstype", ""))} for x in mounts],
            "paths": [metadata(Path(p)) for p in known], "scan": s, "system_units": units(), "docker": docker_metadata(),
            "frontend": frontend, "control_hashes": control, "health": health(),
            "migration_completed": False, "backup_created": False,
            "remaining_discovery": ["target_provider_os_arch_disk_and_domain", "user_services_and_cron_writers", "external_mounts_and_unattached_volumes", "all_application_writers_for_consistent_backup", "provider_side_integrations_and_auth", "browser_unsynced_state_on_old_origin"]}


def summary(d: dict) -> str:
    o = d["os"]; g = lambda n: round(n / 1024**3, 1)
    lines = ["DVIZH MIGRATION INVENTORY (NO TRANSFER / NO BACKUP)",
             f"OS: {o.get('PRETTY_NAME', 'unknown')}; arch={o.get('architecture')}; Python={o.get('python')}",
             f"CPU: {o.get('cpus')}; RAM GiB: {g(o.get('ram_bytes',0))}; root access: {d['root_privileges']}",
             f"Root disk GiB: used={g(d['disk_root']['used'])}; free={g(d['disk_root']['free'])}",
             f"App health JSON: {d['health']['ok']}; installed frontend matches last release: {all(x['matches_last_reported_release'] for x in d['frontend'].values())}"]
    service_rows = d["system_units"].get("units", [])
    lines.append("System services: " + ", ".join(x.get("Id", "?") + "=" + x.get("ActiveState", "?") for x in service_rows))
    lines.append("Accounts: " + ", ".join(x["name"] + "=" + str(x["uid"]) + ":" + str(x["gid"]) for x in d.get("accounts", [])))
    lines.append("Present roots: " + ", ".join(x["path"] for x in d["paths"] if x["kind"] not in ("absent", "unreadable")))
    lines.append("Database candidate paths (CONTENTS NOT READ):")
    lines += ["  " + x["path"] for x in d["scan"]["database_candidates"][:30]]
    if len(d["scan"]["database_candidates"]) > 30: lines.append("  ... more paths in --json report")
    lines.append("Docker: " + d["docker"]["status"])
    for c in d["docker"].get("containers", []):
        lines.append("  " + c["name"] + " running=" + str(c["running"]) + " image=" + c["image"])
        lines += ["    mount=" + m.get("Source", "?") + " -> " + m.get("Destination", "?") for m in c["mounts"]]
    lines.append("Extra mounts: " + ", ".join(m["target"] + " (" + m["fstype"] + ")" for m in d["mounts"] if m["target"] != "/"))
    problems = d["scan"]["limited_or_unreadable"] + d["system_units"].get("errors", []) + d["docker"].get("errors", [])
    if d["system_units"].get("error"): problems.append(d["system_units"]["error"])
    lines.append("Discovery limits/errors: " + (", ".join(problems) or "none in queried subset"))
    lines.append("Scope is partial: user services, cron writers, detached volumes and provider integrations still require verification.")
    lines.append("No environment values, private keys, database rows or chat contents printed. Nothing stopped or installed.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print full metadata report; still no secret file contents")
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Run via sudo /usr/bin/python3 -I -S inventory.py; root metadata access is required. No changes will be made.", file=sys.stderr)
        return 2
    report = collect()
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else summary(report))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
