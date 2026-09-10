#!/usr/bin/env python3
"""Deterministic offline build from pinned installed sources. Never reads production."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]

def replace_once(text, old, new):
    if text.count(old)!=1: raise ValueError(f'baseline anchor must occur once: {old[:100]!r}')
    return text.replace(old,new,1)

def build():
    for file,pin in json.loads((ROOT/'baseline/pins.json').read_text()).items():
        if hashlib.sha256((ROOT/'baseline'/file).read_bytes()).hexdigest()!=pin['sha256']:
            raise ValueError('baseline pin mismatch: '+file)
    domain=(ROOT/'domain.py').read_text()
    for source,target in [('context.py','dvizh_context.py'),('proposals.py','dvizh_proposals.py'),('proposal_bridge.py','dvizh_proposal_bridge.py')]:
        text=(ROOT/'baseline/helpers'/source).read_text()
        text=text.replace('2026.09.05-hermes-context.1','2026.09.10-hermes-context.health-recovery-v1').replace('2026.09.05-hermes-proposals.1','2026.09.10-hermes-proposals.health-recovery-v1').replace('2026.09.05-ai-approval.1','2026.09.10-ai-approval.health-recovery-v1')
        text=replace_once(text,'VERSION = ', '# Generated Health Recovery domain; source: minimal-ui-v1/health-recovery-v1/domain.py\n'+domain+'\n\nVERSION = ')
        if source=='context.py':
            text=replace_once(text,'    return selected\n', '    if view in {"today", "week", "health"} and "healthRecovery" in state:\n        selected["healthRecovery"] = state["healthRecovery"]\n    return selected\n')
            text=replace_once(text,'    return {\n        "version": VERSION,', '''    health = None
    if view in {"today", "week", "health", "full"} and web.get("ok") and isinstance(web.get("state"), dict):
        stored_timezone = _health_dict(web["state"].get("healthRecovery")).get("timezone")
        health_day = today_key
        if isinstance(stored_timezone, str) and stored_timezone:
            try:
                health_day = datetime.now(timezone.utc).astimezone(_health_zone(stored_timezone)).date().isoformat()
            except (ValueError, KeyError):
                pass
        health = health_summary(web["state"], health_day)
    return {
        **({"health": sanitize(health)} if health is not None else {}),
        "version": VERSION,''')
        else:
            text=replace_once(text,'ALLOWED_ACTIONS = {"task_create", "task_complete", "schedule_move", "day_plan"}', 'ALLOWED_ACTIONS = {"task_create", "task_complete", "schedule_move", "day_plan"} | HEALTH_ACTIONS')
        if source=='proposals.py':
            text=replace_once(text,'    if action == "task_create":','''    if action in HEALTH_ACTIONS:
        try:
            health_validate_payload(action, payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise SystemExit(str(exc)) from exc
        return
    if action == "task_create":''')
            # Preserve installed semantics; add terminal statuses already written by bridge.
            text=replace_once(text, '\n\ndef now_iso()', '\nVISIBLE_STATUSES = {"pending", "rejected", "superseded", "applied", "failed"}\n\ndef now_iso()')
            text=text.replace('choices=["pending", "rejected", "superseded"]','choices=sorted(VISIBLE_STATUSES)')
        if source=='proposal_bridge.py':
            text=replace_once(text,'def apply_state_action(','''def state_health_action(state, proposal):
    proposal_id = str(proposal.get("id") or "")
    if not proposal_id:
        raise BridgeError("proposal id required")
    if proposal_id in state.get("healthRecovery", {}).get("appliedProposals", {}):
        return "health already applied:" + proposal_id
    payload = copy.deepcopy(proposal.get("payload") or {})
    payload["source"] = "ai"
    try:
        result = health_apply(state, proposal["action"], payload)
    except (ValueError, TypeError, KeyError) as exc:
        raise BridgeError(str(exc)) from exc
    state["healthRecovery"].setdefault("appliedProposals", {})[proposal_id] = iso()
    return "health saved:" + result


def apply_state_action(''')
            text=replace_once(text,'    if decision == "reject":', '    if action in HEALTH_ACTIONS and decision == "approve" and (type(command.get("healthVersion")) not in (int, float) or command.get("healthVersion") != 1):\n        ack("Обнови Manual: для здоровья нужно подтверждение точных значений.")\n        return True\n\n    if decision == "reject":')
            text=replace_once(text,'    if action not in handlers:', '    handlers.update({action: state_health_action for action in HEALTH_ACTIONS})\n    if action not in handlers:')
        (REPO/'hermes-control-v1'/target).write_text(text)


    ai=(ROOT/'baseline/helpers/ai_home_bridge.py').read_text().replace('2026.09.05-ai-home.1','2026.09.10-ai-home.health-recovery-v1')
    ai=replace_once(ai,'\n\nclass BridgeError', '\nSYSTEM_PROMPT += '+repr((ROOT/'AI-PROMPT.txt').read_text())+'\n\nclass BridgeError')
    (REPO/'ai-home-v2/ai_home_bridge.py').write_text(ai)
    dist=ROOT/'dist'; dist.mkdir(exist_ok=True)
    for path in (ROOT/'baseline/static').iterdir():
        (dist/path.name).write_bytes(path.read_bytes())
    sync=(dist/'sync.js').read_text()
    start=sync.index('  function reconcile(')
    end=sync.index('  // One-time upgrade:',start)
    sync=sync[:start]+(ROOT/'sync-health.js').read_text()+sync[start:end].replace('reconcile(', 'reconcileJSON(')+sync[end:]
    sync=replace_once(sync,'    state.__sync = sync;\n    return state;', '    state.__sync = sync;\n    return normalizeHealthSleep(state);')
    (dist/'sync.js').write_text(sync)
    app=(dist/'app.js').read_text()
    # Recursing into inherited __proto__/constructor reaches global prototypes.
    # Keep arbitrary remote JSON fields as own data properties, including arrays.
    app=replace_once(app, "if (!(key in next)) delete target[key];", "if (!Object.hasOwn(next, key)) delete target[key];")
    app=replace_once(app, "      const old = target[key];", "      const old = Object.hasOwn(target, key) ? target[key] : undefined;")
    app=replace_once(app, "      } else target[key] = value;", "      } else Object.defineProperty(target, key, {value, writable:true, enumerable:true, configurable:true});")
    app=replace_once(app,'  init();\n})();', (ROOT/'domain.js').read_text()+'\n'+(ROOT/'ui.js').read_text()+'\n  init();\n  initHealth();\n})();')
    app=replace_once(app,"      day_plan: 'План дня'", "      health_sleep: 'Сон', health_checkin: 'Самочувствие', health_supplement_schedule: 'Расписание добавок', health_supplement_mark: 'Отметка добавки',\n      day_plan: 'План дня'")
    app=replace_once(app, '  function aiApprovalDetail(proposal) {', '  function aiApprovalDetail(proposal) {\n    if (proposal.action?.startsWith("health_")) return healthProposalDetail(proposal);')
    app=replace_once(app,"if (view === 'home') { renderHeader();", "if (view === 'home') { renderHealthToday(); renderHeader();")
    app=replace_once(app, "    if (document.body && typeof MutationObserver !== 'undefined') {\n      new MutationObserver(queueEnsure).observe(document.body, {childList:true, subtree:true});\n    }", "    document.addEventListener('click', ensureStructure);")
    start=app.index('  function queueEnsure() {')
    end=app.index('  function boot() {',start)
    app=app[:start]+app[end:]
    app=app.replace('  let observerQueued = false;\n','')
    app=replace_once(app,'    state.aiProposalCommands = [...commands.slice(-19), command];', '    if (state.aiProposals?.some(p => String(p.id) === String(proposalId) && p.action?.startsWith("health_"))) command.healthVersion = 1;\n    state.aiProposalCommands = [...commands.slice(-19), command];')
    (dist/'app.js').write_text(app)
    html=(dist/'manual.html').read_text()
    html=replace_once(html,'</head>','<style id="health-recovery-v1">'+(ROOT/'health.css').read_text()+'</style>\n</head>')
    html=replace_once(html,'      <section class="view" id="view-settings" data-view="settings">','      <section class="view" id="view-settings" data-view="settings">\n<button type="button" id="healthOpen" disabled>Здоровье и восстановление</button>\n'+(ROOT/'health.html').read_text())
    html=replace_once(html,'      <section class="view is-active" id="view-home" data-view="home">','      <section class="view is-active" id="view-home" data-view="home">\n<div id="healthToday"></div>')
    nav='<details class="health-more"><summary>Ещё</summary><nav aria-label="Разделы Manual">'+''.join(f'<button type="button" data-nav="{key}">{label}</button>' for key,label in [('home','Сейчас'),('tasks','Задачи'),('focus','Фокус'),('week','Неделя'),('training','Тренировки и Jump'),('social','Соцсети'),('proof','Факты'),('settings','Настройки')])+'<button type="button" data-open-health disabled>Здоровье</button></nav></details>'
    html=replace_once(html,'  </header>\n\n  <div class="app-shell">','    '+nav+'\n  </header>\n\n  <div class="app-shell">')
    (dist/'manual.html').write_text(html)
    autopilot=REPO/'.autopilot';autopilot.mkdir(exist_ok=True)
    mappings=[('dvizh_proposal_bridge.py','/opt/dvizh-ai-approval/proposal_bridge.py','python-syntax-service'),('dvizh_context.py','/usr/local/libexec/dvizh-context','python-syntax'),('dvizh_proposals.py','/usr/local/libexec/dvizh-proposals','python-syntax')]
    privileged={'schema':1,'name':'health-recovery-v1-ai-integration','operations':[], 'restarts':['dvizh-ai-approval.service'],'restart_reason':'Load additive typed health actions in the existing authenticated approval bridge; preserve legacy handlers and CAS.'}
    for filename,target,verification in mappings:
        source='hermes-control-v1/'+filename
        privileged['operations'].append({'source':source,'target':target,'sha256':hashlib.sha256((REPO/source).read_bytes()).hexdigest(),'release_class':'ai-integration-privileged','required_owner':'root:root','required_mode':'0755','verification':verification})
    frontend={'schema':1,'name':'health-recovery-v1-manual','operations':[{'source':'minimal-ui-v1/health-recovery-v1/dist/'+file,'target':'/opt/dvizh/static/'+file,'http_path':'/'+file} for file in ['app.js','manual.html','sync.js']], 'restarts':[]}
    ai_manifest={'schema':1,'name':'health-recovery-v1-ai-home','operations':[{'source':'ai-home-v2/ai_home_bridge.py','target':'/opt/dvizh-ai-home/ai_home_bridge.py'}], 'restarts':['dvizh-ai-home.service']}
    for name,manifest in [('health-recovery-privileged.json',privileged),('health-recovery-frontend.json',frontend),('health-recovery-ai-home.json',ai_manifest)]:
        (autopilot/name).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__': build()
