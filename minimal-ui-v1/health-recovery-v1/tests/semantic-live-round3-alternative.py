#!/usr/bin/env python3
"""Inference-only acceptance. Run with python3 -B; no Hermes runtime imports.

All model-selected terminal strings are DATA. Only dispatch() interprets them,
against disposable Python objects. No shell executor or production client exists.
"""
import ast
import builtins
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HERMES = Path('/home/exedev/.hermes/hermes-agent')
ENDPOINT = 'https://llm.int.exe.xyz/v1/responses'
MODEL = 'gpt-5.5'
DAY = '2026-09-10'
PREFIX = 'semantic-live-round3-alternative-'
MAX_STEPS, MAX_TOOLS, MAX_SECONDS = 4, 6, 90
SOURCES = {
    'bridge': ROOT / 'ai-home-v2/ai_home_bridge.py',
    'domain': HERE.parent / 'domain.py',
    'prompt': HERE.parent / 'AI-PROMPT.txt',
    'terminal': HERMES / 'tools/terminal_tool.py',
    'dvizhctl': ROOT / 'hermes-control-v1/dvizhctl',
    'context': ROOT / 'hermes-control-v1/dvizh_context.py',
    'proposals': ROOT / 'hermes-control-v1/dvizh_proposals.py',
}

def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()

def write(name, value):
    path = HERE / (PREFIX + name + '.json')
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

class NoRuntimeImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'run_agent', 'agent', 'hermes_cli', 'model_tools', 'providers', 'plugins', 'tools'}:
            raise RuntimeError('forbidden_runtime_import')

sys.meta_path.insert(0, NoRuntimeImports())

def audit(event, args):
    if event in {'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.fork', 'pty.spawn'}:
        raise RuntimeError('process_execution_forbidden')
    if event == 'urllib.Request' and (args[0] != ENDPOINT or args[3] != 'POST'):
        raise RuntimeError('non_inference_request_forbidden')
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        p = Path(os.fsdecode(args[0])).absolute()
        if p.name == '.env' or p.name in {'auth.json', 'config.yaml', 'config.toml', 'settings.json'} or str(p).startswith(('/var/lib/dvizh', '/root/', '/opt/dvizh')):
            raise RuntimeError('protected_file_access_forbidden')
        flags = args[2] or 0
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            if p.parent != HERE or not p.name.startswith(PREFIX):
                raise RuntimeError('write_outside_semantic_live_forbidden')

sys.addaudithook(audit)

def pure_domain(raw):
    """Compile snapshotted pure source with a restricted import/builtin surface."""
    allowed = {'copy', 're', 'datetime', 'zoneinfo'}
    def imp(name, *args, **kwargs):
        if name not in allowed:
            raise RuntimeError('domain_import_not_allowlisted')
        return builtins.__import__(name, *args, **kwargs)
    safe = {k: v for k, v in vars(builtins).items() if k not in {'open','eval','exec','compile','input','breakpoint'}}
    safe['__import__'] = imp
    ns = {'__builtins__': safe, '__name__': 'semantic_live_domain_snapshot'}
    exec(compile(raw, '<domain snapshot>', 'exec'), ns)
    return ns

def bridge_messages(raw):
    # Execute the actual unchanged AST definitions, excluding module-level auth reads.
    tree = ast.parse(raw)
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id == 'SYSTEM_PROMPT': nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in {'normalize_messages','hermes_messages'}:
            nodes.append(node)
    ns = {'Any': object, 'BridgeError': ValueError}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual bridge definitions>', 'exec'), ns)
    return ns

def terminal_schema(raw):
    tree = ast.parse(raw)
    # Only this documented, nonsecret numeric environment override is resolved.
    try: timeout = int(os.getenv('TERMINAL_MAX_FOREGROUND_TIMEOUT') or '600')
    except ValueError: timeout = 600
    ns = {'FOREGROUND_MAX_TIMEOUT': timeout}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {'TERMINAL_TOOL_DESCRIPTION','TERMINAL_SCHEMA'}:
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual terminal schema>', 'exec'), ns)
    return ns['TERMINAL_SCHEMA']

