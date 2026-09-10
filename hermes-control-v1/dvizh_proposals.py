#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Generated Health Recovery domain; source: minimal-ui-v1/health-recovery-v1/domain.py
"""Health Recovery v1. Pure JSON operations, embedded into allowlisted helpers by build.py."""
import copy as _hc
import re as _hr
from datetime import date as _hd, datetime as _hdt, timedelta as _htd, timezone as _htz
from zoneinfo import ZoneInfo as _hzone, available_timezones as _hzones

# Case-insensitive IANA names; exclude host-local/pseudo zones unavailable in Intl.
_HEALTH_ZONES = {z.lower(): z for z in _hzones() if z not in ("Factory", "localtime")}
def _health_zone(value):
    if not isinstance(value,str) or value.lower() not in _HEALTH_ZONES:
        raise ValueError("invalid IANA timezone")
    return _hzone(_HEALTH_ZONES[value.lower()])

HEALTH_ACTIONS = {'health_sleep', 'health_checkin', 'health_supplement_schedule', 'health_supplement_mark'}
HEALTH_RATINGS = ('energy', 'mood', 'stress', 'soreness', 'wellbeing')

def _health_day(value):
    if not isinstance(value, str) or not _hr.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise ValueError('day must be YYYY-MM-DD (local wake day for sleep)')
    return _hd.fromisoformat(value)

def _health_number(value, low, high):
    if type(value) not in (int, float) or not low <= value <= high:
        raise ValueError(f'number must be {low}..{high}')
    return int(value) if int(value)==value else value

def _health_rating(value):
    if type(value) not in (int,float) or not 1 <= value <= 5 or int(value)!=value:
        raise ValueError('rating must be an integer 1..5')
    return int(value)

def _health_text(value, limit=1000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'text must be at most {limit} characters')
    # Frozen Python/ECMAScript whitespace union, identical to domain.js.
    return value.strip('\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff')

def _health_clock(value):
    if not isinstance(value, str) or not _hr.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', value):
        raise ValueError('time must be explicit HH:MM')
    h,m=map(int,value.split(':'))
    return h*60+m

def _health_id(value):
    if not isinstance(value,str) or value in ('__proto__','constructor','prototype') or not _hr.fullmatch(r'[A-Za-z0-9_-]{1,80}',value): raise ValueError('stable id required (letters, numbers, underscore, hyphen)')
    return value

def _health_safe_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('__proto__', 'constructor', 'prototype'):
                raise ValueError('unsafe object key')
            _health_safe_keys(child)
    elif isinstance(value, list):
        for child in value: _health_safe_keys(child)

