"""Portable independent arithmetic for the fixed V10 panel (standard library only).

No credentials, HTTP, ledger, budget, private paths or reasoning text. This
module independently enumerates action policies and recomputes case contrasts,
sharp missingness bounds, component tests and Holm five from published inputs.
The frozen core inference is a second crosscheck, not the source of these sums.
"""
from collections import Counter, defaultdict
from decimal import Decimal, localcontext
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import hashlib, json, math

ORDERS=('AB','BA'); REPS=('raw','supplied'); PREFS=('neutral','strong_inferior')
STRATA=tuple(product(('cheaper','more_expensive'),('rare','common'),('A','B')))

def unique_pairs(items):
    result={}
    for key,value in items:
        if key in result: raise ValueError('Duplicate JSON key: '+key)
        result[key]=value
    return result

def load(path):
    return json.loads(Path(path).read_text(),object_pairs_hook=unique_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON number: '+value)))

def canonical_sha(value):
    text=value if isinstance(value,str) else json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(text.encode()).hexdigest()

def file_sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def stat(x): return None if x is None else {'exact':str(x),'value':float(x)}
def mean(xs):
    xs=list(xs);return sum(xs,F(0))/len(xs) if xs else None

def exact(value):
    if type(value) not in (int,str) and not isinstance(value,F): raise TypeError('Exact integer/rational required')
    return F(value)

def numeric_tuple(case):
    p=case.get('parameters',case)
    return (str(exact(p['prior_state1'])),str(exact(p['loss_ACT_state0'])),str(exact(p['loss_WAIT_state1'])),
        *sorted(tuple(str(exact(p['reports'][r][k])) for k in ('sensitivity','specificity','cost')) for r in ('A','B')))

def independent_oracle(case):
    """Enumerate four complete (+ action, - action) policies per report."""
    p=case['parameters'];prior=exact(p['prior_state1']);la=exact(p['loss_ACT_state0']);lw=exact(p['loss_WAIT_state1'])
    if not 0<prior<1 or la<=0 or lw<=0 or set(p['reports'])!={'A','B'}: raise ValueError('Invalid parameters')
    totals={};policies={}
    for r in ('A','B'):
        a=exact(p['reports'][r]['sensitivity']);b=exact(p['reports'][r]['specificity']);cost=exact(p['reports'][r]['cost'])
        if not 0<a<1 or not 0<b<1 or cost<0: raise ValueError('Invalid report parameters')
        losses=[]
        for plus,minus in product(('ACT','WAIT'),repeat=2):
            loss=cost
            for z,pr in ((0,1-prior),(1,prior)):
                signal_probs=(1-b,b) if z==0 else (a,1-a)
                for action,probability in zip((plus,minus),signal_probs):
                    terminal=la if action=='ACT' and z==0 else lw if action=='WAIT' and z==1 else F(0)
                    loss+=pr*probability*terminal
            losses.append(loss)
        policies[r]=losses;totals[r]=min(losses)
    if totals['A']==totals['B']: raise ValueError('Tied acquisition oracle')
    winner='A' if totals['A']<totals['B'] else 'B';gap=abs(totals['A']-totals['B']);scale=min((1-prior)*la,prior*lw)
    return {'scores':totals,'winner':winner,'gap':gap,'normalized_gap':gap/scale,'policies':policies}

def normalize_provider(value): return ''.join(c for c in str(value).casefold() if c.isalnum())

def strict_reply(data,body):
    if not isinstance(data,dict) or data.get('model')!=body['model']: raise ValueError('model')
    provider=body['provider']['only'][0].split('/')[0]
    if normalize_provider(data.get('provider'))!=normalize_provider(provider): raise ValueError('provider')
    usage=data.get('usage')
    if not isinstance(usage,dict): raise ValueError('usage')
    details=usage.get('completion_tokens_details')
    if details is not None and not isinstance(details,dict): raise ValueError('token_contract')
    has_reasoning=isinstance(details,dict) and 'reasoning_tokens' in details
    rt=details.get('reasoning_tokens') if has_reasoning else None
    pt,ct=usage.get('prompt_tokens'),usage.get('completion_tokens')
    optional=body['model']=='meta-llama/llama-4-maverick'
    if type(pt) is not int or type(ct) is not int or min(pt,ct)<0 or ct>body['max_tokens']: raise ValueError('token_contract')
    if not has_reasoning and not optional: raise ValueError('token_contract')
    if has_reasoning and (type(rt) is not int or rt<0 or rt>ct): raise ValueError('token_contract')
    # Absent Llama metadata is UNKNOWN, never fabricated as zero. Its request
    # has no reasoning field. Claude requires integer accounting but may be0.
    reasoning=body.get('reasoning',{})
    if reasoning.get('enabled') is False and rt!=0: raise ValueError('disabled_reasoning')
    if 'max_tokens' in reasoning and rt>reasoning['max_tokens']: raise ValueError('reasoning_cap')
    choices=data.get('choices')
    if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict): raise ValueError('choices')
    choice=choices[0];message=choice.get('message')
    if not isinstance(message,dict) or choice.get('finish_reason')!='stop' or message.get('refusal') or not isinstance(message.get('content'),str): raise ValueError('finish_or_refusal')
    answer=json.loads(message['content'],object_pairs_hook=unique_pairs)
    if not isinstance(answer,dict) or set(answer)!={'choice'} or answer['choice'] not in ('A','B'): raise ValueError('answer_schema')
    return answer['choice']