def fixture(domain, scenario):
    state = {'aiHomeMessages': [], 'tasks': [{'id':'synthetic-task-41','title':'Синтетическая прогулка 17 минут','status':'pending'}],
             'trainingHub': {'readiness': {'localDate': DAY, 'score': 2, 'scale':'0–3'}},
             'jumpLab': {'today': {'readiness': {'day':'2026-09-07','score':1,'scale':'0–3'}}}}
    apply = domain['health_apply']
    for d, minutes in [('2026-09-05',360), ('2026-09-08',420), (DAY,480)]:
        apply(state, 'health_sleep', {'day':d,'timezone':'Europe/Moscow','durationMinutes':minutes})
    apply(state, 'health_checkin', {'day':DAY,'timezone':'Europe/Moscow','energy':3,'note':'Ранее: прогулка у реки.'})
    for ident, name, slot, clock in [('mg_fixture_73','Магний','mg_evening_19','21:13'), ('vd_fixture_29','Витамин D','vd_noon_83','12:17'), ('om_fixture_61','Омега','om_lunch_47','13:19')]:
        slots = [{'id':slot,'time':clock}]
        if scenario == 'multiple_slot_ambiguity' and ident == 'mg_fixture_73':
            slots.append({'id':'mg_morning_97','time':'08:23'})
        apply(state, 'health_supplement_schedule', {'day':DAY,'timezone':'Europe/Moscow','id':ident,'name':name,'dose':'Синтетическая пользовательская доза','slots':slots,'weekdays':list(range(7)),'enabled':True})
    if scenario == 'readiness_reasons':
        del state['healthRecovery']['sleep'][DAY]
        del state['healthRecovery']['checkins'][DAY]
    return state

class Dispatch:
    def __init__(self, domain, state):
        self.domain, self.state = domain, copy.deepcopy(state)
        self.pending, self.calls, self.views = [], [], []

    def dispatch(self, name, args):
        if name != 'terminal' or not isinstance(args, dict): raise ValueError('tool_not_allowed')
        if set(args) - {'command','timeout','background','pty','notify'}: raise ValueError('terminal_option_not_allowed')
        if any(args.get(k, False) is not False for k in ('background','pty','notify')): raise ValueError('non_foreground_mode_forbidden')
        if 'timeout' in args and (type(args['timeout']) is not int or not 1 <= args['timeout'] <= 600): raise ValueError('timeout_not_allowed')
        command = args.get('command')
        if not isinstance(command, str) or len(command) > 16000: raise ValueError('invalid_command')
        tokens = shlex.split(command)  # Parsing only. Never a shell, eval, or subprocess.
        if len(tokens) == 3 and tokens[:2] == ['dvizhctl','context'] and tokens[2] in {'health','week','today'}:
            view = tokens[2]
            self.views.append(view)
            return {'view':view,'today':DAY,'timezone':'Europe/Moscow','read_only':True,
                    'health':self.domain['health_summary'](self.state, DAY),
                    'web':{'ok':True,'revision':73019,'state':copy.deepcopy(self.state)},
                    'telegram':{},'statuses':{},'synthetic':True}
        if len(tokens) == 5 and tokens[:2] == ['dvizhctl','propose'] and tokens[2] in self.domain['HEALTH_ACTIONS']:
            if not self.views: raise ValueError('fresh_context_required')
            if not 1 <= len(tokens[3]) <= 1000 or len(tokens[4]) > 12000: raise ValueError('proposal_too_large')
            payload = json.loads(tokens[4])
            if not isinstance(payload,dict): raise ValueError('payload_object_required')
            self.domain['health_validate_payload'](tokens[2], payload)
            # Validate existence and merge on a COPY; saved synthetic state stays unchanged.
            preview = copy.deepcopy(self.state)
            self.domain['health_apply'](preview, tokens[2], payload)
            item = {'id':f'synthetic-proposal-{len(self.pending)+1}','action':tokens[2],'summary':tokens[3],
                    'payload':payload,'status':'pending','synthetic':True}
            self.pending.append(item)
            return copy.deepcopy(item)
        raise ValueError('command_not_allowlisted')

