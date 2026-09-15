#!/usr/bin/env python3
"""Read-only, secret-minimizing inventory for the DVIZH server migration.

No installs, service changes, database opens, environment-file reads, outbound
network calls, Git writes or backups. Only the optional report file is created.
Run in an owner session, with: sudo /usr/bin/python3 -I -S inventory.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.client
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
from typing import Any

VERSION = "2026-09-15.inventory.1"
SOURCE_RELEASE = "f6b8959c7d05eea434fbe25937b6428b70ed1716"
SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
MAX_FILE = 2 * 1024 * 1024
KNOWN = {
    "sync.js": "58991ea1a0d95facbe21402792e7607d6c4ff55603234b808f646cd8b5f5c12e",
    "app.js": "41cd3d0683eabdf649c47878ad214408af1acb9c93352fe1c12302adc248b84e",
    "ai-home-v2.js": "b8538939f48be484d21eaa56c991fc237b20188f917eed3c65ae07cb25baaf76",
    "index.html": "41bc4d1509c5818675d488164f01e35bf8dcdb35c15d660c38fde72f7a77ee02",
    "manual.html": "9a0847bc1e9b0bcd2c775974c94994d8c49979fb5316ce6372e408c283fee514",
}
SERVICE_PREFIXES = ("dvizh", "hermes", "postgresql", "mysql", "mariadb", "redis")
SERVICE_NAMES = {"nginx.service", "caddy.service", "apache2.service", "docker.service", "containerd.service", "cron.service"}
PROPERTIES = ("LoadState", "ActiveState", "UnitFileState", "User", "Group",
              "FragmentPath", "DropInPaths", "WorkingDirectory", "EnvironmentFiles",
              "StateDirectory", "LogsDirectory", "RuntimeDirectory")
RUNTIMES = ("python3", "python3-venv", "nodejs", "npm", "git", "gh", "rsync",
            "openssh-server", "sqlite3", "nginx", "caddy", "docker.io", "docker-ce",
            "postgresql", "mariadb-server", "redis-server", "age", "gnupg")
PSEUDO_FS = {"proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2",
             "mqueue", "securityfs", "debugfs", "tracefs", "configfs", "fusectl",
             "pstore", "hugetlbfs", "autofs", "binfmt_misc", "nsfs"}


def clean(value: Any, limit: int = 800) -> str:
    """Defense in depth; only technical metadata is passed to this function."""
    s = str(value)
    s = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", s)
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)
    s = re.sub(r"(?i)https?://[^/@\s]+:[^/@\s]+@", "https://[redacted]@", s)
    s = re.sub(r"(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-(?:proj-)?[A-Za-z0-9_-]{12,})", "[redacted]", s)
    s = re.sub(r"(?i)(?:bearer\s+|(?:password|passwd|token|secret|api[_-]?key)[=:]\s*)[^\s,;]+", "[redacted]", s)
    return s[:limit]


def kv(text: str, allowed: tuple[str, ...]) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        name, sep, value = line.partition("=")
        if sep and name in allowed:
            out[name] = clean(value.strip().strip('"'))
    return out


def command(args: list[str], timeout: int = 8) -> dict[str, Any]:
    """Never executes a shell or reports stderr/command arguments."""
    binary = shutil.which(args[0], path=SAFE_PATH)
    if not binary:
        return {"status": "missing_command", "output": ""}
    try:
        p = subprocess.run([binary, *args[1:]], stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout, check=False,
                           env={"PATH": SAFE_PATH, "LANG": "C", "LC_ALL": "C", "SYSTEMD_COLORS": "0"})
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "output": ""}
    except OSError:
        return {"status": "unavailable", "output": ""}
    if len(p.stdout) > MAX_FILE:
        return {"status": "too_large", "output": ""}
    return {"status": "ok" if p.returncode == 0 else "failed", "output": p.stdout.decode("utf-8", "replace") if p.returncode == 0 else ""}


def no_symlink_ancestors(path: Path) -> None:
    for p in (path, *path.parents):
        if p.is_symlink():
            raise ValueError("symlink")


def read_regular(path: Path, limit: int = MAX_FILE) -> bytes:
    """Used only for explicitly named OS metadata and program source files."""
    no_symlink_ancestors(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
            raise ValueError("not_bounded_regular_file")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(limit + 1)
        if len(data) > limit:
            raise ValueError("too_large")
        return data
    finally:
        os.close(fd)


def describe(path: Path, logical: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"path": clean(logical or str(path))}
    try:
        s = path.lstat()
        out.update(exists=True, uid=s.st_uid, gid=s.st_gid,
                   mode=format(stat.S_IMODE(s.st_mode), "04o"), bytes=s.st_size, links=s.st_nlink,
                   kind="symlink" if stat.S_ISLNK(s.st_mode) else "directory" if stat.S_ISDIR(s.st_mode) else "file" if stat.S_ISREG(s.st_mode) else "special")
        if stat.S_ISLNK(s.st_mode):
            out["link_target"] = clean(os.readlink(path))
    except FileNotFoundError:
        out["exists"] = False
    except OSError:
        out["exists"] = None
        out["error"] = "unreadable_metadata"
    return out


def mounts(text: str) -> list[dict[str, str]]:
    result = []
    for line in text.splitlines():
        left, sep, right = line.partition(" - ")
        a, b = left.split(), right.split()
        if not sep or len(a) < 6 or len(b) < 1 or b[0] in PSEUDO_FS:
            continue
        target = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), a[4])
        # Mount source/options can contain credentials; intentionally omitted.
        result.append({"target": clean(target), "type": clean(b[0]),
                       "read_only": str("ro" in a[5].split(",")).lower()})
    return result


def health() -> dict[str, Any]:
    conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=4)
    try:
        conn.request("GET", "/api/health", headers={"Cache-Control": "no-cache"})
        res = conn.getresponse()
        body = res.read(32769)
        if len(body) > 32768:
            return {"ok": False, "reason": "response_too_large"}
        obj = json.loads(body)
        valid = res.status == 200 and isinstance(obj, dict) and obj.get("ok") is True and obj.get("app") == "dvizh"
        return {"ok": valid, "endpoint": "127.0.0.1:8000/api/health", "status": res.status}
    except Exception:
        return {"ok": False, "reason": "unavailable_or_invalid_json"}
    finally:
        conn.close()


class Inventory:
    def __init__(self, root: Path = Path("/"), run=command):
        self.root, self.run = root, run
        self.warnings: list[str] = []

    def p(self, path: str) -> Path:
        return self.root / path.lstrip("/")

    def listdir(self, path: str) -> list[Path]:
        try:
            p = self.p(path)
            no_symlink_ancestors(p)
            return sorted(p.iterdir())
        except OSError:
            self.warnings.append("cannot_list:" + path)
            return []
        except ValueError:
            self.warnings.append("symlink_directory_not_scanned:" + path)
            return []

    def paths(self) -> list[dict[str, Any]]:
        wanted = {"/opt", "/home", "/root", "/usr/local", "/var/lib/dvizh", "/etc/dvizh",
                  "/etc/systemd/system", "/var/lib/dvizh-release-gate", "/etc/sudoers.d",
                  "/etc/cron.d", "/var/spool/cron/crontabs", "/var/lib/docker/volumes",
                  "/var/lib/postgresql", "/var/lib/mysql", "/var/lib/redis", "/etc/letsencrypt",
                  "/srv", "/var/www", "/var/spool", "/var/backups", "/mnt", "/media"}
        for parent in ("/opt", "/var/lib", "/etc", "/usr/local/bin", "/usr/local/sbin", "/usr/local/libexec"):
            for p in self.listdir(parent):
                if p.name.startswith(("dvizh", "hermes")):
                    wanted.add(parent + "/" + p.name)
        for home in ["/root", *["/home/" + p.name for p in self.listdir("/home") if not p.is_symlink() and p.is_dir()]]:
            wanted.add(home)
            for suffix in (".hermes", ".claude", ".codex", ".config", ".local", ".ssh", ".config/systemd/user"):
                wanted.add(home + "/" + suffix)
        # Only lstat metadata, including for credentials/config directories.
        return [describe(self.p(p), p) for p in sorted(wanted)]

    def units(self) -> dict[str, Any]:
        r = self.run(["systemctl", "list-unit-files", "--type=service", "--no-pager", "--no-legend"])
        listed = {line.split()[0] for line in r["output"].splitlines() if line.strip()}
        local = {p.name for p in self.listdir("/etc/systemd/system") if p.name.endswith((".service", ".timer", ".socket", ".path"))}
        selected = {n for n in listed if n.startswith(SERVICE_PREFIXES) or n in SERVICE_NAMES}
        selected |= {n for n in local if n.endswith(".service")}
        selected |= {"dvizh.service", "dvizh-auth.service", "dvizh-ai-home.service", "dvizh-ai-approval.service"}
        if len(selected) > 150:
            self.warnings.append("service_inventory_truncated")
        items = []
        for name in sorted(selected)[:150]:
            if not re.fullmatch(r"[A-Za-z0-9_.@:+\\-]+\.service", name):
                continue
            show = self.run(["systemctl", "show", "--no-pager", "--property=" + ",".join(PROPERTIES), "--", name])
            info = kv(show["output"], PROPERTIES) if show["status"] == "ok" else {}
            if info.get("LoadState") == "not-found":
                continue
            items.append({"name": clean(name), "query_status": show["status"], **info})
        return {"discovery": r["status"], "items": items, "local_triggers": sorted(clean(n) for n in local if not n.endswith(".service"))}

    def docker(self) -> dict[str, Any]:
        r = self.run(["docker", "ps", "--all", "--no-trunc", "--format", "{{.ID}}"], timeout=12)
        if r["status"] != "ok":
            return {"status": r["status"], "containers": None}
        ids = [s for s in r["output"].splitlines() if re.fullmatch(r"[0-9a-f]{64}", s)]
        result = []
        for cid in ids[:50]:
            # No .Config, Env, commands, labels, logs or credential content.
            form = '{"id":"{{.Id}}","image_id":"{{.Image}}","running":{{.State.Running}},"mounts":{{json .Mounts}}}'
            t = self.run(["docker", "inspect", "--format", form, cid])
            item: dict[str, Any] = {"id": cid, "query_status": t["status"]}
            if t["status"] == "ok":
                try:
                    d = json.loads(t["output"])
                    item.update(image_id=clean(d.get("image_id", "")), running=d.get("running") is True,
                                mounts=[{k: clean(m.get(k, "")) for k in ("Type", "Source", "Destination")} for m in d.get("mounts", []) if isinstance(m, dict)])
                except (ValueError, TypeError):
                    item["query_status"] = "invalid_response"
            result.append(item)
        return {"status": "ok", "count": len(ids), "truncated": len(ids) > 50, "containers": result}

    def collect(self, with_health: bool = True) -> dict[str, Any]:
        os_file = self.p("/etc/os-release")
        # Standard Ubuntu /etc/os-release is a symlink to vendor metadata.
        try:
            vendor = self.p("/usr/lib/os-release") if os_file.is_symlink() else os_file
            release = kv(read_regular(vendor, 16384).decode(), ("ID", "VERSION_ID", "PRETTY_NAME"))
        except (OSError, ValueError, UnicodeError):
            release = {"error": "os_release_unavailable"}
        try:
            v = os.statvfs(self.root)
            disk = {"total_bytes": v.f_blocks * v.f_frsize, "free_bytes": v.f_bavail * v.f_frsize}
        except OSError:
            disk = {"error": "unavailable"}
        try:
            text = self.p("/proc/self/mountinfo").read_text()
            disks = mounts(text)
        except OSError:
            disks = []
            self.warnings.append("mount_inventory_unavailable")
        sizes = {}
        for name in ("/opt", "/home", "/root", "/usr/local", "/etc", "/var/lib", "/srv", "/var/www"):
            r = self.run(["du", "--summarize", "--one-file-system", "--block-size=1", "--", str(self.p(name))], timeout=20)
            token = r["output"].split(maxsplit=1)
            sizes[name] = {"status": r["status"], "allocated_bytes": int(token[0]) if r["status"] == "ok" and token and token[0].isdigit() else None}
        files = {}
        for name, expected in KNOWN.items():
            p = self.p("/opt/dvizh/static/" + name)
            try:
                h = hashlib.sha256(read_regular(p)).hexdigest()
                files[name] = {"sha256": h, "matches_last_confirmed_release": h == expected}
            except (OSError, ValueError):
                files[name] = {"error": "missing_unreadable_or_unsafe"}
        package_rows = self.run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Architecture}\n"])
        packages = []
        for line in package_rows["output"].splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and (parts[0] in RUNTIMES or re.fullmatch(r"python3\.\d+(?:-venv)?", parts[0])):
                packages.append({"name": clean(parts[0]), "version": clean(parts[1]), "arch": clean(parts[2])})
        ports = self.run(["ss", "--listening", "--tcp", "--no-header", "--numeric"])
        listeners = []
        if ports["status"] == "ok":
            for line in ports["output"].splitlines():
                parts = line.split()
                if len(parts) >= 4:
                    listeners.append(clean(parts[3]))
        account_rows = []
        if self.root == Path("/"):
            for a in pwd.getpwall():
                if a.pw_name in ("root", "exedev", "dvizh") or a.pw_dir.startswith("/home/"):
                    account_rows.append({"name": clean(a.pw_name), "uid": a.pw_uid, "gid": a.pw_gid, "home": clean(a.pw_dir)})
        result = {
            "schema": 1, "tool": VERSION, "mode": "inventory_only", "observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "root_access": os.geteuid() == 0, "os": release, "architecture": clean(platform.machine()), "hostname": clean(platform.node()),
            "python": clean(platform.python_version()), "cpu_count": os.cpu_count(), "disk": disk,
            "mounts": disks, "sizes": sizes, "services": self.units(), "paths": self.paths(),
            "docker": self.docker(), "runtime_packages": {"query_status": package_rows["status"], "items": packages},
            "accounts": account_rows, "listeners": {"query_status": ports["status"], "addresses": listeners},
            "application_health": health() if with_health else {"not_checked": True},
            "static_files": files, "last_confirmed_release": SOURCE_RELEASE,
            "backup_created": False, "migration_performed": False, "service_changes": False,
            "database_files_opened": False, "credential_contents_read": False,
            "not_inspected": ["environment/config values and external provider credentials", "database files/rows and live writers", "user crontab contents", "uncommitted Git changes", "external volumes and provider integrations", "target server and DNS"],
            "warnings": sorted(set(self.warnings)),
        }
        return result


def gib(n: int | None) -> str:
    return "?" if n is None else f"{n / (1024 ** 3):.1f} GiB"


def summary(r: dict[str, Any]) -> str:
    units = r["services"]["items"]
    names = {u["name"]: u for u in units}
    exists = {p["path"] for p in r["paths"] if p.get("exists")}
    lines = ["DVIZH MIGRATION / READ-ONLY INVENTORY", f"Tool: {VERSION}",
             f"Host: {r['hostname']}",
             f"OS: {r['os'].get('PRETTY_NAME', '?')} | {r['architecture']} | root={r['root_access']}",
             f"Disk /: total {gib(r['disk'].get('total_bytes'))}; free {gib(r['disk'].get('free_bytes'))}",
             "Sizes (allocated; nested mounts are listed separately):"]
    for p, d in r["sizes"].items():
        lines.append(f"  {p}: {gib(d.get('allocated_bytes'))} [{d['status']}]")
    lines.append("Custom/application services:")
    shown = [u for u in units if u["name"].startswith(SERVICE_PREFIXES) or u["name"] in {"nginx.service", "caddy.service", "docker.service"}]
    for u in shown[:18]:
        lines.append(f"  {u['name']}: {u.get('ActiveState', u['query_status'])}; user={u.get('User') or '(default root)'}")
    if len(shown) > 18:
        lines.append(f"  ... {len(shown) - 18} more (full report: --json)")
    auth = names.get("dvizh-auth.service", {})
    lines.append("Own login gateway: " + auth.get("ActiveState", "not confirmed"))
    lines.append("Hermes home(s): " + (", ".join(sorted(p for p in exists if p.endswith("/.hermes"))) or "not found"))
    lines.append("Docker: " + str(r["docker"].get("count", r["docker"]["status"])))
    lines.append("Disk mounts: " + (", ".join(m["target"] + "(" + m["type"] + ")" for m in r["mounts"][:8]) or "unknown"))
    lines.append("TCP listeners: " + ", ".join(r["listeners"]["addresses"][:15]))
    n = sum(x.get("matches_last_confirmed_release") is True for x in r["static_files"].values())
    lines.append(f"App static matches installed f6b8959c7d: {n}/5")
    lines.append("App /api/health JSON: " + ("OK" if r["application_health"].get("ok") is True else "NOT CONFIRMED"))
    lines.append(f"Inventory warnings: {len(r['warnings'])}; services discovery: {r['services']['discovery']}")
    lines += ["NO INSTALL / NO BACKUP / NO SERVICE STOP", "This report is not a complete backup manifest.", "Нужны: новый сервер (ОС/архитектура) и адрес сайта/домен."]
    return "\n".join(lines) + "\n"


def save_report(path: Path, report: dict[str, Any]) -> None:
    no_symlink_ancestors(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print a full metadata-only report instead of the short summary")
    parser.add_argument("--output", type=Path, help="Optionally create a NEW 0600 report file; never overwrite")
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("Для полного перечня нужна owner sudo-сессия. Никакие изменения не выполнялись.", file=sys.stderr)
        return 2
    if not args.json:
        print("Проверяю состав сервера. Не останавливаю службы и не открываю базы/секреты...", flush=True)
    report = Inventory().collect()
    if args.output:
        try:
            save_report(args.output, report)
        except (OSError, ValueError):
            print("Не удалось создать НОВЫЙ файл отчёта; существующие файлы не заменялись.", file=sys.stderr)
            return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else summary(report), end="\n" if args.json else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
