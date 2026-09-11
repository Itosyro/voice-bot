#!/usr/bin/python3
"""Standalone owner bootstrap; authenticate this exact buffer BEFORE execution.

See BOOTSTRAP-v232.md. No adjacent imports, shell, Git, or candidate interpreter.
The contract is an independently authenticated owner input, never a candidate
claim. All installation operations remain inside the verified installer buffer.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import stat


def verified_bytes(path, expected):
    if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
        raise RuntimeError('invalid external digest')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        st=os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:
            raise RuntimeError('bootstrap input must be a single-link regular file')
        data=stream.read(5_000_001)
    if len(data)>5_000_000 or hashlib.sha256(data).hexdigest()!=expected:
        raise RuntimeError('authenticated bootstrap payload mismatch')
    return data


def bootstrap(payload, installer_sha256, payload_sha256, *, apply=False):
    if not sys.flags.isolated or not sys.flags.no_site:
        raise RuntimeError('trusted /usr/bin/python3 -I -S required')
    payload=Path(payload)
    data=verified_bytes(payload/'owner_install.py',installer_sha256)
    scope={'__name__':'verified_owner_installer','__file__':str(payload/'owner_install.py')}
    exec(compile(data,'<authenticated owner installer>','exec',dont_inherit=True),scope)
    gate=scope['gate_for']()
    if apply:
        gate.require_root()
        return scope['install'](gate,payload,payload_sha256)
    return {'status':'prepared-only','targets':[r['target'] for r in scope['prepare'](gate,payload,payload_sha256)]}


if __name__=='__main__':
    # Digests originate from the authenticated external owner contract.
    if len(sys.argv) not in (4,5) or (len(sys.argv)==5 and sys.argv[4]!='--apply'):
        raise SystemExit('payload-directory installer-sha256 payload-sha256 [--apply]')
    print(json.dumps(bootstrap(*sys.argv[1:4],apply=len(sys.argv)==5),sort_keys=True))