def health_apply(state, action, payload):
    if action not in HEALTH_ACTIONS or not isinstance(payload, dict):
        raise ValueError('unsupported health action')
    _health_safe_keys(payload)
    p=_hc.deepcopy(payload)
    day=_health_day(p.get('day')).isoformat()
    current=state.get('healthRecovery', {})
    if not isinstance(current,dict) or type(current.get('version',1)) not in (int,float) or current.get('version',1)!=1:
        raise ValueError('unsupported healthRecovery version; update client')
    domain=_hc.deepcopy(current)
    tz=p.get('timezone',domain.get('timezone'))
    if not isinstance(tz,str): raise ValueError('explicit IANA timezone required')
    try: _health_zone(tz)
    except Exception as exc: raise ValueError('invalid IANA timezone') from exc
    source=p.get('source','ai')
    if source not in ('manual','ai'): raise ValueError('source must be manual or ai')
    common={'day':day,'timezone':tz,'source':source,'updatedAt':_hdt.now(_htz.utc).isoformat()}
    if 'note' in p: common['note']=_health_text(p['note'])
    if action=='health_sleep':
        allowed={'day','timezone','source','note','start','end','durationMinutes','quality'}
        if set(p)-allowed: raise ValueError('unsupported sleep fields')
        rows=domain.setdefault('sleep',{})
        row={**rows.get(day,{}),**common}
        if 'quality' in p: row['quality']=_health_rating(p['quality'])
        if 'start' in p or 'end' in p:
            start=p.get('start',row.get('start')); end=p.get('end',row.get('end'))
            a,b=_health_clock(start),_health_clock(end)
            minutes=(b-a)%1440
            if not minutes: raise ValueError('equal times are ambiguous; report duration')
            if 'durationMinutes' in p: raise ValueError('use times OR reported duration')
            row.update(start=start,end=end,startDay=(_hd.fromisoformat(day)-_htd(days=int(a>b))).isoformat(),durationMinutes=minutes,durationKind='clock')
        elif 'durationMinutes' in p:
            row['durationMinutes']=_health_number(p['durationMinutes'],1,1440)
            row['durationKind']='reported'
            for key in ('start','end','startDay'): row.pop(key,None)
        _health_derive_sleep(row,day)
        if 'durationMinutes' not in row: raise ValueError('sleep requires times or reported duration')
        rows[day]=row
    elif action=='health_checkin':
        if set(p)-{'day','timezone','source','note',*HEALTH_RATINGS}: raise ValueError('unsupported check-in fields')
        if not set(p)&{'note',*HEALTH_RATINGS}: raise ValueError('check-in is empty')
        row={**domain.setdefault('checkins',{}).get(day,{}),**common}
        for key in HEALTH_RATINGS:
            if key in p: row[key]=_health_rating(p[key])
        domain['checkins'][day]=row
    elif action=='health_supplement_schedule':
        if set(p)-{'day','timezone','source','note','id','name','dose','slots','weekdays','enabled','update'}: raise ValueError('unsupported schedule fields')
        ident=_health_id(p.get('id'))
        rows=domain.setdefault('schedules',{})
        old=rows.get(ident,{})
        if 'update' in p and type(p['update']) is not bool: raise ValueError('update must be boolean')
        if p.get('update') and not old: raise ValueError('schedule to update not found')
        row={**old,**common,**{k:v for k,v in p.items() if k in ('name','dose','slots','weekdays','enabled')},'id':ident}
        for key in ('name','dose'):
            row[key]=_health_text(row.get(key),240)
            if not row[key]: raise ValueError('name and user-provided dose required')
        slots=row.get('slots')
        if not isinstance(slots,list) or not 1<=len(slots)<=12: raise ValueError('explicit time slots required')
        seen=set()
        for slot in slots:
            if not isinstance(slot,dict): raise ValueError('invalid slot')
            sid=_health_id(slot.get('id')); _health_clock(slot.get('time'))
            if sid in seen: raise ValueError('duplicate slot id')
            seen.add(sid)
        # Preserve future per-slot fields when editing known fields.
        old_slots={s['id']:s for s in old.get('slots',[])}
        row['slots']=[{**old_slots.get(s['id'],{}),**s} for s in slots]
        days=row.get('weekdays')
        if not isinstance(days,list) or not days or any(type(d) not in (int,float) or not 0<=d<=6 or int(d)!=d for d in days) or len(set(days))!=len(days): raise ValueError('weekdays are unique Monday=0..Sunday=6')
        if type(row.get('enabled')) is not bool: raise ValueError('enabled must be boolean')
        rows[ident]=row
    elif action=='health_supplement_mark':
        if set(p)-{'day','timezone','source','note','scheduleId','slotId','status'}: raise ValueError('unsupported intake fields')
        sid=_health_id(p.get('scheduleId')); slotid=_health_id(p.get('slotId'))
        schedule=domain.get('schedules',{}).get(sid)
        if not schedule or not schedule.get('enabled') or _hd.fromisoformat(day).weekday() not in schedule['weekdays']: raise ValueError('schedule not enabled for this day')
        slot=next((s for s in schedule['slots'] if s['id']==slotid),None)
        if not slot: raise ValueError('slot not found; clarify which slot')
        status=p.get('status')
        if status not in ('taken','skipped','pending'): raise ValueError('invalid intake status')
        ident=f'{day}/{sid}/{slotid}'
        rows=domain.setdefault('intakes',{})
        old=rows.get(ident,{})
        if old.get('status')==status and ('note' not in p or p['note']==old.get('note')): return ident
        rows[ident]={**old,**common,'id':ident,'scheduleId':sid,'slotId':slotid,'status':status,
            'snapshot':old.get('snapshot') or {'name':schedule['name'],'dose':schedule['dose'],'time':slot['time'],'timezone':schedule['timezone']}}
    domain.update(version=1,timezone=tz)
    state['healthRecovery']=domain
    return day

