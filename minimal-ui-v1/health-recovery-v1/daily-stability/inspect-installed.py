#!/usr/bin/env python3
"""Read-only DVIZH fingerprint. Not an installer; never reads personal state or keys."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import urllib.request

RELEASE = '20260914-daily-stability-1'
EXPECTED = {
 'ai-home-v2.css': ('a43b073c4788e1ba93240fb46bc726b1e07edfdbe653183e0a115a01ffdb42fb', 'a43b073c4788e1ba93240fb46bc726b1e07edfdbe653183e0a115a01ffdb42fb'),
 'ai-home-v2.js': ('3ae439ba11611bd5ec5ea0c61e81245e9032fba36396c4ffeeaebc871c5fb186', 'b8538939f48be484d21eaa56c991fc237b20188f917eed3c65ae07cb25baaf76'),
 'app.js': ('c6882d8821515f0046742e99cce10ed9b8115fabd4c7cd0a06c830a25a6366bf', '41cd3d0683eabdf649c47878ad214408af1acb9c93352fe1c12302adc248b84e'),
 'boot.js': ('1c766410e239a8092de001d6450da6fabcdd552a91f7de593abb0d626fbb0500', '1c766410e239a8092de001d6450da6fabcdd552a91f7de593abb0d626fbb0500'),
 'index.html': ('973bd18e8086cad28d889a10768e94d8b85ca086c4a0cbac4887ef6a9f8f2ebc', '41bc4d1509c5818675d488164f01e35bf8dcdb35c15d660c38fde72f7a77ee02'),
 'manual.html': ('8bfc125485dab2e6134ca5154991bad7869d3f9d3503dae4449f8bec55599797', '9a0847bc1e9b0bcd2c775974c94994d8c49979fb5316ce6372e408c283fee514'),
 'styles.css': ('4fc9de09753daffb3dcacba770684b7f6a152c23a9956fb85a797beba068c8c5', '4fc9de09753daffb3dcacba770684b7f6a152c23a9956fb85a797beba068c8c5'),
 'sw.js': ('7065b95ceac21bf528eeef9635a0b67141fac2e5135dc51e9aaf3c0c085fe86d', '7065b95ceac21bf528eeef9635a0b67141fac2e5135dc51e9aaf3c0c085fe86d'),
 'sync.js': ('04e10a67cb566180ec3590dae4b73dc19f3bb2083fca6ec7002e987a3bb63a71', '58991ea1a0d95facbe21402792e7607d6c4ff55603234b808f646cd8b5f5c12e'),
}
VERSION_PATHS = ('/usr/local/bin/dvizhautopilot', '/usr/local/sbin/dvizhgitpush', '/usr/local/sbin/dvizhrelease')
SERVICES = ('dvizh.service', 'dvizh-ai-home.service', 'dvizh-ai-approval.service')
MAX_FILE = 5_000_000


def read_regular(path: Path):
    # Open each component relative to an already-open directory; never follow links.
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute whitelist path required')
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = following
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_FILE:
                raise ValueError('not a single-link bounded regular file')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = stream.read(MAX_FILE + 1)
            after = os.fstat(fd)
            if len(data) > MAX_FILE or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('file changed during read')
            return data, before
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def fingerprint(path: Path, expected=None):
    try:
        data, info = read_regular(path)
        digest = hashlib.sha256(data).hexdigest()
        result = {'sha256': digest, 'bytes': len(data), 'uid': info.st_uid, 'gid': info.st_gid,
                  'mode': format(stat.S_IMODE(info.st_mode), '04o')}
        if expected:
            old, new = expected
            result['match'] = 'preserved' if old == new == digest else 'candidate' if digest == new else 'baseline' if digest == old else 'DIFFERENT_STOP'
        return result
    except Exception as error:
        return {'error': type(error).__name__, 'match': 'UNREADABLE_STOP'}


def version_literal(path: Path):
    try:
        data, _ = read_regular(path)
        # AST is parsed, not imported or executed. Nothing runs from these components.
        tree = ast.parse(data.decode('utf-8'))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets):
                value = node.value.value if isinstance(node.value, ast.Constant) else None
                if isinstance(value, str) and re.fullmatch(r'\d{4}\.\d{2}\.\d{2}-[A-Za-z0-9_.-]{1,100}', value):
                    return {'version_literal': value, 'executed': False}
        return {'version_literal': None, 'executed': False}
    except Exception as error:
        return {'error': type(error).__name__, 'executed': False}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def health():
    try:
        req = urllib.request.Request('http://127.0.0.1:8000/api/health', headers={'Accept':'application/json','Cache-Control':'no-cache'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(req, timeout=5) as response:
            raw = response.read(65537)
            if response.status != 200 or len(raw) > 65536 or response.headers.get_content_type() != 'application/json':
                raise ValueError('unexpected health response')
        value = json.loads(raw)
        ok = isinstance(value, dict) and value.get('ok') is True and value.get('app') == 'dvizh'
        return {'ok': ok, 'endpoint': '/api/health', 'json_validated': True}
    except Exception as error:
        return {'ok': False, 'endpoint': '/api/health', 'error': type(error).__name__}


def service_status(name):
    try:
        cp = subprocess.run(['/usr/bin/systemctl', 'is-active', name], capture_output=True, text=True, timeout=5, check=False)
        state = cp.stdout.strip()
        return state if state in {'active','inactive','failed','activating','deactivating','unknown'} else 'unavailable'
    except Exception:
        return 'unavailable'


def main():
    report = {
        'report': 'DVIZH read-only preflight; NOT AN INSTALLATION', 'release': RELEASE,
        'observed_at_utc': datetime.now(timezone.utc).isoformat(), 'installation_performed': False,
        'personal_state_read': False, 'requires_approved_release': True,
        'static_files': {name:fingerprint(Path('/opt/dvizh/static')/name, expected) for name,expected in EXPECTED.items()},
        'backend': fingerprint(Path('/opt/dvizh/server.py')),
        'control_component_literals': {Path(name).name:version_literal(Path(name)) for name in VERSION_PATHS},
        'services': {name:service_status(name) for name in SERVICES}, 'application_health': health(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

if __name__ == '__main__':
    main()
