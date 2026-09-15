#!/usr/bin/env python3
"""Read-only migration inventory. Never exports secrets or starts/stops services.
Only a private metadata report is written, under a new /var/tmp directory.
This is NOT a backup, a restore utility, or proof of a consistent data snapshot.
"""
from __future__ import annotations
import argparse
import datetime as dt
import grp
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
import tempfile
import time

VERSION = '2026-09-15.1'
BASELINE_RELEASE = 'f6b8959c7d05eea434fbe25937b6428b70ed1716'
SAFE_PATH = '/usr/sbin:/usr/bin:/sbin:/bin'
UNIT_RE = re.compile(r'^[A-Za-z0-9_.@:\\-]+\.(?:service|socket|timer|path)$')
STATIC_NAMES = ('sync.js', 'app.js', 'ai-home-v2.js', 'index.html', 'manual.html',
                'styles.css', 'ai-home-v2.css', 'boot.js', 'sw.js')
EXPECTED = {
 'sync.js':'58991ea1a0d95facbe21402792e7607d6c4ff55603234b808f646cd8b5f5c12e',
 'app.js':'41cd3d0683eabdf649c47878ad214408af1acb9c93352fe1c12302adc248b84e',
 'ai-home-v2.js':'b8538939f48be484d21eaa56c991fc237b20188f917eed3c65ae07cb25baaf76',
 'index.html':'41bc4d1509c5818675d488164f01e35bf8dcdb35c15d660c38fde72f7a77ee02',
 'manual.html':'9a0847bc1e9b0bcd2c775974c94994d8c49979fb5316ce6372e408c283fee514',
}
KNOWN = (
 '/etc/dvizh', '/var/lib/dvizh', '/var/lib/dvizh/auth-identity.json',
 '/var/lib/dvizh-release-gate', '/var/lib/dvizh-git-push-gate',
 '/var/lib/docker', '/var/lib/containerd', '/var/lib/postgresql', '/var/lib/mysql',
 '/var/lib/redis', '/etc/nginx', '/etc/caddy', '/etc/letsencrypt',
 '/usr/local/bin/dvizhautopilot', '/usr/local/sbin/dvizhgitpush',
 '/usr/local/sbin/dvizhrelease', '/usr/local/libexec',
)


def printable(value):
    """Escape terminal control characters; never return command stderr."""
    return ''.join(c if c.isprintable() else '?' for c in str(value))[:1024]


def parse_os(text):
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        if sep and key in ('ID', 'VERSION_ID', 'PRETTY_NAME'):
            out[key] = printable(value.strip().strip('\"\''))
    return out


def parse_units(text):
    out = []
    for line in text.splitlines():
        cols = line.split()
        if cols and UNIT_RE.fullmatch(cols[0]):
            out.append({'unit': cols[0], 'state': cols[1:4]})
    return out


def parse_properties(text):
    allowed = {'Id', 'User', 'Group', 'WorkingDirectory', 'EnvironmentFiles',
               'FragmentPath', 'DropInPaths', 'ActiveState', 'SubState', 'UnitFileState'}
    out = {}
    for line in text.splitlines():
        key, sep, val = line.partition('=')
        if sep and key in allowed:
            out[key] = printable(val)
    return out


def file_meta(path, hash_code=False):
    p = Path(path)
    out = {'path': printable(path)}
    try:
        s = p.lstat()
    except FileNotFoundError:
        return {**out, 'present': False}
    except OSError:
        return {**out, 'present': None, 'error': 'metadata_unreadable'}
    out.update(present=True, uid=s.st_uid, gid=s.st_gid,
               mode=oct(stat.S_IMODE(s.st_mode)), bytes=s.st_size, links=s.st_nlink,
               kind='symlink' if stat.S_ISLNK(s.st_mode) else
                    'directory' if stat.S_ISDIR(s.st_mode) else
                    'file' if stat.S_ISREG(s.st_mode) else 'special')
    # Only known PUBLIC static code may be hashed; never hashes credentials/data.
    if hash_code and stat.S_ISREG(s.st_mode) and s.st_size <= 8 * 1024 * 1024:
        fd = None
        try:
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            s2 = os.fstat(fd)
            if (s.st_dev, s.st_ino, s.st_size) != (s2.st_dev, s2.st_ino, s2.st_size):
                raise OSError('changed')
            with os.fdopen(fd, 'rb') as stream:
                fd = None
                data = stream.read(8 * 1024 * 1024 + 1)
                end = os.fstat(stream.fileno())
            if len(data) != s2.st_size or end.st_mtime_ns != s2.st_mtime_ns:
                raise OSError('changed')
            out['sha256'] = hashlib.sha256(data).hexdigest()
        except OSError:
            out['error'] = 'code_changed_or_unreadable'
        finally:
            if fd is not None:
                os.close(fd)
    return out


