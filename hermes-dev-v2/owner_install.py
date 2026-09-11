#!/usr/bin/env python3
"""Offline owner upgrade; not installed as a privileged gate or sudo capability.

Default is read-only preparation. --apply requires root and an independently
reviewed payload digest. Fixture roots are forbidden for root execution.
"""
from __future__ import annotations
import argparse
import hashlib
import fcntl
import signal
import threading
import stat
import secrets
from contextlib import contextmanager
from types import SimpleNamespace
import json
import os
import tempfile
from pathlib import Path

SKILL_TARGET = '/home/exedev/.hermes/skills/dvizh/dvizh-dev/SKILL.md'
TARGETS = {
    '/usr/local/bin/dvizhautopilot': 'dvizhautopilot.py',
    '/usr/local/sbin/dvizhrelease': 'dvizhrelease.py',
    '/usr/local/sbin/dvizhgitpush': 'dvizhgitpush.py',
}
MARKER = b'<!-- DVIZH TRUSTED MODE v2.3 -->'


def gate_for(root=Path('/'), *, fixture=False):
    root = Path(root)
    if os.geteuid() == 0 and (fixture or root != Path('/')):
        raise RuntimeError('root cannot use fixture overrides')
    if not fixture and root != Path('/'):
        raise RuntimeError('production root is fixed')
    global TEST_MODE, FS_ROOT, APPROVAL_ROOT, BACKUP_ROOT
    TEST_MODE = fixture; FS_ROOT = root
    APPROVAL_ROOT = root/'var/lib/dvizh-release-gate/approvals'
    BACKUP_ROOT = root/'var/lib/dvizh-release-gate/backups'
    return SimpleNamespace(**globals())


def policy_bytes(payload):
    return (payload/'TRUSTED-MODE-v2.3.md').read_bytes()


def buffer_digest(buffers):
    digest = hashlib.sha256()
    for name, data in sorted(buffers.items()):
        digest.update(name.encode()+b'\0'+hashlib.sha256(data).digest())
    return digest.hexdigest()


def payload_digest(payload):
    return buffer_digest({name: (payload/name).read_bytes()
                          for name in {*TARGETS.values(), 'owner_install.py'}})


def prepare(gate, payload, expected):
    buffers = {}
    for name in {*TARGETS.values(), 'owner_install.py'}:
        path = payload/name
        gate.checked_path(path)
        if not gate.TEST_MODE:
            parent = gate.walk_parent(path, trusted=True); os.close(parent)
        data, metadata = gate.read_regular(path)
        if not gate.TEST_MODE and (metadata['uid'] != 0 or metadata['gid'] != 0 or metadata['mode'] & 0o022):
            raise gate.GateError('payload staging must be root owned and immutable to callers')
        buffers[name] = data
    if not expected or buffer_digest(buffers) != expected:
        raise gate.GateError('owner payload digest mismatch')
    records = []
    for target, source in TARGETS.items():
        path = gate.fs_path(target)
        gate.checked_path(path)
        old, metadata = gate.read_regular(path)
        if metadata != gate.privileged_metadata():
            raise gate.GateError('installed gate metadata mismatch')
        new = buffers[source]
        compile(new, source, 'exec', dont_inherit=True)
        parent = gate.walk_parent(path, trusted=True); os.close(parent)
        records.append(dict(target=target, old=old, new=new, metadata=metadata))
    return records


