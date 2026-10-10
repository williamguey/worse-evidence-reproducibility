#!/usr/bin/env python3
"""Read-only post hoc gap-band table from the published H01 repository.

Python 3.9+ standard library; no network calls or scientific-source imports.
Reads public scored choices/case banks, and writes only the requested JSON.
Frozen validity is retained. No tests, p-values, intervals, raw reasoning,
accounting fields, or baseline-success subgroup enter this companion.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

MODEL = 'deepseek/deepseek-v4-pro-0813'
REPRESENTATIONS = ('raw', 'supplied')
PREFERENCES = ('neutral', 'strong_inferior')
ORDERS = ('AB', 'BA')
BANDS = ('low', 'moderate', 'high')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def gap_band(normalized):
    return 'low' if normalized <= Fraction(1, 10) else ('moderate' if normalized <= Fraction(7, 20) else 'high')


def oracle(case):
    """Independent rational optimum and normalized gap from public parameters."""
    p = case['parameters']
    prevalence = Fraction(p['prior_state1'])
    loss0, loss1 = Fraction(p['loss_ACT_state0']), Fraction(p['loss_WAIT_state1'])
    totals = {}
    for label, report in p['reports'].items():
        sensitivity, specificity = Fraction(report['sensitivity']), Fraction(report['specificity'])
        totals[label] = Fraction(report['cost']) + min((1-prevalence)*(1-specificity)*loss0, prevalence*sensitivity*loss1) + min((1-prevalence)*specificity*loss0, prevalence*(1-sensitivity)*loss1)
    require(set(totals) == {'A', 'B'} and totals['A'] != totals['B'], 'Invalid/tied public case')
    optimum = min(totals, key=totals.get)
    gap = abs(totals['A']-totals['B'])
    normalized = gap / min((1-prevalence)*loss0, prevalence*loss1)
    require(optimum == case['oracle']['optimal_report'], 'Public oracle optimum mismatch')
    require(gap == Fraction(case['oracle']['regret_of_wrong_report']), 'Public oracle gap mismatch')
    require(normalized == Fraction(case['oracle']['normalized_regret']), 'Public normalized gap mismatch')
    require(gap_band(normalized) == case['generation']['strata']['regret'], 'Frozen gap-band mismatch')
    return optimum, gap, normalized, gap_band(normalized)


def tabulate(cohort, cells, case_list):
    original = cohort == 'Original H01'
    cases = {case['case_id']: oracle(case) for case in case_list}
    require(len(cases) == len(case_list) == 96, 'Expected 96 unique public cases')
    lookup = {}
    for row in cells:
        if original:
            condition = row['condition']
            if row['model'] != MODEL or condition[0] != 'preference' or condition[3] not in PREFERENCES:
                continue
            require(condition[2] == 'none' and not row['control'], 'Unexpected original preference cell')
            representation, preference = condition[1], condition[3]
        else:
            if row['config_id'] != 'ds_off_bd' or row['control']:
                continue
            require(row['block'] == 'preference' and row['model_id'] == MODEL, 'Unexpected follow-up cell')
            representation, preference = row['representation'], row['preference']
        case_id, order = row['case_id'], row['order']
        require(case_id in cases and representation in REPRESENTATIONS and preference in PREFERENCES and order in ORDERS, 'Unexpected planned cell')
        expected, gap, normalized, _ = cases[case_id]
        require(row['expected'] == expected and Fraction(row['gap']) == gap and Fraction(row['normalized_gap']) == normalized, 'Scored case metadata mismatch')
        key = (case_id, representation, preference, order)
        require(key not in lookup, 'Duplicate scientific cell')
        error = None
        if row['valid']:
            require(row['choice'] in ('A', 'B'), 'Valid row lacks A/B choice')
            error = int(row['choice'] != expected)
            require(error == row['error'], 'Scored error disagrees with independent oracle')
        lookup[key] = (bool(row['valid']), error)
    require(len(lookup) == 96 * 2 * 2 * 2, 'Incomplete public preference plan')
    rows = []
    for representation in REPRESENTATIONS:
        for band in BANDS:
            ids = sorted(key for key, value in cases.items() if value[3] == band)
            require(len(ids) == 32, 'Expected 32 cases per frozen gap band')
            neutral, strong, differences = [], [], []
            for case_id in ids:
                n = [lookup[(case_id, representation, 'neutral', order)] for order in ORDERS]
                s = [lookup[(case_id, representation, 'strong_inferior', order)] for order in ORDERS]
                neutral.extend(n)
                strong.extend(s)
                if all(value[0] for value in n+s):
                    differences.append(Fraction(sum(p[1]-q[1] for q, p in zip(n, s)), 2))
            mean = sum(differences, Fraction(0))/len(differences) if differences else None
            rows.append({'cohort': cohort, 'representation': representation, 'gap_band': band,
                         'planned_cases': len(ids), 'both_order_complete_cases': len(differences),
                         'planned_responses_per_arm': len(neutral),
                         'neutral_valid_responses': sum(valid for valid, _ in neutral),
                         'neutral_errors': sum(error for valid, error in neutral if valid),
                         'strong_inferior_valid_responses': sum(valid for valid, _ in strong),
                         'strong_inferior_errors': sum(error for valid, error in strong if valid),
                         'both_order_fullcase_contrast_exact': str(mean) if mean is not None else None,
                         'both_order_fullcase_contrast_pp': float(100*mean) if mean is not None else None})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repository', type=Path, required=True, help='Published repository root or extracted followup-reproducibility directory')
    parser.add_argument('--output', type=Path, required=True, help='JSON output outside the input repository/bundle')
    args = parser.parse_args()
    repository = args.repository.resolve()
    bundle = repository / 'followup-reproducibility' if (repository / 'followup-reproducibility/original').is_dir() else repository
    output = args.output.resolve()
    require(output != repository and repository not in output.parents and bundle not in output.parents, 'Choose an output outside the input repository/bundle')
    paths = {'original_scoring': bundle/'original/results/heldout/analysis.json',
             'original_cases': bundle/'original/data/heldout/cases.json',
             'followup_scoring': bundle/'baidu/results/new-scored-cells.json',
             'followup_cases': bundle/'baidu/data/heldout/cases.json'}
    for name, path in paths.items():
        require(path.is_file(), 'Missing public scientific input: '+name)
    original, followup = read(paths['original_scoring']), read(paths['followup_scoring'])
    rows = tabulate('Original H01', original['cells'], read(paths['original_cases'])) + tabulate('Baidu follow-up', followup, read(paths['followup_cases']))
    result = {'version': 'h01-public-gap-band-description-v1',
              'role': 'post hoc descriptive table using prespecified numerical gap bands',
              'gap_definition': 'inferior-minus-optimal report total-cost gap / pre-report Bayes terminal risk',
              'gap_bands': {'low':'(0,1/10]', 'moderate':'(1/10,7/20]', 'high':'(7/20,infinity)'},
              'contrast': 'Average strong-inferior-minus-neutral binary error over AB/BA within each case, then equally average cases complete in all four responses within each band.',
              'unit': '32 numerical cases per band and cohort; two orders per case; cohorts are separate.',
              'interpretation': 'Numerical gap is not validated task difficulty. This table adds no tests or intervals and does not identify knowledge, baseline-adjusted susceptibility or provider causal effects.',
              'verification': {'independent_rational_oracle_cases':192, 'selected_planned_scored_cells':1536,
                               'scored_choices_errors_and_frozen_bands_match_oracle':True},
              'public_input_hashes': {name:{'path':path.relative_to(bundle).as_posix(), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for name,path in paths.items()},
              'rows':rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('PASS: wrote 12 descriptive rows; verified 192 rational case optima and 1,536 selected scored cells.')


if __name__ == '__main__':
    main()
