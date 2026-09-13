#!/usr/bin/env python3
"""Read-only DVIZH daily-update preflight. Does not install or read user state."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.request

VERSION = '2026.09.14-daily-preflight.1'
MAX_BYTES = 2_000_000
TARGETS = {
 'ai-home-v2.js': ('075cea330640ab94da266365a87c81c769e0d467','e449ac6a7abdc5eda6bba09b7fb86e0da72bf16854d5e8b6003a755cd602a1c3'),
 'sync.js': ('d1a935c1451d58b5671bc3553db0864a5caf2746','d474da15914297cdcf064d50eb471172854f051c2bc5c645f2eb0b2a9345569f'),
 'index.html': ('271d72f3f6b5021240b32ee1a90f76d56de4ddbc','656d6062346ae6b651eeaec2119fd800144e0854c9c55aced05b2f90edbabb43'),
 'manual.html': ('c94da18a1d5e2b87be7ddb09e4cb4548504e1928','24161668ce78443cd83e7b0f09bff7ea7ff80a2277d63c24443e744c2debc868'),
}


def fingerprint(path: Path) -> dict:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                return {'error': 'unsupported_file'}
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = stream.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES: return {'error':'too_large'}
        finally: os.close(fd)
        digest = hashlib.sha256(data).hexdigest()
        result = {'sha256':digest,'blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),
                  'bytes':len(data),'uid':info.st_uid,'gid':info.st_gid,'mode':oct(stat.S_IMODE(info.st_mode)), 'links':info.st_nlink}
        match = re.search(rb'^VERSION\s*=\s*["\']([A-Za-z0-9._-]{1,100})["\']',data,re.M)
        if match: result['version']=match.group(1).decode('ascii')
        return result
    except OSError as exc: return {'error':type(exc).__name__}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def http(path: str) -> dict:
    # Fixed loopback origin only. No cookies, credentials, proxy or redirects.
    request = urllib.request.Request('http://127.0.0.1:8000'+path, headers={'Cache-Control':'no-cache'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with opener.open(request,timeout=8) as response:
            data = response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES: return {'status':response.status,'error':'too_large'}
            result={'status':response.status,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
            if path.startswith('/api/ai-home/health'):
                try:
                    value=json.loads(data)
                    if isinstance(value,dict) and type(value.get('ok')) is bool: result['reported_ok']=value['ok']
                except (ValueError,UnicodeError): result['error']='not_json'
            return result
    except urllib.error.HTTPError as exc: return {'status':exc.code}
    except (OSError,urllib.error.URLError,TimeoutError): return {'error':'unavailable'}


def main() -> None:
    result={'preflight_version':VERSION,'read_only':True,'installed_by_this_command':False,
            'host':socket.gethostname(),'uid':os.geteuid(),'files':{},'services':{},'control_plane':{}}
    for name,(base,candidate) in TARGETS.items():
        row=fingerprint(Path('/opt/dvizh/static')/name)
        row['match']='candidate' if row.get('sha256')==candidate else 'reviewed_baseline' if row.get('blob')==base else 'unknown'
        request_path='/' if name=='index.html' else '/'+name
        row['http']=http(request_path+'?daily_preflight='+str(time.time_ns()))
        row['http_matches_disk']=row.get('sha256') is not None and row['http'].get('sha256')==row['sha256']
        result['files'][name]=row
    for name in ('app.js','boot.js','styles.css','sw.js'):
        result['files'][name]=fingerprint(Path('/opt/dvizh/static')/name)
    result['backend']=fingerprint(Path('/opt/dvizh/server.py'))
    result['backend']['matches_tested_contract']=result['backend'].get('sha256')=='ac30e07d5abc77a09830218e6cf7d290e46f6d1b719789a7fb7db7fba2854899'
    for file in ('/usr/local/bin/dvizhautopilot','/usr/local/sbin/dvizhrelease','/usr/local/sbin/dvizhgitpush'):
        result['control_plane'][Path(file).name]=fingerprint(Path(file))
    for service in ('dvizh.service','dvizh-ai-home.service','dvizh-ai-approval.service'):
        try:
            cp=subprocess.run(['/usr/bin/systemctl','is-active',service],capture_output=True,text=True,timeout=8)
            value=cp.stdout.strip()
            result['services'][service]=value if value in {'active','inactive','failed','activating','deactivating','unknown'} else 'unknown'
        except (OSError,subprocess.TimeoutExpired): result['services'][service]='unavailable'
    result['ai_health']=http('/api/ai-home/health')
    result['candidate_inputs_match']=all(result['files'][n]['match'] in {'candidate','reviewed_baseline'} and result['files'][n]['http_matches_disk'] for n in TARGETS) and result['backend']['matches_tested_contract']
    result['not_verified']=['release authorization','pending release transaction','full AI semantics','phone microphone','native device smoke']
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
