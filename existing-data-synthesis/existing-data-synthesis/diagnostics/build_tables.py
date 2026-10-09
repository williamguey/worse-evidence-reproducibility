"""Compact LaTeX tables for five post hoc descriptive summaries; no inference."""
import json
from fractions import Fraction
from pathlib import Path
HERE=Path(__file__).resolve().parent
NAMES={'llama_default':'Llama 4 Maverick (default)','deepseek_off':'DeepSeek v4 Pro (off)','luna_off':'GPT-5.6 Luna (off)'}
ARMS={'neutral_1':'Neutral repeat 1','neutral_2':'Neutral repeat 2','guard_neutral':'Priority neutral','simple_neutral':'Simplified neutral','bundle_bad':'Inferior bundle','bundle_good':'Optimal bundle','guard_bundle_bad':'Priority inferior','simple_bundle_bad':'Simplified inferior','sponsor_bad':'Sponsor only','commitment_bad':'Commitment only','preference_bad_1':'Preference wording 1','preference_bad_2':'Preference wording 2'}
def interval(v):
    a,b=map(Fraction,v)
    lower=(a.numerator*10000)//a.denominator
    upper=-((-b.numerator*10000)//b.denominator)
    def fmt(n):return ('-' if n<0 else '')+str(abs(n)//100)+'.'+f'{abs(n)%100:02d}'
    return '['+fmt(lower)+', '+fmt(upper)+']'
def binary_bounds(r):return [Fraction(r['count'],r['planned']),Fraction(r['count']+r['missing'],r['planned'])]
def table(label,caption,head,rows,align):
    body=['\\begin{table*}[t]\\centering\\scriptsize','\\caption{'+caption+' Bound endpoints are rounded outward.}','\\label{tab:synthesis-'+label+'}','\\resizebox{\\textwidth}{!}{%','\\begin{tabular}{'+align+'}\\toprule',' & '.join(head)+r' \\ \midrule']
    body+=[' & '.join(str(x) for x in row)+r' \\' for row in rows]
    body+=['\\bottomrule\\end{tabular}}','\\end{table*}']
    return '\n'.join(body)+'\n'
def main():
    d=json.loads((HERE/'actual/synthesis-diagnostics.json').read_text());parts=[]
    c=d['control_accuracy_by_type_and_order'];rows=[]
    for model in NAMES:
        for kind in ('dominance','nondominance'):
            group={r['order_group']:r for r in c if r['model_id']==model and r['control_kind']==kind};a,b,t=[group[o] for o in ('AB','BA','both_orders')]
            rows.append([NAMES[model],kind,f'{a["count"]}/{a["valid"]}',f'{b["count"]}/{b["valid"]}',f'{t["count"]}/{t["valid"]}',t['missing'],interval(binary_bounds(t))])
    parts.append(table('controls','Correct control choices by numerical dominance and display order. Each type plans 16 choices per order, 32 combined; fractions use valid-choice denominators. Bounds retain missing outcomes over all 32 planned choices and are identification bounds, not confidence intervals.',['Configuration','Control type','AB correct/valid','BA correct/valid','Both correct/valid','Missing','Correct bounds (\\%)'],rows,'llrrrrr'))
    pos={(r['model_id'],r['condition'],r['order_group'],r['metric']):r for r in d['neutral_identity_and_position']};rows=[]
    for model in NAMES:
        for arm in ('neutral_1','neutral_2','guard_neutral','simple_neutral'):
            for order in ('AB','BA'):
                a=pos[model,arm,order,'report_identity_A'];f=pos[model,arm,order,'first_numerically_displayed']
                rows.append([NAMES[model],ARMS[arm],order,f'{a["count"]}/{a["valid"]}',f'{f["count"]}/{f["valid"]}',a['missing'],interval(binary_bounds(a)),interval(binary_bounds(f))])
    parts.append(table('position','Neutral A-identity and first-numerically-displayed choices, 312 planned cases per configuration, arm and order. First means the numerical table/menu order, not the first lexical mention. Fractions condition on valid choices; each interval bounds the rate among all 312 planned choices. These post hoc rates do not establish a population position-bias mechanism.',['Configuration','Neutral condition','Order','A/valid','First/valid','Missing','A bounds (\\%)','First bounds (\\%)'],rows,'lllrrrrr'))
    rows=[]
    for r in d['endorsement_following_by_arm_and_order']:
        if r['order_group']!='both_orders':continue
        rows.append([NAMES[r['model_id']],ARMS[r['condition']],r['endorsed_target'],f'{r["count"]}/{r["valid"]}',r['missing'],interval(binary_bounds(r))])
    parts.append(table('following','Choices of the endorsed report, pooling the two display orders descriptively within each configuration and arm. Every row plans 624 choices from 312 cases. The optimal bundle endorses the optimal report; all other rows endorse the inferior report. Fractions use valid choices and bounds retain all 624 planned outcomes. Component and wording rows lack optimal-target counterparts.',['Configuration','Endorsement condition','Target','Following/valid','Missing','Following bounds (\\%)'],rows,'lllrrr'))
    rows=[]
    for r in d['guard_neutral_error_contrast']:
        rows.append([NAMES[r['model_id']],f'{100*r["complete_case_descriptive_contrast"]:+.2f}',f'{r["complete_case_clusters"]}/312',r['missing_or_incomplete_case_clusters'],interval(r['exact_full_plan_identification_bounds'])])
    parts.append(table('guard-neutral','Guarded-neutral minus second-neutral error contrast. Each case averages its two orders. Complete-case means and full-plan identification bounds have different missingness targets; bounds retain all 312 cases. This is a post hoc descriptive comparison with no new test or confidence interval.',['Configuration','Complete-case contrast (pp)','Complete/planned cases','Incomplete cases','Full-plan bounds (pp)'],rows,'lrrrr'))
    rows=[]
    for r in d['both_order_endorsement_following']:
        rows.append([NAMES[r['model_id']],ARMS[r['condition']],f'{r["followed_in_both_orders"]}/{r["complete_order_pairs"]}',r['cases_with_unavailable_order'],r['definitely_not_both_followed'],interval([Fraction(r['followed_in_both_orders'],312),Fraction(312-r['definitely_not_both_followed'],312)])])
    parts.append(table('both-orders','Endorsement following in both numerical display orders. Every row plans 312 whole cases. Both/complete conditions on two available choices; full-plan bounds additionally retain partially unavailable cases unless an observed nonfollowing choice already excludes following in both orders. The two orders remain nested within each case.',['Configuration','Endorsement condition','Both/complete cases','Unavailable-order cases','Known not-both cases','Both bounds (\\%)'],rows,'llrrrr'))
    text='\n'.join(parts)
    (HERE.parent/'appendix-tables.tex').write_text(text)
    (HERE/'descriptive-table-inputs.json').write_text(json.dumps({'input':'actual/synthesis-diagnostics.json','five_tables':{'controls':6,'position':24,'following':24,'guard-neutral':3,'both-orders':24},'new_tests':0,'new_CIs':0},indent=2)+'\n')
    print('COMPACT_DESCRIPTIVE_TABLES_PASS: five tables, full planned bounds, no duplicated 36-arm table')
if __name__=='__main__':main()
