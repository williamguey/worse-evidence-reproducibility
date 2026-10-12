"""Post hoc descriptive summaries from the immutable, audited V11 export.

No network, sampling, fitted model, new tests, or changes to frozen artifacts.
See analysis-plan.txt for definitions fixed before this computation.
"""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction as F
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import re


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def independently_enumerated_totals(p):
    prior, l0, l1 = (F(p[k]) for k in ('prior_state1', 'loss_ACT_state0', 'loss_WAIT_state1'))
    answer = {}
    for report in 'AB':
        q = p['reports'][report]
        se, sp, cost = (F(q[k]) for k in ('sensitivity', 'specificity', 'cost'))
        plus0, plus1 = (1-prior)*(1-sp), prior*se
        minus0, minus1 = (1-prior)*sp, prior*(1-se)
        all_policies = [cost + (l0*plus0 if a else l1*plus1) + (l0*minus0 if b else l1*minus1)
                        for a, b in product((True, False), repeat=2)]
        enumerated = min(all_policies)
        signalwise = cost + min(l0*plus0, l1*plus1) + min(l0*minus0, l1*minus1)
        assert enumerated == signalwise
        answer[report] = enumerated
    scale = min((1-prior)*l0, prior*l1)
    gap = abs(answer['A'] - answer['B'])
    assert gap > 0 and scale > 0
    return answer, gap, gap/scale