class Probe:
    def __init__(self, seconds=180):
        self.deadline = time.monotonic() + seconds
        self.gaps = []

    def run(self, args, timeout=12):
        binary = shutil.which(args[0], path=SAFE_PATH)
        if binary is None:
            self.gaps.append(args[0] + ':not_installed')
            return None
        left = self.deadline - time.monotonic()
        if left < 0.2:
            self.gaps.append(args[0] + ':time_budget_exceeded')
            return None
        try:
            # No inherited API keys, Docker context or proxy variables.
            done = subprocess.run([binary] + list(args[1:]), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                errors='replace', timeout=max(0.1, min(timeout, left)),
                env={'PATH': SAFE_PATH, 'LC_ALL': 'C', 'LANG': 'C', 'HOME': '/root',
                     'SYSTEMD_PAGER': '', 'SYSTEMD_COLORS': '0'}, check=False)
        except subprocess.TimeoutExpired:
            self.gaps.append(args[0] + ':timeout')
            return None
        except OSError:
            self.gaps.append(args[0] + ':unavailable')
            return None
        if done.returncode:
            self.gaps.append(args[0] + ':exit_' + str(done.returncode))
            return None
        if len(done.stdout) > 2 * 1024 * 1024:
            self.gaps.append(args[0] + ':output_limit')
            return None
        return done.stdout


def directory_names(path):
    try:
        return [printable(p.name) for p in sorted(Path(path).iterdir())]
    except FileNotFoundError:
        return []
    except OSError:
        return None


def account_rows():
    rows = []
    for p in pwd.getpwall():
        if p.pw_name:
            memberships = sorted(g.gr_name for g in grp.getgrall()
                                 if p.pw_name in g.gr_mem or g.gr_gid == p.pw_gid)
            rows.append({'name': p.pw_name, 'uid': p.pw_uid, 'gid': p.pw_gid,
                         'home': printable(p.pw_dir), 'shell': printable(p.pw_shell),
                         'groups': memberships})
    return rows


def docker_inventory(probe):
    # Explicit LOCAL rootful daemon. Does not read .Config.Env or run a container.
    prefix = ['docker', '--host', 'unix:///var/run/docker.sock']
    if not Path('/var/run/docker.sock').exists():
        return {'local_rootful_socket': False, 'containers': [],
                'rootless_and_remote_daemons': 'not_queried'}
    text = probe.run(prefix + ['ps', '-aq', '--no-trunc'])
    if text is None:
        return {'local_rootful_socket': True, 'error': 'unreadable', 'containers': []}
    ids = [x for x in text.splitlines() if re.fullmatch('[a-f0-9]{12,64}', x)]
    rows = []
    # Fields explicitly selected to avoid environment variables, labels, commands.
    fmt = ('{"id":{{json .Id}},"name":{{json .Name}},"image":{{json .Config.Image}},'
           '"status":{{json .State.Status}},"mounts":{{json .Mounts}},'
           '"restart":{{json .HostConfig.RestartPolicy.Name}}}')
    for cid in ids[:100]:
        raw = probe.run(prefix + ['inspect', '--format', fmt, cid])
        try:
            row = json.loads(raw) if raw else {'id': cid, 'error': 'unreadable'}
            # Strip mount options; they can contain sensitive driver configuration.
            if 'mounts' in row:
                row['mounts'] = [{k: m[k] for k in ('Type','Source','Destination','RW','Name') if k in m}
                                 for m in row['mounts']]
            rows.append(row)
        except (ValueError, TypeError, KeyError):
            rows.append({'id': cid, 'error': 'invalid_metadata'})
    if len(ids) > 100:
        probe.gaps.append('docker:container_limit')
    return {'local_rootful_socket': True, 'containers': rows,
            'rootless_and_remote_daemons': 'not_queried'}