def _health_dict(value):
    return value if isinstance(value, dict) else {}

def _health_derive_sleep(row, day):
    # Older clients can persist a stale cache; clocks remain authoritative.
    if row.get('durationKind')=='reported':
        for key in ('start','end','startDay'): row.pop(key,None)
    elif row.get('durationKind')=='clock' or ('start' in row and 'end' in row and 'durationKind' not in row):
        try:
            a,b=_health_clock(row.get('start')),_health_clock(row.get('end'))
            minutes=(b-a)%1440
            if not minutes: raise ValueError('ambiguous clocks')
            row['startDay']=(_health_day(day)-_htd(days=int(a>b))).isoformat()
            row['durationMinutes']=minutes
        except (ValueError,TypeError):
            row.pop('durationMinutes',None)
            row.pop('startDay',None)
    return row

def _health_summary_domain(value, day):
    domain=_hc.deepcopy(_health_dict(value))
    if type(domain.get('version',1)) not in (int,float) or domain.get('version',1)!=1: return {}
    def valid_day(value):
        try: return _health_day(value).isoformat()<=day
        except (ValueError,TypeError): return False
    for kind in ('sleep','checkins'):
        rows={k:v for k,v in _health_dict(domain.get(kind)).items() if valid_day(k) and isinstance(v,dict)}
        for key,row in rows.items():
            if kind=='sleep': _health_derive_sleep(row,key)
            for key in (('durationMinutes','quality') if kind=='sleep' else HEALTH_RATINGS):
                if key not in row: continue
                try:
                    if key=='durationMinutes': row[key]=_health_number(row[key],1,1440)
                    else: row[key]=_health_rating(row[key])
                except ValueError: row.pop(key)
        domain[kind]={k:v for k,v in rows.items() if 'durationMinutes' in v} if kind=='sleep' else rows
    schedules={}
    for sid,row in _health_dict(domain.get('schedules')).items():
        if not isinstance(row,dict): continue
        try:
            _health_id(sid)
            if type(row.get('enabled')) is not bool or not isinstance(row.get('weekdays'),list) or any(type(d) not in (int,float) or not 0<=d<=6 or int(d)!=d for d in row['weekdays']): continue
            if any(not isinstance(row.get(k),str) for k in ('name','dose','timezone')): continue
            if not isinstance(row.get('slots'),list): continue
            for slot in row['slots']:
                _health_id(_health_dict(slot).get('id')); _health_clock(slot.get('time'))
        except (ValueError,TypeError): continue
        schedules[sid]=row
    domain['schedules']=schedules
    domain['intakes']={k:r for k,r in _health_dict(domain.get('intakes')).items() if isinstance(r,dict) and isinstance(r.get('id'),str) and valid_day(r.get('day')) and r.get('status') in ('pending','taken','skipped') and isinstance(r.get('snapshot'),dict)}
    return domain

