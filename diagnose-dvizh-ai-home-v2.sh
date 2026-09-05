#!/usr/bin/env bash
set -Eeuo pipefail

VERSION="2026.09.06-ai-home-v2-live-diagnostics.1"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Запусти через sudo: диагностика только читает состояние и делает короткий probe к Hermes." >&2
  exit 1
fi

for tool in systemctl journalctl python3 curl; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Не найден обязательный инструмент: $tool" >&2; exit 1; }
done

echo "=== DVIZH AI Home v2 live diagnostics ==="
echo "Version: $VERSION"
date -u '+UTC: %Y-%m-%dT%H:%M:%SZ'
echo

for unit in dvizh.service dvizh-auth.service dvizh-ai-home.service; do
  echo "--- $unit ---"
  systemctl is-active "$unit" || true
  systemctl show "$unit" --no-pager -p ActiveState -p SubState -p MainPID -p NRestarts -p ActiveEnterTimestamp -p ExecMainStartTimestamp || true
  echo
done

echo "--- DVIZH /api/health ---"
curl -fsS --max-time 8 http://127.0.0.1:8000/api/health || echo "HEALTH_FAILED"
echo -e '\n'

python3 <<'PY'
from __future__ import annotations
import json, shlex, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

IDENTITY = Path('/var/lib/dvizh/auth-identity.json')
STATUS = Path('/var/lib/dvizh/ai-home-status.json')
ENV = Path('/etc/dvizh/ai-home.env')


def recursive(value, keys):
    if isinstance(value, dict):
        for key in keys:
            v = value.get(key)
            if isinstance(v, (str, int)) and str(v).strip():
                return str(v).strip()
        for v in value.values():
            found = recursive(v, keys)
            if found:
                return found
    elif isinstance(value, list):
        for v in value:
            found = recursive(v, keys)
            if found:
                return found
    return ''


def load_env(path: Path):
    out = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        try:
            parts = shlex.split(value, posix=True)
            out[key] = parts[0] if parts else ''
        except Exception:
            out[key] = value.strip().strip('"').strip("'")
    return out


def age_seconds(value):
    if value in (None, ''):
        return None
    if isinstance(value, (int, float)):
        return time.time() - float(value)
    raw = str(value).strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
    except Exception:
        return None

print('--- bridge status file ---')
if STATUS.is_file():
    try:
        data = json.loads(STATUS.read_text(encoding='utf-8'))
        safe = {k: data.get(k) for k in ('version','at','ok','busy','processed','model','error') if k in data}
        print(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True))
        age = age_seconds(data.get('at'))
        print('status_age_seconds=', None if age is None else round(age, 1))
    except Exception as exc:
        print('STATUS_PARSE_ERROR:', type(exc).__name__, str(exc))
else:
    print('STATUS_MISSING')
print()

env = load_env(ENV)
web_api = (env.get('DVIZH_WEB_API') or 'http://127.0.0.1:8000').rstrip('/')

print('--- current AI Home request state (content redacted) ---')
try:
    ident = json.loads(IDENTITY.read_text(encoding='utf-8'))
    user_id = recursive(ident, ('DVIZH_WEB_USER_ID','user_id','userId','web_user_id','webUserId','subject','uid','id'))
    email = recursive(ident, ('DVIZH_WEB_USER_EMAIL','email','user_email','userEmail')) or 'local-account@dvizh.invalid'
    if not user_id:
        raise RuntimeError('identity has no user id')
    req = urllib.request.Request(web_api + '/api/state', headers={
        'Accept':'application/json',
        'X-ExeDev-UserID': user_id,
        'X-ExeDev-Email': email,
        'User-Agent':'DVIZH-AI-Home-Diagnostics/1',
    })
    with urllib.request.urlopen(req, timeout=8) as response:
        payload = json.loads(response.read().decode('utf-8'))
    state = payload.get('state') if isinstance(payload, dict) else {}
    print('revision=', payload.get('revision'))
    print('aiHomeStatus=', json.dumps(state.get('aiHomeStatus'), ensure_ascii=False))
    rows = state.get('aiHomeRequests') if isinstance(state.get('aiHomeRequests'), list) else []
    print('request_count=', len(rows))
    for row in rows[-6:]:
        if not isinstance(row, dict):
            continue
        stamp = row.get('startedAtEpoch') or row.get('startedAt') or row.get('createdAt')
        age = age_seconds(stamp)
        summary = {
            'id': str(row.get('id') or '')[:80],
            'status': row.get('status'),
            'createdAt': row.get('createdAt'),
            'startedAt': row.get('startedAt'),
            'finishedAt': row.get('finishedAt'),
            'ageSeconds': None if age is None else round(age, 1),
            'error': str(row.get('error') or '')[:180] or None,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
except Exception as exc:
    print('STATE_READ_ERROR:', type(exc).__name__, str(exc))
print()

print('--- direct Hermes chat/completions probe (no DVIZH write) ---')
hermes_api = (env.get('HERMES_API_URL') or 'http://127.0.0.1:8642/v1').rstrip('/')
hermes_key = (env.get('HERMES_API_KEY') or '').strip()
model = (env.get('HERMES_API_MODEL') or 'hermes-agent').strip() or 'hermes-agent'
print('endpoint=', hermes_api + '/chat/completions')
print('model=', model)
print('api_key_configured=', len(hermes_key) >= 20)
if len(hermes_key) < 20:
    print('HERMES_PROBE_SKIPPED: API key missing/too short')
else:
    body = json.dumps({
        'model': model,
        'messages': [
            {'role':'system','content':'Diagnostic probe only. Do not call tools. Reply exactly OK.'},
            {'role':'user','content':'OK?'}
        ],
        'stream': False,
        'temperature': 0,
    }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    request = urllib.request.Request(
        hermes_api + '/chat/completions', data=body, method='POST', headers={
            'Authorization':'Bearer ' + hermes_key,
            'Content-Type':'application/json',
            'Accept':'application/json',
            'User-Agent':'DVIZH-AI-Home-Diagnostics/1',
        })
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
        elapsed = time.monotonic() - started
        result = json.loads(raw.decode('utf-8'))
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '') if isinstance(result, dict) else ''
        if isinstance(content, list):
            content = ' '.join(str(x.get('text') or '') for x in content if isinstance(x, dict))
        print('HERMES_PROBE_OK elapsed_seconds=', round(elapsed, 2), 'response=', str(content).strip()[:120])
    except Exception as exc:
        elapsed = time.monotonic() - started
        print('HERMES_PROBE_ERROR elapsed_seconds=', round(elapsed, 2), type(exc).__name__, str(exc)[:240])
PY

echo
echo "--- dvizh-ai-home.service recent journal ---"
journalctl -u dvizh-ai-home.service --since '-20 min' -n 120 --no-pager -o short-iso || true

echo
echo "=== END DIAGNOSTICS ==="