def collect():
    q = Probe()
    root = os.geteuid() == 0
    disk = shutil.disk_usage('/')
    try:
        system = parse_os(Path('/etc/os-release').read_text())
    except OSError:
        system = {}; q.gaps.append('os_release:unreadable')
    try:
        memory = int(re.search(r'^MemTotal:\s+(\d+)', Path('/proc/meminfo').read_text(), re.M)[1]) * 1024
    except (OSError, TypeError):
        memory = None
    units = parse_units(q.run(['systemctl','list-units','--all',
                        '--type=service,timer,socket,path','--no-pager','--plain','--no-legend']) or '')
    files = parse_units(q.run(['systemctl','list-unit-files','--type=service,timer,socket,path',
                             '--no-pager','--no-legend']) or '')
    custom = directory_names('/etc/systemd/system')
    names = {r['unit'] for r in units if r['unit'].startswith(('dvizh','hermes'))}
    names.update(n for n in (custom or []) if UNIT_RE.fullmatch(n))
    properties = []
    fields = 'Id,ActiveState,SubState,User,Group,WorkingDirectory,EnvironmentFiles,FragmentPath,DropInPaths,UnitFileState'
    for n in sorted(names):
        raw = q.run(['systemctl', 'show', n, '--no-pager', '--property=' + fields], timeout=5)
        properties.append(parse_properties(raw or 'Id=' + n))
    accounts = account_rows()
    home_meta = []
    for a in accounts:
        if not (a['uid'] == 0 or 1000 <= a['uid'] < 65534 or a['name'].startswith(('dvizh', 'hermes'))):
            continue
        h = Path(a['home'])
        home_meta.append({'user': a['name'], 'home': str(h),
            'hermes_dir': file_meta(h / '.hermes'), 'hermes_agent_dir': file_meta(h / 'hermes-agent'),
            'ssh_dir': file_meta(h / '.ssh'),
            'user_unit_files': directory_names(h / '.config/systemd/user'),
            'linger': file_meta('/var/lib/systemd/linger/' + a['name'])['present'],
            'rootless_docker_socket': file_meta('/run/user/' + str(a['uid']) + '/docker.sock')['present']})
    sizes = []
    for p in ('/etc','/opt','/usr/local','/home','/root','/srv','/var/lib','/var/spool'):
        raw = q.run(['du', '-s', '-x', '-B1', '--', p], timeout=18)
        number = raw.split(None,1)[0] if raw else ''
        sizes.append({'path':p, 'allocated_bytes':int(number) if number.isdigit() else None})
    packages = q.run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\t${db:Status-Status}\n'])
    package_rows = [x.split('\t')[:2] for x in (packages or '').splitlines()
                    if len(x.split('\t')) == 3 and x.split('\t')[2] == 'installed']
    mounts = q.run(['findmnt','--json','--real','--output','TARGET,FSTYPE'])
    try:
        mounts = json.loads(mounts) if mounts else None
    except ValueError:
        mounts = None; q.gaps.append('findmnt:parse_error')
    static = [file_meta('/opt/dvizh/static/' + n, hash_code=True) for n in STATIC_NAMES]
    for entry in static:
        n = Path(entry['path']).name
        if n in EXPECTED:
            entry['matches_last_reported_release'] = entry.get('sha256') == EXPECTED[n]
    docker = docker_inventory(q)
    # Public health only; curl cannot send browser cookies/credentials by default (-q).
    raw_health = q.run(['curl','-q','--noproxy','*','-fsS','--max-time','5',
                       '--max-filesize','65536','http://127.0.0.1:8000/api/health'])
    try:
        health = json.loads(raw_health) if raw_health else {}
        health_ok = health.get('ok') is True and health.get('app') == 'dvizh'
    except (ValueError, AttributeError):
        health_ok = False
    paths = [file_meta(p) for p in KNOWN]
    # Metadata only for project directories, never recursive contents.
    for base in ('/opt', '/srv'):
        for n in directory_names(base) or []:
            paths.append(file_meta(Path(base)/n))
    return {
      'schema':1, 'tool_version':VERSION, 'kind':'READ_ONLY_MIGRATION_INVENTORY_NOT_BACKUP',
      'observed_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'root_inventory':root,
      'os':system, 'architecture':platform.machine(), 'kernel':platform.release(),
      'memory_bytes':memory, 'cpu_count':os.cpu_count(),
      'root_disk':{'total':disk.total,'used':disk.used,'free':disk.free},
      'mounts':mounts, 'directory_sizes_non_recursive_mounts':sizes,
      'accounts_without_password_fields':accounts, 'home_metadata':home_meta,
      'all_system_units':units, 'system_unit_files':files, 'custom_unit_properties':properties,
      'cron_metadata':{'system':directory_names('/etc/cron.d'),
                       'user_spool':directory_names('/var/spool/cron/crontabs'),
                       'root_crontab_file':file_meta('/etc/crontab')},
      'installed_debian_packages':package_rows, 'docker':docker, 'paths':paths,
      'static_code':static, 'last_user_reported_release':BASELINE_RELEASE,
      'application_health':{'path':'/api/health','ok':health_ok},
      'gaps':sorted(set(q.gaps + ([] if root else ['ROOT_REQUIRED_FOR_COMPLETE_INVENTORY']))),
      'unverified':[
        'No consistent database snapshot or backup has been taken.',
        'External volumes, remote databases and provider-side integrations need owner review.',
        'User unit FILES inventoried; live user-manager state and rootless containers not queried.',
        'No environment values, credentials, personal task data or auth identities were opened.',
        'New server access, OS, architecture, disk capacity and final HTTPS domain not verified.',
        'No source write freeze, transfer, target restore, service startup or DNS cutover performed.',
      ],
      'backup_created':False, 'migration_performed':False, 'production_changed':False,
    }


