"""Existing-choice descriptive synthesis. No tests, CIs, APIs, or new inference."""
from __future__ import annotations
import argparse,csv,hashlib,json
from collections import Counter
from fractions import Fraction
from itertools import product
from pathlib import Path

MODELS=('llama_default','deepseek_off','luna_off')
ORDERS=('AB','BA')
CONDITIONS=('neutral_1','neutral_2','bundle_bad','bundle_good','preference_bad_1','preference_bad_2','sponsor_bad','commitment_bad','guard_bundle_bad','guard_neutral','simple_neutral','simple_bundle_bad')
TARGETED=('bundle_bad','bundle_good','guard_bundle_bad','preference_bad_1','preference_bad_2','sponsor_bad','commitment_bad','simple_bundle_bad')

def exact_oracle(p):
    p1=Fraction(p['prior_state1']); l0=Fraction(p['loss_ACT_state0']);l1=Fraction(p['loss_WAIT_state1'])
    totals={}
    for label,r in p['reports'].items():
        sens=Fraction(r['sensitivity']);spec=Fraction(r['specificity'])
        # Direct minimization by signal; independent of the prior four-policy implementation.
        positive=min((1-p1)*(1-spec)*l0,p1*sens*l1)
        negative=min((1-p1)*spec*l0,p1*(1-sens)*l1)
        totals[label]=Fraction(r['cost'])+positive+negative
    assert totals['A']!=totals['B']
    return min(totals,key=totals.get),totals

def ratio(n,d):return None if not d else n/d
def binary(n,valid,planned):
    assert 0<=n<=valid<=planned
    return {'count':n,'valid':valid,'planned':planned,'missing':planned-valid,
            'observed_rate':ratio(n,valid),'full_plan_identification_bounds':[n/planned,(n+planned-valid)/planned]}

def contrast(ids,model,coefficients,index):
    lo=hi=Fraction(0);complete=[]
    for cid in ids:
        total=Fraction(0);known=True
        for arm,coefficient in coefficients.items():
            for order in ORDERS:
                e=index[cid,model,arm,order]['error'];known &= e is not None
                lower=0 if e is None else e;upper=1 if e is None else e
                lo+=Fraction(coefficient*(lower if coefficient>0 else upper),2)
                hi+=Fraction(coefficient*(upper if coefficient>0 else lower),2)
                if e is not None:total+=Fraction(coefficient*e,2)
        if known:complete.append(total)
    return {'planned_case_clusters':len(ids),'complete_case_clusters':len(complete),
            'missing_or_incomplete_case_clusters':len(ids)-len(complete),
            'complete_case_descriptive_contrast':None if not complete else float(sum(complete)/len(complete)),
            'full_plan_identification_bounds':[float(lo/len(ids)),float(hi/len(ids))],
            'exact_full_plan_identification_bounds':[str(lo/len(ids)),str(hi/len(ids))]}

