#!/usr/bin/env python3
"""Offline review of immutable live evidence; never makes model requests."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import re
import runpy
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
PREFIX='semantic-live-alternative-'
runtime=runpy.run_path(str(HERE/'semantic-live-alternative.py'))
raw_bytes=(HERE/(PREFIX+'evidence.json')).read_bytes()
raw=json.loads(raw_bytes)
assert raw['status']=='COMPLETE'
review=copy.deepcopy(raw)
review['raw_evidence_sha256']=hashlib.sha256(raw_bytes).hexdigest()
review['evaluation_corrections']=[]
for row in review['scenarios']:
    row['original_status']=row['status']
    if row['id']=='sleep_week':
        # Same expected 420 minutes; also recognize clock notation for duration.
        row['assertions']['mean_420_minutes']=row['assertions']['mean_420_minutes'] or bool(re.search(r'Среднее[^\n]*\b7:00\b',row['final_text'],re.I))
        review['evaluation_corrections'].append({'scenario':row['id'],'reason':'Original regex missed the correct 7:00 / ночь mean. No model retry or output alteration.'})
    if row['id']=='evening_schedule':
        # The prior matrix requires clarification, not a context read before clarification.
        row['assertions']['required_context']=True
        text=row['final_text']
        row['assertions']['no_unsupplied_dose_time_examples']=not bool(re.search(r'\b\d+\s*(?:мг|mg)\b|\b\d{1,2}:\d{2}\b',text,re.I))
        review['evaluation_corrections'].append({'scenario':row['id'],'reason':'Removed extra context prerequisite absent from prior matrix. Added its missing no-fabricated-values check. The response offers an illustrative 400 mg / every day / 21:30 schedule; it does not claim these are user facts and creates no proposal, but violates the requested no-unsupplied-values boundary.'})
    if 'assertions' in row: row['status']='PASS' if all(row['assertions'].values()) else 'FAIL'

latest={k:p.read_text() for k,p in runtime['SOURCES'].items()}
domain=runtime['pure_domain'](latest['domain'])
bridge=runtime['bridge_messages'](latest['bridge'])
review['reviewed_at']=datetime.now(timezone.utc).isoformat()
review['review_source_hashes']={k:runtime['digest'](v) for k,v in latest.items()}
review['review_source_drift']={k:runtime['digest'](v)!=raw['source_hashes'][k] for k,v in latest.items()}
review['final_prompt_embedded_exactly']=latest['prompt'] in bridge['SYSTEM_PROMPT']
review['review_revalidation']=[]
for row in review['scenarios']:
    state=copy.deepcopy(row['fixture'])
    for proposal in row['pending']:
        before=copy.deepcopy(state)
        domain['health_validate_payload'](proposal['action'],proposal['payload'])
        preview=copy.deepcopy(state)
        domain['health_apply'](preview,proposal['action'],proposal['payload'])
        assert before==state and proposal['status']=='pending'
        review['review_revalidation'].append({'scenario':row['id'],'proposal_id':proposal['id'],'passed':True})
    expected=bridge['hermes_messages']({'aiHomeMessages':[]},{'text':row['synthetic_user_input']})
    row['messages_match_final_bridge']=expected==row['hermes_messages']
    assert row['messages_match_final_bridge']
review['counts'].update({s.lower():sum(r['status']==s for r in review['scenarios']) for s in ('PASS','FAIL','ERROR','NOT_RUN')})
assert review['counts']['model_requests']==33 and review['counts']['model_responses']==33
assert len(review['review_revalidation'])==8
review['usage_totals']={key:sum(response.get('usage',{}).get(key,0) for row in raw['scenarios'] for response in row['responses']) for key in ('input_tokens','output_tokens','total_tokens')}
# Keep the review compact; the immutable raw file contains every request/response.
for row in review['scenarios']:
    row['raw_evidence_scenario_id']=row['id']
    for key in ('requests','responses','fixture','hermes_messages','tool_calls'):
        row.pop(key,None)
runtime['write']('review',review)
runtime['write']('review-snapshot',{k:{'sha256':runtime['digest'](v),'source':v,'path':str(runtime['SOURCES'][k])} for k,v in latest.items()})
print(json.dumps({'counts':review['counts'],'final_payloads_revalidated':len(review['review_revalidation']),'source_drift':review['review_source_drift'],'prompt_exact':review['final_prompt_embedded_exactly']}))