def save_report(report, base='/var/tmp'):
    directory = Path(tempfile.mkdtemp(prefix='dvizh-migration-', dir=base))
    path = directory / 'inventory.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(report, out, ensure_ascii=True, indent=2); out.write('\n')
    # Make the metadata report retrievable by the invoking owner, not world-readable.
    if os.geteuid() == 0 and os.environ.get('SUDO_UID','').isdigit():
        uid = int(os.environ['SUDO_UID'])
        if uid > 0:
            try:
                gid = pwd.getpwuid(uid).pw_gid
                os.chown(path, uid, gid); os.chown(directory, uid, gid)
            except KeyError:
                pass
    return path


def brief(report, path):
    gb = lambda n: 'unknown' if n is None else f'{n / 1024**3:.2f} GiB'
    lines = ['DVIZH SERVER MOVE / INVENTORY ONLY',
      'OS: ' + str(report['os']), 'ARCH: ' + report['architecture'],
      'RAM: ' + gb(report['memory_bytes']),
      'DISK used/free: ' + gb(report['root_disk']['used']) + ' / ' + gb(report['root_disk']['free']),
      'ROOT: ' + str(report['root_inventory']),
      'APP /api/health: ' + str(report['application_health']['ok']), 'DATA ROOTS:']
    lines.extend('  '+r['path']+' '+gb(r['allocated_bytes']) for r in report['directory_sizes_non_recursive_mounts'])
    lines.append('CUSTOM / DVIZH UNITS:')
    lines.extend('  '+u.get('Id','?')+' '+u.get('ActiveState','unknown')+' user='+u.get('User','root')
                 for u in report['custom_unit_properties'])
    lines.append('USER SERVICES / HERMES:')
    for h in report['home_metadata']:
        lines.append('  '+h['user']+' hermes='+str(h['hermes_dir']['present'])+' linger='+str(h['linger'])+
                     ' units='+str(h['user_unit_files']))
    lines.append('DOCKER CONTAINERS: '+str(len(report['docker']['containers'])))
    for c in report['docker']['containers']:
        lines.append('  '+str(c.get('name','?'))+' '+str(c.get('status','unknown'))+' mounts='+str(len(c.get('mounts',[]))))
    lines.append('STATIC MATCH LAST RELEASE:')
    lines.extend('  '+Path(s['path']).name+' '+str(s.get('matches_last_reported_release'))
                 for s in report['static_code'] if Path(s['path']).name in EXPECTED)
    lines.extend(['GAPS: '+str(report['gaps']), 'REPORT: '+str(path),
      'NOT A BACKUP. No transfer, source stop, target restore or DNS change.',
      'Review inventory.json for mounts, packages, cron and unverified items.'])
    return '\n'.join(printable(line) for line in lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print metadata JSON; no report file.')
    args = parser.parse_args()
    if os.geteuid() != 0:
        print('Run from the owner shell with sudo; no application changes are made.', file=sys.stderr)
        return 2
    report = collect()
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        path = save_report(report)
        print(brief(report, path))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