def health_summary(state, day):
    today=_health_day(day)
    domain=_health_summary_domain(state.get('healthRecovery'), day)
    rows=domain.get('sleep') or {}
    days=sorted(k for k in rows if k<=day)
    week=[rows[k]['durationMinutes'] for k in days if (today-_health_day(k)).days<7 and type(rows[k].get('durationMinutes')) in (int,float)]
    checkins=domain.get('checkins') or {}
    checkin=checkins.get(day,{})
    sleep=rows.get(day,{})
    factors=[]
    if not sleep: factors.append('stale sleep' if days else 'missing sleep')
    previous=sorted(k for k in checkins if k<day)
    if not checkin: factors.append('stale check-in' if previous else 'missing check-in')
    for key in HEALTH_RATINGS:
        if key not in checkin: factors.append('missing '+key)
    low=False
    if sleep:
        factors.append('sleep '+str(sleep.get('durationMinutes'))+' minutes (under 360 lowers recovery)')
        low=sleep.get('durationMinutes',0)<360 or sleep.get('quality',3)<=2
    for key in HEALTH_RATINGS:
        if key in checkin:
            factors.append(key+' '+str(checkin[key])+'/5')
            low=low or (checkin[key]>=4 if key in ('stress','soreness') else checkin[key]<=2)
    has_ratings=any(k in checkin for k in HEALTH_RATINGS)
    level='insufficient_data' if not sleep or not has_ratings else 'low' if low else 'high' if sleep.get('durationMinutes',0)>=420 and checkin.get('energy',0)>=4 and checkin.get('wellbeing',0)>=4 else 'normal'
    factors.append('Training readiness uses its existing 0–3 scale; no conversion. Review training and Jump context separately.')
    context={}
    for label, readiness in [('training',_health_dict(state.get('trainingHub')).get('readiness')),('jump',_health_dict(_health_dict(state.get('jumpLab')).get('today')).get('readiness'))]:
        recorded_day=_health_dict(readiness).get('localDate') or _health_dict(readiness).get('day')
        freshness='missing' if not readiness else 'undated' if not recorded_day else 'current' if recorded_day==day else 'stale'
        context[label]={'readiness':readiness,'freshness':freshness}
        factors.append(label+' context '+freshness)
    today_slots=[]
    for sid,schedule in (domain.get('schedules') or {}).items():
        if not schedule.get('enabled') or today.weekday() not in schedule.get('weekdays',[]): continue
        for slot in schedule.get('slots',[]):
            ident=f"{day}/{sid}/{slot['id']}"
            existing=(domain.get('intakes') or {}).get(ident)
            today_slots.append(existing or {'id':ident,'day':day,'scheduleId':sid,'slotId':slot['id'],'status':'pending','snapshot':{'name':schedule['name'],'dose':schedule['dose'],'time':slot['time'],'timezone':schedule['timezone']}})
    return {'day':day,'timezone':domain.get('timezone'),
        'sleep':{'last':rows[days[-1]] if days else None,'mean7Minutes':sum(week)/len(week) if week else None,'recordedDays':len(week),'history':[rows[k] for k in reversed(days)]},
        'checkin':checkin or None,
        'supplements':{'today':today_slots,'remaining':[r for r in today_slots if r['status']=='pending'],'history':sorted((domain.get('intakes') or {}).values(),key=lambda r:r['id'],reverse=True)},
        'readiness':{'level':level,'factors':factors,'clinical':False,'context':context,'trainingReference':state.get('trainingHub'),'jumpReference':state.get('jumpLab')}}

def health_validate_payload(action, payload):
    """Validate proposal syntax without reading state; bridge validates existence on approval."""
    _health_safe_keys(payload)
    p=_hc.deepcopy(payload)
    day=_health_day(p.get('day')).isoformat()
    seed={'healthRecovery':{'version':1,'timezone':p.get('timezone')}}
    if action=='health_sleep' and not set(p)&{'start','end','durationMinutes'}:
        if not set(p)&{'quality','note'}: raise ValueError('empty sleep update')
        seed['healthRecovery']['sleep']={day:{'durationMinutes':1}}
    if action=='health_supplement_schedule':
        if not p.get('update') and not {'id','name','dose','slots','weekdays','enabled'} <= set(p):
            raise ValueError('new schedule needs user dose, exact slots, weekdays and enabled; clarify first')
        # Patch validation does not authorize creation with missing fields.
        seed['healthRecovery']['schedules']={p.get('id',''):{'name':'validation','dose':'validation','slots':[{'id':'validation','time':'00:00'}],'weekdays':[0],'enabled':True}}
    if action=='health_supplement_mark':
        seed['healthRecovery']['schedules']={p.get('scheduleId',''):{'name':'validation','dose':'validation','timezone':p.get('timezone'),'slots':[{'id':p.get('slotId'),'time':'00:00'}],'weekdays':list(range(7)),'enabled':True}}
    health_apply(seed,action,p)


VERSION = "2026.09.10-hermes-proposals.health-recovery-v1"
STORE_DIR = Path(os.environ.get("DVIZH_PROPOSAL_DIR", "/var/lib/dvizh/hermes-proposals"))
STORE = STORE_DIR / "proposals.json"
LOCK = STORE_DIR / ".lock"
ALLOWED_ACTIONS = {"task_create", "task_complete", "schedule_move", "day_plan"} | HEALTH_ACTIONS

VISIBLE_STATUSES = {"pending", "rejected", "superseded", "applied", "failed"}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir() -> None:
    STORE_DIR.mkdir(parents=True, exist_ok=True)