def install(gate, payload, expected):
    # Payload and all installed bytes inspected before lock/state creation.
    prepare(gate, payload, expected)
    with gate.transaction():
        records = prepare(gate, payload, expected)
        if all(r['old'] == r['new'] for r in records):
            return dict(ok=True, status='unchanged')
        parent = gate.walk_parent(gate.BACKUP_ROOT/'placeholder', create=True, trusted=True)
        try:
            os.fchmod(parent, 0o700)
            backup = Path(tempfile.mkdtemp(prefix='owner-v232.', dir=gate.BACKUP_ROOT)); os.fsync(parent)
        finally: os.close(parent)
        mapping = []
        for i, r in enumerate(records):
            dest = gate.fs_path(r['target'])
            gate._STATE.parents[dest] = gate.walk_parent(dest, trusted=r['target'] != SKILL_TARGET)
            bp = backup/str(i)
            sha = hashlib.sha256(r['old']).hexdigest()
            gate.atomic_write(bp, r['old'], r['metadata'])
            mapping.append(dict(target=r['target'], backup=str(bp), sha256=sha, **r['metadata']))
        metadata = dict(uid=os.geteuid(), gid=os.getegid(), mode=0o600)
        raw = json.dumps(mapping, sort_keys=True).encode()
        gate.atomic_write(backup/'mapping.json', raw, metadata)
        for r, m in zip(records, mapping):
            gate.verify_file(Path(m['backup']), m['sha256'], m)
            gate.verify_file(gate.fs_path(m['target']), m['sha256'], m)
        gate.verify_file(backup/'mapping.json', hashlib.sha256(raw).hexdigest(), metadata)
        journal = dict(schema=1, kind='owner-install-v232', backup=str(backup), mapping_sha256=hashlib.sha256(raw).hexdigest(), state='pending', restarts=[])
        gate.atomic_write(gate.APPROVAL_ROOT/'pending.json', json.dumps(journal).encode(), metadata)
        try:
            for r in records:
                gate.atomic_write(gate.fs_path(r['target']), r['new'], r['metadata'])
            for r in records:
                gate.verify_file(gate.fs_path(r['target']), hashlib.sha256(r['new']).hexdigest(), r['metadata'])
            gate.journal_clear(journal)
        except BaseException as failure:
            with gate.rollback_signals():
                errors = ["journal cleanup unconfirmed"] if isinstance(failure, gate.JournalCleanupError) else []
                if not os.path.lexists(gate.APPROVAL_ROOT/'pending.json'):
                    try: gate.atomic_write(gate.APPROVAL_ROOT/'pending.json', json.dumps(journal).encode(), metadata)
                    except BaseException: errors.append('cannot re-arm journal')
                for m in reversed(mapping):
                    try:
                        gate.verify_file(Path(m['backup']), m['sha256'], m)
                        gate.atomic_write(gate.fs_path(m['target']), gate.read_regular(Path(m['backup']))[0], m)
                    except BaseException: errors.append('restore failed: '+m['target'])
                for m in mapping:
                    try:
                        path = gate.fs_path(m['target'])
                        gate.canonical_parent(path, gate._STATE.parents[path])
                        gate.verify_file(path, m['sha256'], m)
                    except BaseException: errors.append('restoration identity unconfirmed')
                if errors: raise gate.GateError('CRITICAL: owner rollback unconfirmed; pending journal retained') from failure
                gate.journal_clear(journal)
                raise gate.GateError('owner install failed; rollback confirmed') from failure
        return dict(ok=True, status='installed', backup=str(backup))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-payload-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    gate = gate_for()
    payload = Path(__file__).resolve().parent
    if args.apply:
        gate.require_root()
        result = install(gate, payload, args.expected_payload_sha256)
    else:
        rows = prepare(gate, payload, args.expected_payload_sha256)
        result = dict(ok=True, status='prepared-only', targets=[r['target'] for r in rows])
    print(json.dumps(result, sort_keys=True))


# Standalone bootstrap primitives. These bytes require independent owner review
# BEFORE invoking this installer; a candidate-supplied digest is not bootstrap trust.
MAX_FILE = 5_000_000
TEST_MODE = False
FS_ROOT = Path('/')
APPROVAL_ROOT = Path('/var/lib/dvizh-release-gate/approvals')
BACKUP_ROOT = Path('/var/lib/dvizh-release-gate/backups')
_STATE = threading.local()


def require_root():
    if os.geteuid() == 0 and TEST_MODE:
        raise GateError('root cannot use fixtures')
    if not TEST_MODE and os.geteuid() != 0:
        raise GateError('owner installation requires root')


def canonical_path(value: str, *, absolute: bool) -> bool:
    return (isinstance(value, str) and bool(value) and "\\" not in value
            and "\0" not in value and value.startswith("/") == absolute
            and not value.startswith("//") and str(Path(value)) == value
            and ".." not in Path(value).parts)


class GateError(RuntimeError):
    pass


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
    if st.st_uid != (os.geteuid() if TEST_MODE else 0) or st.st_gid != (os.getegid() if TEST_MODE else 0) or st.st_mode & 0o022:
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


def fs_path(target: str) -> Path:
    if not target.startswith("/"):
        raise GateError(f"target must be absolute: {target}")
    if FS_ROOT == Path("/"):
        return Path(target)
    return FS_ROOT / target.lstrip("/")


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


if __name__ == '__main__':
    main()