def negative_checks(domain):
    d = Dispatch(domain, fixture(domain, 'preflight'))
    before = copy.deepcopy(d.state)
    cases = [('unknown_tool','python',{'command':'dvizhctl context health'}),
             ('shell','terminal',{'command':'touch /tmp/semantic-live-forbidden'}),
             ('chain','terminal',{'command':'dvizhctl context health; id'}),
             ('pipe','terminal',{'command':'dvizhctl context health | cat'}),
             ('approve','terminal',{'command':'dvizhctl approve synthetic-proposal-1'}),
             ('apply','terminal',{'command':'dvizhctl apply synthetic-proposal-1'}),
             ('file','terminal',{'command':'cat /var/lib/dvizh/state.json'}),
             ('background','terminal',{'command':'dvizhctl context health','background':True}),
             ('workdir','terminal',{'command':'dvizhctl context health','workdir':'/var/lib/dvizh'}),
             ('unknown_view','terminal',{'command':'dvizhctl context full'})]
    results = []
    for label, name, args in cases:
        try: d.dispatch(name,args)
        except ValueError: results.append({'id':label,'passed':True})
        else: results.append({'id':label,'passed':False})
    d.dispatch('terminal', {'command':'dvizhctl context health'})
    for label, action, payload in [('bad_rating','health_checkin',{'energy':6}),
                                   ('missing_slot','health_supplement_mark',{'scheduleId':'mg_fixture_73','slotId':'invented','status':'taken'})]:
        p = {'day':DAY,'timezone':'Europe/Moscow',**payload}
        try: d.dispatch('terminal',{'command':shlex.join(['dvizhctl','propose',action,'negative test',json.dumps(p)])})
        except ValueError: results.append({'id':label,'passed':True})
        else: results.append({'id':label,'passed':False})
    results.append({'id':'negative_tests_no_pending_or_saved_mutation','passed':not d.pending and d.state == before})
    p = {'day':DAY,'timezone':'Europe/Moscow','durationMinutes':420}
    d.dispatch('terminal',{'command':shlex.join(['dvizhctl','propose','health_sleep','offline harness test',json.dumps(p)])})
    results.append({'id':'valid_offline_proposal_pending_only','passed':len(d.pending)==1 and d.pending[0]['status']=='pending' and d.state==before})
    # These are harness tests, never counted as model proposals or model outputs.
    assert all(r['passed'] for r in results), 'preflight_boundary_failed'
    return results

def check_scenario(row, d, original):
    sid, text = row['id'], row.get('final_text','')
    checks = {'saved_state_unchanged':d.state==original,
              'pending_only':all(x['status']=='pending' for x in d.pending),
              'no_tool_errors':not any('error' in c['result'] for c in d.calls),
              'completed_response':row.get('finish')=='completed'}
    query = sid in {'sleep_week','readiness_reasons','today_summary'}
    clarify = sid in {'multiple_slot_ambiguity','evening_schedule'}
    checks['required_context'] = ('week' in d.views if sid=='sleep_week' else 'today' in d.views if sid=='today_summary' else bool(d.views) if sid=='evening_schedule' else 'health' in d.views)
    checks['proposal_count'] = len(d.pending)==(0 if query or clarify else 1)
    if d.pending:
        p = d.pending[0]['payload']; action = d.pending[0]['action']
        checks['current_day_timezone'] = p.get('day')==DAY and p.get('timezone')=='Europe/Moscow'
        checks['confirmation_language'] = bool(re.search(r'подтверд|подтвержд',text,re.I)) and 'Manual' in text
        expected = 'health_sleep' if sid.startswith('sleep_') else 'health_checkin' if sid.startswith('checkin_') else 'health_supplement_mark'
        checks['typed_action'] = action==expected
        preview = copy.deepcopy(original)
        d.domain['health_apply'](preview,action,p)
        if sid=='sleep_times':
            sleep=preview['healthRecovery']['sleep'][DAY]
            checks['clock_values_overnight'] = p.get('start')=='23:30' and p.get('end')=='07:00' and sleep['durationMinutes']==450 and sleep['startDay']=='2026-09-09'
            checks['no_invented_quality_or_duration'] = 'quality' not in p and 'durationMinutes' not in p
        elif sid=='sleep_duration': checks['duration_only'] = p.get('durationMinutes')==420 and not {'start','end','quality'} & set(p)
        elif sid=='sleep_quality':
            checks['quality_preserves_sleep'] = p.get('quality')==4 and preview['healthRecovery']['sleep'][DAY]['durationMinutes']==480
        elif sid in {'magnesium_taken','vitamind_taken','omega_skip'}:
            expected_slot = {'magnesium_taken':('mg_fixture_73','mg_evening_19','taken'),'vitamind_taken':('vd_fixture_29','vd_noon_83','taken'),'omega_skip':('om_fixture_61','om_lunch_47','skipped')}[sid]
            checks['exact_current_slot_status'] = (p.get('scheduleId'),p.get('slotId'),p.get('status'))==expected_slot
        elif sid.startswith('checkin_'):
            checks['note_preserved'] = 'Ранее: прогулка у реки.' in p.get('note','')
            checks['no_inferred_ratings'] = not (set(p)&set(d.domain['HEALTH_RATINGS']) - ({'energy','stress'} if sid=='checkin_explicit_notes' else set()))
            checks['new_note'] = bool(re.search(r'sore legs|болят ноги|бол[ьи].*ног',p.get('note',''),re.I)) if sid=='checkin_explicit_notes' else bool(re.search(r'feels great|чувствую себя отлично|отличн',p.get('note',''),re.I))
            if sid=='checkin_explicit_notes': checks['explicit_ratings'] = p.get('energy')==2 and p.get('stress')==4
    if clarify:
        checks['asks_clarification'] = '?' in text
        if sid=='evening_schedule': checks['dose_time_weekdays_question'] = all(re.search(pattern,text,re.I) for pattern in [r'доз|сколько',r'врем|час|во сколько',r'дн|ежеднев'])
        else: checks['slot_ambiguity'] = bool(re.search(r'утр|вечер|слот|08:23|21:13',text,re.I))
    if sid=='sleep_week':
        checks['recorded_day_denominator'] = bool(re.search(r'3\s*(?:запис|дн|дня)|три\s*(?:запис|дн)',text,re.I))
        checks['mean_420_minutes'] = bool(re.search(r'420|7\s*(?:ч|час)',text,re.I))
    if sid=='readiness_reasons':
        checks['insufficient_and_stale'] = bool(re.search(r'недостат|insufficient',text,re.I)) and bool(re.search(r'устар|свеж|стар|сегодня.*нет|нет.*сегодня',text,re.I))
        checks['reference_scales'] = bool(re.search(r'0\s*[–—-]\s*3',text)) and bool(re.search(r'Jump|прыж',text,re.I)) and bool(re.search(r'1\s*[–—-]\s*5|/5',text))
    if sid=='today_summary': checks['current_synthetic_task'] = '17' in text and bool(re.search(r'прогул',text,re.I))
    row['assertions'] = checks
    row['status'] = 'PASS' if all(checks.values()) else 'FAIL'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): raise RuntimeError('redirect_forbidden')