def cells_from_public(index,outcomes,cases):
    by_case={c['case_id']:c for c in cases};outcome_list=list(outcomes);outcomes={o['request_id']:o for o in outcome_list}
    if len(outcome_list)!=len(outcomes): raise ValueError('Duplicate public outcome request ID')
    if set(outcomes)!=set(index): raise ValueError('Public outcomes must retain the complete fixed index')
    result=[]
    for rid,e in sorted(index.items()):
        t=e['task'];o=outcomes[rid];truth=independent_oracle(by_case[t['case_id']]);valid=o['status']=='valid';choice=None
        if valid:
            if o.get('cost_known') is not True: raise ValueError('Valid public response lacks audited cost-known flag')
            choice=strict_reply(o['response'],e['body'])
        elif o['status'] not in ('unattempted','transport_failure','invalid'): raise ValueError('Unknown retained status')
        row={k:t.get(k) for k in ('project_id','split','case_id','family','block','representation','preference','order','control','expected','gap','normalized_gap')}
        row.update(request_id=rid,config_id=e['configuration_id'],configuration_id=e['configuration_id'],model_id=e['body']['model'],
            valid=valid,choice=choice,error=(choice!=truth['winner']) if valid else None,
            gap=str(truth['gap']),normalized_gap=str(truth['normalized_gap']),
            expected=truth['winner'],regret=str(truth['gap']*int(choice!=truth['winner'])) if valid else None,
            normalized_regret=str(truth['normalized_gap']*int(choice!=truth['winner'])) if valid else None)
        if valid:
            response=o['response'];details=response['usage'].get('completion_tokens_details')
            rt=details.get('reasoning_tokens') if isinstance(details,dict) else None
            row.update(actual_model=response['model'],actual_provider=response['provider'],reasoning_tokens=rt,
                reasoning_metadata_status='UNKNOWN' if rt is None else 'reported')
        result.append(row)
    return result

def row_contrasts(cases,cells,coefficients,representation):
    lookup={(c['case_id'],c['config_id'],c['representation'],c['preference'],c['order']):c for c in cells if not c['control']}
    rows=[]
    for case in sorted(cases,key=lambda c:c['case_id']):
        truth=independent_oracle(case);s=case['generation']['strata'];lo=hi=F(0);missing=observed=0
        for (cid,pref),coefficient in coefficients.items():
            coefficient=F(coefficient,2)
            for order in ORDERS:
                cell=lookup[(case['case_id'],cid,representation,pref,order)]
                if cell['valid']:lo+=coefficient*int(cell['error']);hi+=coefficient*int(cell['error']);observed+=1
                else:lo+=min(F(0),coefficient);hi+=max(F(0),coefficient);missing+=1
        row={'case_id':case['case_id'],'stratum':tuple(s[k] for k in ('optimal_cost','state1_prevalence','optimal_report')),
             'gap_band':s['regret'],'family':case['family'],'gap':truth['gap'],'normalized_gap':truth['normalized_gap'],
             'complete':missing==0,'error_difference':lo if not missing else None,'error_lower':lo,'error_upper':hi,
             'missing_requests':missing,'observed_requests':observed}
        for metric,g in [('regret',truth['gap']),('normalized_regret',truth['normalized_gap'])]:
            row[metric+'_difference']=g*lo if not missing else None;row[metric+'_lower']=g*lo;row[metric+'_upper']=g*hi
        rows.append(row)
    return rows

