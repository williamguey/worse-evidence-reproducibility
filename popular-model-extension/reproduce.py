"""Reproduce the entire fixed extension output offline, with independent checks."""
from pathlib import Path
import argparse,json,sys
sys.dont_write_bytecode=True
from extension_reproduction import (load,file_sha,canonical_sha,numeric_tuple,independent_oracle,
    cells_from_public,recompute,compare_subset)
import inference
import decision_engine
import parameter_codec

def reproduce(repository,output):
    repository=Path(repository).resolve();manifest=load(repository/'manifest.json')
    for name,digest in manifest['files'].items():
        if file_sha(repository/name)!=digest:raise RuntimeError('Published input/source changed: '+name)
    study=load(repository/'study.json');cases=load(repository/'cases.json');controls=load(repository/'controls.json')
    index=load(repository/'request-index.json');outcomes=load(repository/'outcomes.json');proof=load(repository/'sampling-proof.json')
    blocked={tuple(x[:3])+tuple(tuple(r) for r in x[3:]) for x in proof['fixed_blocked_numeric_tuples']}
    import hashlib
    fp=lambda sig:hashlib.sha256(json.dumps(sig,separators=(',',':')).encode('ascii')).hexdigest()
    old_sha=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if old_sha(sorted(blocked))!=proof['fixed_blocked_set_sha256']:raise RuntimeError('Published blocked set changed')
    by_case={c['case_id']:c for c in cases+controls};seen=set()
    for c in cases+controls:
        sig=numeric_tuple(c);truth=independent_oracle(c)
        if sig in blocked or sig in seen:raise RuntimeError('Numeric collision, including report-label swap')
        seen.add(sig);decision_engine.validate_supplied_oracle(c,c['oracle'])
        if truth['winner']!=c['oracle']['optimal_report']:raise RuntimeError('Independent oracle differs')
        if c in cases:
            g=c['generation'];slot=g['independent_slot'];seed=int(old_sha({'study_seed':study['seed'],'role':'heldout-independent-slot','slot':slot})[:16],16)
            if int(fp(sig),16)%8!=slot['numeric_hash_slot'] or seed!=g['seed'] or fp(sig)!=g['parameter_sha256'] or g['fixed_blocked_parameter_set_sha256']!=proof['fixed_blocked_set_sha256']:raise RuntimeError('Case hash/slot/seed differs')
    models={m['id']:m for m in study['models']}
    if len(index)!=3328 or len(cases)!=96 or len(controls)!=32:raise RuntimeError('Fixed plan size differs')
    for rid,e in index.items():
        b=e['body'];t=e['task'];m=models[e['configuration_id']]
        if e['body_sha256']!=canonical_sha(b) or rid!='h01-v10-heldout-'+e['configuration_id']+'-'+canonical_sha(b)[:20]:raise RuntimeError('Body/ID hash differs')
        if any(b[k]!=m[k] for k in ('model','provider','max_tokens')) or b.get('reasoning')!=m.get('reasoning') or ('reasoning' in b)!=('reasoning' in m) or b['stream'] is not False or 'temperature' in b or b['plugins']!=[{'id':'context-compression','enabled':False}]:raise RuntimeError('Fixed native settings differ')
        schema=b['response_format']['json_schema']
        if schema['strict'] is not True or schema['schema']!={'type':'object','properties':{'choice':{'type':'string','enum':['A','B']}},'required':['choice'],'additionalProperties':False}:raise RuntimeError('Strict schema differs')
        prompt=b['messages'][1]['content'];truth=independent_oracle(by_case[t['case_id']])
        if canonical_sha(prompt)!=t['prompt_sha256'] or t['expected']!=truth['winner'] or t['gap']!=str(truth['gap']) or t['normalized_gap']!=str(truth['normalized_gap']):raise RuntimeError('Task source/oracle metadata differs')
        lines=[next(x for x in prompt.splitlines() if x.startswith(prefix)) for prefix in ('Prior P(Z=1):','Loss ACT in state 0:','Loss WAIT in state 1:')]
        lines += [next(x for x in prompt.splitlines() if x.startswith('Report '+r+': sensitivity=')) for r in ('A','B')]
        parameter_codec.validate_rendered_source(by_case[t['case_id']],'\n'.join(lines))
    cells=cells_from_public(index,outcomes,cases+controls);independent=recompute(cases,cells,study)
    result=inference.analyze_scored_cells(cases,cells,list(models),study['scientific']['mode_pairs'],bootstrap_draws=inference.BOOTSTRAP_DRAWS)
    discrepancies=compare_subset({k:v for k,v in independent.items() if k!='control_summary'},result)
    expected=load(repository/'expected-analysis.json');discrepancies+=compare_subset(result,expected)
    discrepancies+=compare_subset(independent['control_summary'],load(repository/'expected-controls.json'))
    if discrepancies:raise RuntimeError(json.dumps(discrepancies,indent=2))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    for name,value in [('reproduced-analysis.json',result),('reproduced-controls.json',independent['control_summary']),('reproduced-cells.json',cells)]:
        (output/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    receipt={'status':'SYNTHETIC_PUBLIC_REPRODUCTION_PASS' if manifest['kind']=='SYNTHETIC_FIXTURE_ONLY' else 'OFFLINE_PUBLIC_REPRODUCTION_PASS','case_count':96,'requests':3328,'family_size':5,'independent_oracle_scoring_missing_bounds_tests':True,'all_paper_endpoints_reproduced':True,'api_calls':0}
    (output/'reproduction-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',type=Path,default=Path(__file__).resolve().parent);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(reproduce(a.repository,a.output),indent=2))
