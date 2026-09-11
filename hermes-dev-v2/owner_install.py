#!/usr/bin/env python3
"""Offline owner upgrade; not installed as a privileged gate or sudo capability.

Default is read-only preparation. --apply requires root and an independently
reviewed payload digest. Fixture roots are forbidden for root execution.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

SKILL_TARGET = '/home/exedev/.hermes/skills/dvizh/dvizh-dev/SKILL.md'
TARGETS = {
    '/usr/local/bin/dvizhautopilot': 'dvizhautopilot.py',
    '/usr/local/sbin/dvizhrelease': 'dvizhrelease.py',
    '/usr/local/sbin/dvizhgitpush': 'dvizhgitpush.py',
    SKILL_TARGET: 'TRUSTED-MODE-v2.3.md',
}
MARKER = b'<!-- DVIZH TRUSTED MODE v2.3 -->'


def gate_for(root=Path('/'), *, fixture=False):
    root = Path(root)
    if os.geteuid() == 0 and (fixture or root != Path('/')):
        raise RuntimeError('root cannot use fixture overrides')
    if not fixture and root != Path('/'):
        raise RuntimeError('production root is fixed')
    spec = importlib.util.spec_from_file_location('owner_release_primitives', Path(__file__).with_name('dvizhrelease.py'))
    gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
    gate.TEST_MODE = fixture; gate.FS_ROOT = root
    gate.APPROVAL_ROOT = root/'var/lib/dvizh-release-gate/approvals'
    gate.BACKUP_ROOT = root/'var/lib/dvizh-release-gate/backups'
    gate.SOURCE_ROOT = ''; gate.HTTP_BASE = 'http://127.0.0.1:8000'
    return gate


def policy_bytes(payload):
    return (payload/'TRUSTED-MODE-v2.3.md').read_bytes()


def payload_digest(payload):
    digest = hashlib.sha256()
    for name in sorted({*TARGETS.values(), 'owner_install.py'}):
        data = (payload/name).read_bytes()
        digest.update(name.encode()+b'\0'+hashlib.sha256(data).digest())
    return digest.hexdigest()


def prepare(gate, payload, expected):
    for name in {*TARGETS.values(), 'owner_install.py'}:
        gate.checked_path(payload/name)
    if not expected or payload_digest(payload) != expected:
        raise gate.GateError('owner payload digest mismatch')
    policy = policy_bytes(payload)
    if policy.count(MARKER) != 1:
        raise gate.GateError('invalid additive skill policy')
    records = []
    for target, source in TARGETS.items():
        path = gate.fs_path(target)
        gate.checked_path(path)
        old, metadata = gate.read_regular(path)
        if target == SKILL_TARGET:
            if MARKER in old:
                if not old.endswith(policy) or old.count(MARKER) != 1:
                    raise gate.GateError('conflicting v2.3 policy; owner reconciliation required')
                new = old
            else:
                new = old + policy
            if not gate.TEST_MODE:
                import pwd
                user = pwd.getpwnam('exedev')
                if metadata != dict(uid=user.pw_uid, gid=user.pw_gid, mode=0o600):
                    raise gate.GateError('installed skill metadata mismatch')
        else:
            if metadata != gate.privileged_metadata():
                raise gate.GateError('installed gate metadata mismatch')
            new = gate.read_regular(payload/source)[0]
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
            backup = Path(tempfile.mkdtemp(prefix='owner-v23.', dir=gate.BACKUP_ROOT)); os.fsync(parent)
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
        journal = dict(schema=1, kind='owner-install-v23', backup=str(backup), mapping_sha256=hashlib.sha256(raw).hexdigest(), state='pending', restarts=[])
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


if __name__ == '__main__':
    main()