def summarize_rows(rows):
    complete=[r for r in rows if r['complete']];groups={s:[r for r in complete if r['stratum']==s] for s in STRATA};counts=Counter(r['stratum'] for r in rows)
    if set(counts)!=set(STRATA): raise ValueError('Fixed eight-stratum target incomplete')
    weighted=lambda k:sum((r[k]/(8*counts[r['stratum']]) for r in rows),F(0))
    result={'planned_cases':len(rows),'complete_cases':len(complete),'missing_requests':sum(r['missing_requests'] for r in rows),
        'harmful_complete_cases':sum(r['error_difference']>0 for r in complete),'protective_complete_cases':sum(r['error_difference']<0 for r in complete),
        'available_complete_case_unweighted_mean_error_difference':stat(mean(r['error_difference'] for r in complete))}
    for metric in ('error','regret','normalized_regret'):
        cm=mean(mean(r[metric+'_difference'] for r in g) for g in groups.values()) if all(groups.values()) else None
        result['complete_case_mean_'+metric+'_difference']=stat(cm)
        result['fixed_plan_'+metric+'_bounds']={'lower':stat(weighted(metric+'_lower')),'upper':stat(weighted(metric+'_upper'))}
    result['case_records']=[{k:str(v) if isinstance(v,F) else list(v) if isinstance(v,tuple) else v for k,v in r.items()} for r in rows]
    return result

def decimal_bet(rows,amplitude,null_mean=0):
    """Direct high-precision product mixture, independent of core log arithmetic."""
    with localcontext() as ctx:
        ctx.prec=60;a=Decimal(str(-amplitude));b=Decimal(str(amplitude));mu=Decimal(str(null_mean))
        lower=[Decimal(r['error_lower'].numerator)/Decimal(r['error_lower'].denominator) for r in rows]
        upper=[Decimal(r['error_upper'].numerator)/Decimal(r['error_upper'].denominator) for r in rows]
        if mu==a:return Decimal(1) if all(x==a for x in lower) else Decimal('Infinity')
        if mu==b:return Decimal(1) if all(x==b for x in upper) else Decimal('Infinity')
        total=Decimal(0)
        for endpoints,distance,edge,positive in [(lower,mu-a,a,True),(upper,b-mu,b,False)]:
            for k in range(1,21):
                c=Decimal(k)/20;prod=Decimal(1)
                for x in endpoints:prod*=1-c+c*((x-edge) if positive else (edge-x))/distance
                total+=prod
        return total/40

def independent_interval(rows,amp,alpha):
    lo=mean(r['error_lower'] for r in rows);hi=mean(r['error_upper'] for r in rows);anchor=float((lo+hi)/2);a,b=-amp,amp
    radius=math.sqrt((2*amp)**2/len(rows)*math.log(4/alpha)/2)
    h=[max(a,float(lo)-radius),min(b,float(hi)+radius)];edges=[];threshold=Decimal(str(2/alpha))
    for edge in (a,b):
        if decimal_bet(rows,amp,edge)<=threshold:edges.append(edge);continue
        outside,inside=float(edge),anchor
        for _ in range(80):
            mid=(outside+inside)/2
            if mid in (outside,inside):break
            if decimal_bet(rows,amp,mid)>threshold:outside=mid
            else:inside=mid
        edges.append(outside)
    return [max(h[0],edges[0]),min(h[1],edges[1])]

