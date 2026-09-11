#!/usr/bin/env python3
"""Run unchanged test bytes in a disposable Git clone and OS namespaces.

No installation or dependency download. Missing tools fail closed. Host homes,
application state, sockets, /etc and /usr/local are absent from the mount tree.
This is a local test harness, not the privileged runtime verification boundary.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SHA = '9d492693de2c7cf66350293afcf42b74edeebaef'


def sandbox(copy, node=None):
    argv = ['/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
            '--uid', str(os.getuid()), '--gid', str(os.getgid()), '--cap-drop', 'ALL']
    for name in ('bin', 'lib', 'lib64', 'share'):
        path = Path('/usr')/name
        if path.exists(): argv += ['--ro-bind', str(path), str(path)]
    argv += ['--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
             '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev',
             '--tmpfs', '/tmp', '--dir', '/home/test', '--dir', '/var/lib', '--dir', '/opt',
             '--bind', str(copy), '/repo', '--chdir', '/repo', '--clearenv',
             '--setenv', 'HOME', '/home/test', '--setenv', 'PATH', '/tools:/usr/bin:/bin',
             '--setenv', 'PYTHONDONTWRITEBYTECODE', '1', '--setenv', 'GIT_CONFIG_NOSYSTEM', '1']
    if node: argv += ['--ro-bind', str(node), '/tools/node']
    return argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--health', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.geteuid() == 0: raise SystemExit('unprivileged harness only')
    repo = Path(__file__).resolve().parents[1]
    command = args.command or ['python3', '-m', 'unittest', 'discover', '-s', 'tests/hermes_autopilot', '-v']
    if command[0] == '--': command = command[1:]
    with tempfile.TemporaryDirectory(prefix='dvizh-v231-isolated-') as temp:
        root = Path(temp); copy = root/'repo'
        # Keep complete local history: feature contracts resolve historical blobs.
        subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', str(repo), str(copy)], check=True)
        if args.health:
            subprocess.run(['git', '-C', str(copy), 'checkout', '--quiet', SHA], check=True)
        else:
            for rel in ('hermes-dev-v2', 'tests/hermes_autopilot', '.github/workflows'):
                shutil.copytree(repo/rel, copy/rel, dirs_exist_ok=True)
        node = shutil.which('node')
        if node:
            shutil.copyfile(Path(node).resolve(), root/'node'); (root/'node').chmod(0o755)
        boundary = sandbox(copy, root/'node' if node else None)
        sentinel = root/'host-only'; sentinel.write_text('fixture sentinel')
        probe = '''import os, pathlib, socket, subprocess, sys
assert os.geteuid() != 0
status=pathlib.Path('/proc/self/status').read_text()
assert 'NoNewPrivs:\\t1' in status
assert 'CapEff:\\t0000000000000000' in status
assert not pathlib.Path(sys.argv[1]).exists()
assert not pathlib.Path('/home/exedev').exists()
assert not pathlib.Path('/usr/local/sbin/dvizhrelease').exists()
assert not pathlib.Path('/var/lib/dvizh').exists()
subprocess.run(['/bin/sh','-c','test ! -e "$1" && test ! -e /home/exedev', 'probe',sys.argv[1]],check=True)
s=socket.socket();s.settimeout(.1)
try: s.connect(('192.0.2.1',443))
except OSError: pass
else: raise AssertionError('network escaped')
print('isolation probe PASS; uid=',os.geteuid(),'groups=',os.getgroups(),flush=True)
'''
        subprocess.run(boundary+['python3', '-c', probe, str(sentinel)], check=True)
        print(json.dumps({'command': command, 'health_commit': SHA if args.health else None,
                          'boundary': 'mount/pid/network/user namespaces; no capabilities; no_new_privs',
                          'supplementary_groups': 'inherited IDs unmapped except invoking gid; not a production privilege-drop contract'}), flush=True)
        try:
            result = subprocess.run(boundary+command, timeout=300)
            print('COMMAND_EXIT='+str(result.returncode), flush=True)
            return result.returncode
        except subprocess.TimeoutExpired:
            print('BLOCKED: command timeout after 300 seconds', flush=True)
            return 124


if __name__ == '__main__':
    raise SystemExit(main())