def compute(cases,cells):
    assert len(cases)==344 and len(cells)==22656
    ids=sorted(c['case_id'] for c in cases if not c['control']);assert len(ids)==312
    truths={c['case_id']:exact_oracle(c['parameters']) for c in cases}
    kinds={c['case_id']:c['control_kind'] for c in cases if c['control']}
    for c in cases:
        if not c['control']:continue
        best=truths[c['case_id']][0];other='B' if best=='A' else 'A';a=c['parameters']['reports'][best];b=c['parameters']['reports'][other]
        dominant=Fraction(a['cost'])<=Fraction(b['cost']) and Fraction(a['sensitivity'])>=Fraction(b['sensitivity']) and Fraction(a['specificity'])>=Fraction(b['specificity'])
        assert dominant == (c['control_kind']=='dominance')
    for r in cells:
        best=truths[r['case_id']][0];assert r['optimal_report']==best
        assert r['error']==(None if r['choice'] is None else int(r['choice']!=best))
    index={(r['case_id'],r['model_id'],r['condition'],r['order']):r for r in cells if r['kind']=='science'}
    assert len(index)==22464 and len({r['request_id'] for r in cells})==22656
    assert set(index)==set(product(ids,MODELS,CONDITIONS,ORDERS))
    control_rows=[]
    for model,kind,order in product(MODELS,('dominance','nondominance'),(*ORDERS,'both_orders')):
        rows=[r for r in cells if r['kind']=='control' and r['model_id']==model and kinds[r['case_id']]==kind and (order=='both_orders' or r['order']==order)]
        valid=[r for r in rows if r['choice'] is not None];correct=sum(r['error']==0 for r in valid)
        control_rows.append({'model_id':model,'control_kind':kind,'order_group':order,**binary(correct,len(valid),len(rows)),'incorrect_valid':len(valid)-correct})
    positions=[]
    for model,arm,order in product(MODELS,('neutral_1','neutral_2','guard_neutral','simple_neutral'),(*ORDERS,'both_orders')):
        rows=[index[cid,model,arm,o] for cid in ids for o in ORDERS if order=='both_orders' or o==order]
        valid=[r for r in rows if r['choice'] is not None]
        for metric in ('report_identity_A','first_numerically_displayed'):
            count=sum(r['choice']==('A' if metric=='report_identity_A' else r['order'][0]) for r in valid)
            positions.append({'model_id':model,'condition':arm,'order_group':order,'metric':metric,**binary(count,len(valid),len(rows))})
    following=[];both=[]
    for model,arm in product(MODELS,TARGETED):
        def target(cid):
            best=truths[cid][0]
            return best if arm=='bundle_good' else ('B' if best=='A' else 'A')
        for order in (*ORDERS,'both_orders'):
            rows=[index[cid,model,arm,o] for cid in ids for o in ORDERS if order=='both_orders' or o==order]
            valid=[r for r in rows if r['choice'] is not None]
            count=sum(r['choice']==target(r['case_id']) for r in valid)
            following.append({'model_id':model,'condition':arm,'order_group':order,'endorsed_target':'optimal' if arm=='bundle_good' else 'inferior',**binary(count,len(valid),len(rows))})
        complete=followed=possible=definitely_not=unknown=0
        for cid in ids:
            choices=[index[cid,model,arm,o]['choice'] for o in ORDERS]
            flags=[None if x is None else x==target(cid) for x in choices]
            complete+=all(x is not None for x in flags)
            followed+=all(x is True for x in flags)
            possible+=not any(x is False for x in flags)
            definitely_not+=any(x is False for x in flags)
            unknown+=any(x is None for x in flags)
        both.append({'model_id':model,'condition':arm,'endorsed_target':'optimal' if arm=='bundle_good' else 'inferior',
                     'planned_cases':312,'complete_order_pairs':complete,'cases_with_unavailable_order':unknown,
                     'followed_in_both_orders':followed,'definitely_not_both_followed':definitely_not,
                     'both_following_rate_among_complete_pairs':ratio(followed,complete),
                     'full_plan_identification_bounds':[followed/312,possible/312]})
    arms=[]
    for model,arm in product(MODELS,CONDITIONS):
        rows=[index[cid,model,arm,o] for cid in ids for o in ORDERS];valid=[r for r in rows if r['choice'] is not None]
        arms.append({'model_id':model,'condition':arm,**binary(sum(r['error'] for r in valid),len(valid),len(rows))})
    guards=[]
    for model in MODELS:
        guards.append({'model_id':model,'contrast':'guard_neutral_minus_neutral_2',**contrast(ids,model,{'guard_neutral':1,'neutral_2':-1},index)})
    return {'status':'EXISTING_DATA_DESCRIPTIVE_SYNTHESIS','case_bank':'shared_312','planned_scientific_choices':22464,'planned_all_choices':22656,
            'new_hypothesis_tests':0,'new_confidence_intervals':0,'new_API_calls':0,
            'control_accuracy_by_type_and_order':control_rows,'neutral_identity_and_position':positions,
            'endorsement_following_by_arm_and_order':following,'both_order_endorsement_following':both,
            'guard_neutral_error_contrast':guards,'all_arm_error_rates':arms,
            'limits':['Descriptive choice rates condition on valid responses; full-plan bounds retain missing outcomes.',
                      'First displayed means the numerical report/table/menu order, not first lexical mention; A/B report identities remain fixed.',
                      'Both-order pairs are nested within 312 whole-case clusters and are not new independent cases.',
                      'Guard-neutral contrasts are post hoc descriptions, with no new tests or confidence intervals.',
                      'Component/preference arms target the inferior report only; they cannot distinguish directional following from disruption for each individual cue.',
                      'Controls describe dominance/nondominance performance; observed errors do not identify fraction comparison as a mechanism.']}

def load(directory):
    cases=json.loads((directory/'cases.json').read_text())
    with (directory/'cells.csv').open(newline='') as f:cells=list(csv.DictReader(f))
    for r in cells:r['choice']=r['choice'] or None;r['error']=None if r['error']=='' else int(r['error'])
    return cases,cells

def write(directory,result):
    directory.mkdir(parents=True,exist_ok=False)
    (directory/'synthesis-diagnostics.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    for key,rows in result.items():
        if isinstance(rows,list) and rows and isinstance(rows[0],dict):
            with (directory/(key+'.csv')).open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=Path(__file__).parent);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=compute(*load(a.input));expected=a.input/'expected-synthesis-diagnostics.json'
    if expected.exists():assert result==json.loads(expected.read_text()),'Exact descriptive reproduction differs.'
    write(a.output,result)
    print('EXISTING_CHOICE_SYNTHESIS_PASS: 312 clusters, 22656 retained cells, no added tests, CIs, or API calls')