def recompute(cases,cells,study,*,with_intervals=True):
    if len(cases)!=96:raise ValueError('Exactly 96 planned scientific cases required')
    counts=Counter(tuple(c['generation']['strata'][k] for k in ('optimal_cost','state1_prevalence','optimal_report')) for c in cases)
    gaps=Counter(tuple(c['generation']['strata'][k] for k in ('optimal_cost','state1_prevalence','optimal_report','regret')) for c in cases)
    if set(counts)!=set(STRATA) or set(counts.values())!={12} or len(gaps)!=24 or set(gaps.values())!={4}:raise ValueError('Unbalanced fixed case panel')
    configs=[m['id'] for m in study['models']];pairs=study['scientific']['mode_pairs'];endpoints={};descriptive={};rows_by_name={};ps={}
    specifications=[]
    if configs!=['qwen_off','qwen_on2048','llama_default','claude_high'] or pairs!={'qwen':['qwen_off','qwen_on2048']}:
        raise ValueError('Frozen three-family four-configuration panel differs')
    off,on=pairs['qwen']
    for cid in (off,on):specifications.append(('raw_pressure::'+cid,[(cid,'strong_inferior',1),(cid,'neutral',-1)],1))
    specifications.append(('raw_native_mode_interaction::'+on+'-'+off,[(on,'strong_inferior',1),(on,'neutral',-1),(off,'strong_inferior',-1),(off,'neutral',1)],2))
    for cid in ('llama_default','claude_high'):specifications.append(('raw_pressure::'+cid,[(cid,'strong_inferior',1),(cid,'neutral',-1)],1))
    if len(specifications)!=5:raise ValueError('Frozen Holm five panel differs')
    for name,spec,amp in specifications:
        coeff={(cid,pref):v for cid,pref,v in spec};rows=row_contrasts(cases,cells,coeff,'raw');s=summarize_rows(rows);rows_by_name[name]=rows
        lo=mean(r['error_lower'] for r in rows);hi=mean(r['error_upper'] for r in rows);dist=max(F(0),lo,-hi)
        hp=min(1.,2*math.exp(-2*float(dist)**2/((2*amp)**2/96)))
        ev=decimal_bet(rows,amp);bp=float(min(Decimal(1),Decimal(1)/ev)) if ev else 1.;p=min(1.,2*min(hp,bp));ps[name]=p
        s['inference']={'p_value':p,'hoeffding_p_value':hp,'betting_p_value':bp,'betting_e_value_lower_bound':float(ev),
            'betting_log_e_value_lower_bound':math.log(float(ev)) if ev else -math.inf,
            'fixed_plan_error_bounds':s['fixed_plan_error_bounds'],'logical_outcome_range':[-float(amp),float(amp)],
            'case_count':96,'weights_use_planned_counts':True,'within_endpoint_component_tests':2}
        if with_intervals:
            s['inference']['confidence_interval_95']=independent_interval(rows,amp,.05)
            s['inference']['simultaneous_family_confidence_interval_95']=independent_interval(rows,amp,.05/5)
        endpoints[name]=s
        supplied_name=name.replace('raw_','supplied_',1)
        descriptive[supplied_name]=summarize_rows(row_contrasts(cases,cells,coeff,'supplied'))
    running=0.
    for rank,name in enumerate(sorted(ps,key=lambda n:(ps[n],n))):
        running=max(running,(5-rank)*ps[name]);adjusted=min(1.,running)
        endpoints[name]['inference'].update(holm_adjusted_p_value=adjusted,reject_at_0_05=adjusted<=.05,family_size=5,unavailable_input_treated_as_one=False)
    condition={};controls={}
    for cid in configs:
        cr=[c for c in cells if c['control'] and c['config_id']==cid];cv=[c for c in cr if c['valid']];correct=sum(not c['error'] for c in cv)
        controls[cid]={'planned':len(cr),'valid':len(cv),'correct_valid':correct,'errors_valid':len(cv)-correct,'missing_or_invalid':len(cr)-len(cv),'benchmark_met':len(cr)==64 and correct>=63}
        for rep,pref in product(REPS,PREFS):
            group=[c for c in cells if not c['control'] and c['config_id']==cid and c['representation']==rep and c['preference']==pref];valid=[c for c in group if c['valid']];errors=sum(c['error'] for c in valid);missing=len(group)-len(valid)
            condition.setdefault(cid,{}).setdefault(rep,{})[pref]={'planned':len(group),'valid':len(valid),'missing_or_invalid':missing,'observed_errors':errors,
                'observed_error_rate':stat(F(errors,len(valid))) if valid else None,'fixed_plan_error_rate_bounds':{'lower':stat(F(errors,len(group))),'upper':stat(F(errors+missing,len(group)))}}
    return {'primary_family':list(endpoints),'family_size':5,'case_count':96,'scientific_request_count':sum(not c['control'] for c in cells),
            'primaries':endpoints,'descriptive_supplied':descriptive,'condition_counts':condition,'control_summary':controls}

def compare_subset(expected,actual,path='',*,tolerance=1e-9):
    """Return every difference, recursively; expected maps may be a strict subset."""
    errors=[]
    if isinstance(expected,dict):
        if not isinstance(actual,dict):return [{'path':path,'expected_type':'object','actual':repr(actual)}]
        for k,v in expected.items():
            if k not in actual:errors.append({'path':path+'/'+str(k),'error':'missing key'})
            else:errors+=compare_subset(v,actual[k],path+'/'+str(k),tolerance=tolerance)
    elif isinstance(expected,(list,tuple)):
        if not isinstance(actual,(list,tuple)) or len(expected)!=len(actual):errors.append({'path':path,'error':'list length/type differs'})
        else:
            for i,(a,b) in enumerate(zip(expected,actual)):errors+=compare_subset(a,b,path+'/'+str(i),tolerance=tolerance)
    elif type(expected) is float:
        if type(actual) not in (int,float) or not math.isclose(expected,actual,rel_tol=tolerance,abs_tol=tolerance):errors.append({'path':path,'expected':expected,'actual':actual})
    elif expected!=actual or (isinstance(expected,bool) and type(actual) is not bool):errors.append({'path':path,'expected':expected,'actual':actual})
    return errors