def load_unlocked() -> list[dict[str, Any]]:
    if not STORE.exists():
        return []
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_unlocked(rows: list[dict[str, Any]]) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix="proposals.", suffix=".json", dir=str(STORE_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, STORE)
        os.chmod(STORE, 0o640)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def locked_update(fn):
    ensure_dir()
    with LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        rows = load_unlocked()
        result = fn(rows)
        save_unlocked(rows)
        return result


def parse_payload(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"payload must be valid JSON: {exc}")
    if not isinstance(value, dict):
        raise SystemExit("payload must be a JSON object")
    if len(json.dumps(value, ensure_ascii=False)) > 12000:
        raise SystemExit("payload too large")
    return value


def validate(action: str, payload: dict[str, Any]) -> None:
    if action not in ALLOWED_ACTIONS:
        raise SystemExit("unsupported action")
    if action in HEALTH_ACTIONS:
        try:
            health_validate_payload(action, payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise SystemExit(str(exc)) from exc
        return
    if action == "task_create":
        title = str(payload.get("title") or "").strip()
        if not 1 <= len(title) <= 240:
            raise SystemExit("task_create requires title (1..240 chars)")
    elif action == "task_complete":
        if not str(payload.get("task_id") or "").strip():
            raise SystemExit("task_complete requires task_id")
    elif action == "schedule_move":
        if not str(payload.get("occurrence_id") or "").strip():
            raise SystemExit("schedule_move requires occurrence_id")
        start = str(payload.get("start_local") or "").strip()
        if len(start) != 5 or start[2] != ":":
            raise SystemExit("schedule_move requires start_local HH:MM")
        try:
            hour, minute = map(int, start.split(":"))
        except ValueError:
            raise SystemExit("invalid start_local")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise SystemExit("invalid start_local")
    elif action == "day_plan":
        blocks = payload.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise SystemExit("day_plan requires non-empty blocks array")
        if len(blocks) > 40:
            raise SystemExit("too many day_plan blocks")


def create(action: str, summary: str, payload: dict[str, Any]) -> dict[str, Any]:
    validate(action, payload)
    summary = summary.strip()
    if not 1 <= len(summary) <= 500:
        raise SystemExit("summary must be 1..500 chars")
    proposal = {
        "id": uuid.uuid4().hex[:12],
        "action": action,
        "summary": summary,
        "payload": payload,
        "status": "pending",
        "source": "hermes",
        "created_at_utc": now_iso(),
        "resolved_at_utc": None,
        "resolution": None,
        "version": VERSION,
    }
    def mut(rows):
        rows.append(proposal)
        if len(rows) > 200:
            del rows[:-200]
        return proposal
    return locked_update(mut)


def resolve(proposal_id: str, resolution: str) -> dict[str, Any]:
    if resolution not in {"rejected", "superseded"}:
        raise SystemExit("only rejected/superseded can be resolved by Hermes control")
    def mut(rows):
        for row in rows:
            if row.get("id") == proposal_id:
                if row.get("status") != "pending":
                    raise SystemExit("proposal is not pending")
                row["status"] = resolution
                row["resolution"] = resolution
                row["resolved_at_utc"] = now_iso()
                return row
        raise SystemExit("proposal not found")
    return locked_update(mut)


def list_rows(status: str | None) -> list[dict[str, Any]]:
    ensure_dir()
    rows = load_unlocked()
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows[-50:]


def main() -> int:
    parser = argparse.ArgumentParser(description="DVIZH AI proposal spool (does not apply changes)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_create = sub.add_parser("create")
    p_create.add_argument("action", choices=sorted(ALLOWED_ACTIONS))
    p_create.add_argument("summary")
    p_create.add_argument("payload_json")
    p_list = sub.add_parser("list")
    p_list.add_argument("--status", choices=sorted(VISIBLE_STATUSES))
    p_reject = sub.add_parser("reject")
    p_reject.add_argument("proposal_id")
    sub.add_parser("version")
    args = parser.parse_args()

    if args.cmd == "create":
        out = create(args.action, args.summary, parse_payload(args.payload_json))
    elif args.cmd == "list":
        out = list_rows(args.status)
    elif args.cmd == "reject":
        out = resolve(args.proposal_id, "rejected")
    else:
        print(VERSION)
        return 0
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