def parse_choice(record):
    if record['state'] != 'valid_unscored':
        return None
    r = record['response']
    assert r['choice_count'] == 1 and r['finish_reason'] == 'stop'
    assert not r['api_error_present'] and not r['refusal_present']
    pairs = json.loads(r['content'], object_pairs_hook=list)
    assert len(pairs) == 1 and pairs[0][0] == 'choice' and pairs[0][1] in ('A', 'B')
    return pairs[0][1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    p = args.package.resolve()
    manifest = load(p/'manifest.json')
    for name, expected in manifest['files'].items():
        assert digest(p/name) == expected, name
    audit = load(p/'audit-summary.json')
    assert audit['status'] == 'EMPIRICAL_DATA_AUDIT_PASS'
    assert audit['collection_stop_utc']
    cases = load(p/'cases.json')
    plan = load(p/'plan.json')
    records_list = [json.loads(x) for x in (p/'responses.jsonl').read_text().splitlines()]
    records = {r['request_id']: r for r in records_list}
    assert len(records_list) == len(records) == len(plan) == 22656
    assert set(records) == {e['request_id'] for e in plan}
    assert len(cases) == len({c['case_id'] for c in cases}) == 312
    features = {}
    for c in cases:
        totals, gap, normalized_gap = independently_enumerated_totals(c['parameters'])
        for report in 'AB':
            assert str(totals[report]) == c['oracle']['reports'][report]['expected_total_score']
        assert str(gap) == c['oracle']['regret_of_wrong_report']
        assert str(normalized_gap) == c['oracle']['normalized_regret']
        band = 'low' if normalized_gap <= F(1,10) else 'moderate' if normalized_gap <= F(7,20) else 'high'
        assert band == c['generation']['strata']['regret']
        features[c['case_id']] = {
            'case_id': c['case_id'], 'totals': {r: str(totals[r]) for r in 'AB'},
            'winner': min(totals, key=totals.get), 'gap': str(gap),
            'normalized_gap': str(normalized_gap), 'gap_band': band,
            'denominator_group': 'same' if totals['A'].denominator == totals['B'].denominator else 'different'}
    cell_rows = []
    counters = defaultdict(Counter)
    group_cases = defaultdict(set)
    seen_bodies = set()
    for e in plan:
        if e['kind'] != 'science' or e['condition'] not in ('neutral_1', 'neutral_2'):
            continue
        f = features[e['case_id']]
        if e['body_path'] not in seen_bodies:
            body_path = p/e['body_path']
            assert digest(body_path) == e['body_sha256']
            body = load(body_path)
            content = '\n'.join(m['content'] for m in body['messages'])
            displayed = content.split('Audited expected total costs, including acquisition and optimal subsequent action:\n',1)[1].split('\n\n',1)[0]
            actual = dict(re.findall(r'Report ([AB]): ([^\n]+)',displayed))
            assert actual == f['totals']
            seen_bodies.add(e['body_path'])
        choice = parse_choice(records[e['request_id']])
        error = None if choice is None else int(choice != f['winner'])
        row = {'request_id':e['request_id'], 'case_id':e['case_id'], 'model_id':e['model_id'],
               'condition':e['condition'], 'order':e['order'], 'error':error,
               'state':records[e['request_id']]['state'], 'denominator_group':f['denominator_group'], 'gap_band':f['gap_band']}
        cell_rows.append(row)
        for attr, val in [('all','all'),('denominator_group',f['denominator_group']),('gap_band',f['gap_band'])]:
            key = (e['model_id'],e['condition'],attr,val)
            counters[key]['planned'] += 1
            counters[key]['missing' if error is None else 'valid'] += 1
            if error is not None:
                counters[key]['errors'] += error
            group_cases[key].add(e['case_id'])
    assert len(cell_rows) == 312*2*3*2
    # Independent second aggregation: construct the complete case/order grid,
    # then sum per-case values rather than updating response-level counters.
    by_case = defaultdict(dict)
    for row in cell_rows:
        k = (row['model_id'],row['condition'],row['case_id'])
        assert row['order'] not in by_case[k]
        by_case[k][row['order']] = row['error']
    assert len(by_case) == 312*3*2
    for grid in by_case.values():
        assert set(grid) == {'AB','BA'}
    check_rows = []
    for key, count in sorted(counters.items()):
        model, condition, attr, val = key
        keys = [k for k in by_case if k[:2] == (model,condition) and (attr == 'all' or features[k[2]][attr] == val)]
        vals = [x for k in keys for x in by_case[k].values()]
        independent = {'planned':2*len(keys),'valid':sum(x is not None for x in vals),
                       'missing':sum(x is None for x in vals),'errors':sum(x for x in vals if x is not None)}
        assert all(count[k] == independent[k] for k in independent)
        assert len(group_cases[key]) == len(keys)
        check_rows.append({'model_id':model,'condition':condition,'group_variable':attr,'group':val,
            'cases':len(keys),**independent,
            'observed_error_rate':independent['errors']/independent['valid'] if independent['valid'] else None,
            'full_plan_error_bounds':[independent['errors']/independent['planned'],
                                      (independent['errors']+independent['missing'])/independent['planned']]})
    expected = load(p/'expected-analysis.json')
    for row in check_rows:
        if row['group_variable'] != 'all':
            continue
        old = next(x for x in expected['arm_summaries'] if x['model_id'] == row['model_id'] and x['condition'] == row['condition'])
        for key in ('planned','valid','errors','missing'):
            assert row[key] == old[key]
        assert row['full_plan_error_bounds'] == old['full_plan_error_rate_bounds']
    counts = {attr:dict(Counter(f[attr] for f in features.values())) for attr in ('denominator_group','gap_band')}
    assert counts['gap_band'] == {'low':104,'moderate':104,'high':104}
    result = {'status':'POST_HOC_DESCRIPTIVE_CROSSCHECK_PASS','not_confirmatory':True,
        'definitions_file_sha256':digest(Path(__file__).with_name('analysis-plan.txt')),
        'source_manifest_sha256':digest(p/'manifest.json'),'source_files':{n:digest(p/n) for n in ('cases.json','plan.json','responses.jsonl','expected-analysis.json','audit-summary.json')},
        'case_count':312,'groups':counts,'group_case_percentages':{k:100*v/312 for k,v in counts['denominator_group'].items()},
        'checks':{'full_package_manifest_verified':True,'exact_four_policy_vs_signal_minima':312,
                  'neutral_bodies_checked':len(seen_bodies),'response_vs_case_grid_aggregation':True,
                  'audited_neutral_arm_counts_matched':6,'all_missing_cells_retained':True},
        'rows':check_rows,'cases':list(features.values()),
        'interpretation':'Descriptive associations only. These case attributes are not validated numerical-difficulty measures and do not identify task engagement, attention, reasoning, or cue substitution.'}
    expected = load(Path(__file__).with_name('expected.json'))
    if result != expected:
        raise ValueError('Reproduced diagnostic differs from the retained expected result')
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'numerical-format-results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('OFFLINE_REPRODUCTION_PASS: all 3744 neutral planned cells and all 36 descriptive rows match exactly')
    print('CASE_GROUPS',counts)
    for row in check_rows:
        if row['condition']=='neutral_2':
            print(row['model_id'],row['group_variable'],row['group'],f"{row['errors']}/{row['valid']}",
                  f"{100*row['observed_error_rate']:.1f}%",f"missing={row['missing']}",
                  '['+', '.join(f'{100*x:.2f}%' for x in row['full_plan_error_bounds'])+']')

if __name__ == '__main__':
    main()