def main():
    start = datetime.now(timezone.utc).isoformat()
    # Snapshot at evaluation start, so another agent's subsequent edits cannot mix imports.
    source = {k:p.read_text() for k,p in SOURCES.items()}
    snapshots = {k:{'path':str(SOURCES[k]),'sha256':digest(v),'source':v} for k,v in source.items()}
    write('snapshot',snapshots)
    domain, bridge, schema = pure_domain(source['domain']), bridge_messages(source['bridge']), terminal_schema(source['terminal'])
    tools = [{'type':'function',**schema,'strict':False}]
    assert tools[0]['name']=='terminal' and all(t['type']=='function' for t in tools)
    prior = json.loads((HERE/'semantic-live-evidence.json').read_text())
    evidence = {'started_at':start,'status':'RUNNING','model':MODEL,'endpoint':ENDPOINT,
        'boundary':'Real model tool selection; only bounded synthetic Python dispatch. No production agent or tool execution.',
        'budget':{'max_scenarios':13,'max_steps_per_scenario':MAX_STEPS,'max_tool_calls_per_scenario':MAX_TOOLS,'max_seconds_per_scenario':MAX_SECONDS,'retries':0},
        'source_hashes':{k:v['sha256'] for k,v in snapshots.items()},'terminal_schema':schema,
        'preflight':negative_checks(domain),'counts':{'model_requests':0,'model_responses':0,'production_tool_calls':0,'production_agent_api_calls':0},
        'scenarios':[]}
    write('evidence',evidence)
    if '--preflight-only' in sys.argv:
        evidence['status']='PREFLIGHT_ONLY'
        write('evidence',evidence)
        print(json.dumps({'preflight_checks':len(evidence['preflight']),'model_requests':0}),flush=True)
        return
    # TLS and network happen only here. No Authorization header or placeholder credential.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for case in prior['scenarios'][:13]:
        row = {k:case[k] for k in ('id','synthetic_user_input','required_assertions')}
        row.update(status='RUNNING',requests=[],responses=[],tool_calls=[],pending=[])
        original = fixture(domain,row['id']); d = Dispatch(domain,original)
        row['fixture'] = original
        messages = bridge['hermes_messages']({'aiHomeMessages':[]},{'text':row['synthetic_user_input']})
        row['hermes_messages'] = copy.deepcopy(messages)
        history = messages[:]
        began = time.monotonic()
        evidence['scenarios'].append(row)
        def deadline(signum, frame): raise TimeoutError('scenario_deadline')
        signal.signal(signal.SIGALRM, deadline)
        signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
        try:
            for step in range(MAX_STEPS):
                remaining = MAX_SECONDS - (time.monotonic()-began)
                if remaining <= 0: raise TimeoutError('scenario_deadline')
                payload = {'model':MODEL,'input':history,'tools':tools,'tool_choice':'auto','parallel_tool_calls':False,
                           'store':False,'max_output_tokens':1800,'reasoning':{'effort':'low'}}
                row['requests'].append(copy.deepcopy(payload))
                evidence['counts']['model_requests'] += 1
                write('evidence',evidence)
                req = urllib.request.Request(ENDPOINT,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'},method='POST')
                with opener.open(req,timeout=min(remaining,60)) as response:
                    raw = response.read(2_000_001)
                if len(raw)>2_000_000: raise ValueError('response_too_large')
                result=json.loads(raw)
                row['responses'].append(result)
                evidence['counts']['model_responses'] += 1
                outputs=result.get('output',[])
                if any(x.get('type') not in {'message','reasoning','function_call'} for x in outputs): raise ValueError('unexpected_output_type')
                history.extend(outputs)
                calls=[x for x in outputs if x.get('type')=='function_call']
                if not calls:
                    row['final_text']='\n'.join(c.get('text','') for o in outputs if o.get('type')=='message' for c in o.get('content',[]) if c.get('type')=='output_text')
                    row['finish']=result.get('status')
                    break
                for call in calls:
                    if len(d.calls)>=MAX_TOOLS: raise ValueError('tool_budget_exhausted')
                    try: output=d.dispatch(call.get('name'),json.loads(call.get('arguments','')))
                    except (ValueError,TypeError,KeyError) as exc: output={'error':str(exc),'synthetic':True}
                    record={'model_call':call,'result':output}
                    d.calls.append(record)
                    history.append({'type':'function_call_output','call_id':call['call_id'],'output':json.dumps(output,ensure_ascii=False)})
                write('evidence',evidence)
            else: row['finish']='step_budget_exhausted'
            row['elapsed_seconds']=round(time.monotonic()-began,3)
            check_scenario(row,d,original)
        except Exception as exc:
            # Do not print transport headers, response bodies, URLs, or exception text.
            row.update(status='ERROR',error_type=type(exc).__name__,http_status=getattr(exc,'code',None),elapsed_seconds=round(time.monotonic()-began,3))
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        row['tool_calls']=d.calls; row['pending']=copy.deepcopy(d.pending)
        row['saved_state_unchanged']=d.state==original
        write('evidence',evidence)
        print(row['id'],row['status'],len(row['responses']),flush=True)
    # Revalidate real returned payloads against the current final domain snapshot.
    final_source = {k:p.read_text() for k,p in SOURCES.items()}
    final_domain=pure_domain(final_source['domain'])
    evidence['final_source_hashes']={k:digest(v) for k,v in final_source.items()}
    evidence['source_drift']={k:digest(v)!=digest(source[k]) for k,v in final_source.items()}
    write('final-snapshot',{k:{'path':str(SOURCES[k]),'sha256':digest(v),'source':v} for k,v in final_source.items()})
    for row in evidence['scenarios']:
        results=[]
        for p in row['pending']:
            try:
                final_domain['health_validate_payload'](p['action'],p['payload'])
                preview=copy.deepcopy(row['fixture'])
                final_domain['health_apply'](preview,p['action'],p['payload'])
                results.append({'id':p['id'],'passed':True})
            except Exception as exc: results.append({'id':p['id'],'passed':False,'error_type':type(exc).__name__})
        row['final_payload_revalidation']=results
        if not all(x['passed'] for x in results): row['status']='FAIL'
    evidence['counts'].update({s.lower():sum(r['status']==s for r in evidence['scenarios']) for s in ('PASS','FAIL','ERROR','NOT_RUN')})
    evidence['counts']['synthetic_model_proposals']=sum(len(r['pending']) for r in evidence['scenarios'])
    evidence['counts']['synthetic_model_tool_calls']=sum(len(r['tool_calls']) for r in evidence['scenarios'])
    evidence['status']='COMPLETE'
    evidence['finished_at']=datetime.now(timezone.utc).isoformat()
    write('evidence',evidence)
    print(json.dumps(evidence['counts']),flush=True)

if __name__=='__main__': main()
