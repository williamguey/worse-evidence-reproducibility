"""Offline regeneration of genuine choices, exact scores and frozen inference."""
import argparse, hashlib, importlib.util, json, math
from pathlib import Path
from fractions import Fraction
from itertools import product
ROOT=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def exact(p):
    prior=Fraction(p['prior_state1']);l0=Fraction(p['loss_ACT_state0']);l1=Fraction(p['loss_WAIT_state1']);scores={}
    for r in 'AB':
        q=p['reports'][r];se=Fraction(q['sensitivity']);sp=Fraction(q['specificity']);cost=Fraction(q['cost'])
        j=((1-prior)*(1-sp),prior*se,(1-prior)*sp,prior*(1-se))
        scores[r]=min(cost+(l0*j[0] if a else l1*j[1])+(l0*j[2] if b else l1*j[3]) for a,b in product((True,False),repeat=2))
    if scores['A']==scores['B']:raise ValueError('Tied exact key')
    return min(scores,key=scores.get),abs(scores['A']-scores['B'])

def choice(record):
    d=record.get('response') or {}
    if record['state']!='valid_unscored':return None
    if d.get('choice_count')!=1 or d.get('finish_reason')!='stop' or d.get('refusal_present') or d.get('api_error_present'):raise ValueError('Accepted output failed format')
    def unique(items):
        out=dict(items)
        if len(out)!=len(items):raise ValueError('Duplicate JSON fields')
        return out
    x=json.loads(d['content'],object_pairs_hook=unique)
    if not isinstance(x,dict) or set(x)!={'choice'} or x['choice'] not in ('A','B'):raise ValueError('Accepted output invalid')
    return x['choice']

def near(a,b,path='root'):
    if isinstance(a,dict):
        if set(a)!=set(b):raise ValueError('Result keys differ '+path)
        for k in a:near(a[k],b[k],path+'.'+k)
    elif isinstance(a,list):
        if len(a)!=len(b):raise ValueError('Result lengths differ '+path)
        for i,(x,y) in enumerate(zip(a,b)):near(x,y,path+'['+str(i)+']')
    elif isinstance(a,(int,float)) and not isinstance(a,bool):
        if not isinstance(b,(int,float)) or not math.isclose(a,b,rel_tol=2e-9,abs_tol=2e-10):raise ValueError('Result number differs '+path)
    elif a!=b:raise ValueError('Result value differs '+path)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',default='reproduced');args=p.parse_args();out=ROOT/args.out;out.mkdir(exist_ok=True)
    manifest=read(ROOT/'manifest.json')
    for name,h in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h:raise ValueError('Package file changed: '+name)
    cases=read(ROOT/'cases.json')+read(ROOT/'controls.json');keys={c['case_id']:exact(c['parameters']) for c in cases}
    plan=read(ROOT/'plan.json')
    checked=set()
    for e in plan:
        if e['body_path'] not in checked:
            if hashlib.sha256((ROOT/e['body_path']).read_bytes()).hexdigest()!=e['body_sha256']:raise ValueError('Body commitment differs')
            checked.add(e['body_path'])
    records={x['request_id']:x for x in [json.loads(s) for s in (ROOT/'responses.jsonl').read_text().splitlines()]}
    if len(plan)!=22656 or len(records)!=len(plan) or set(records)!={e['request_id'] for e in plan}:raise ValueError('Fixed cells dropped/duplicated')
    scored=[]
    for e in plan:
        ch=choice(records[e['request_id']]);winner,gap=keys[e['case_id']]
        scored.append({k:e[k] for k in ('request_id','case_id','model_id','condition','order','kind')} | {'choice':ch,'error':None if ch is None else int(ch!=winner),'regret':None if ch is None else str(gap*int(ch!=winner)),'availability':records[e['request_id']]['state']})
    spec=importlib.util.spec_from_file_location('frozen_v11_inference',ROOT/'inference.py');inf=importlib.util.module_from_spec(spec);spec.loader.exec_module(inf)
    gaps={c['case_id']:float(keys[c['case_id']][1]) for c in read(ROOT/'cases.json')};result=inf.analyze(plan,scored,gaps=gaps)
    near(result,read(ROOT/'expected-analysis.json'))
    (out/'scored.json').write_text(json.dumps(scored,indent=2)+'\n');(out/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('OFFLINE_REPRODUCTION_PASS: 22656 fixed cells, 312 independent cases, Holm9 preserved')
