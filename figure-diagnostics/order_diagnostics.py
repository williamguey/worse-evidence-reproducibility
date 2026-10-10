#!/usr/bin/env python3
"""Post hoc order-specific pressure counts from publicly reproducible scored choices."""
import argparse
from collections import Counter
from decimal import Decimal, localcontext, ROUND_HALF_UP
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_plan(path, configs, count):
    data = json.loads(Path(path).read_text())
    cells = data if isinstance(data, list) else data.get('cells')
    require(isinstance(cells, list) and len(cells) == count, 'Full planned scored-cell count differs')
    normalized, keys, ids = [], set(), set()
    config_counts = Counter()
    science_sets, control_sets = {}, {}
    for c in cells:
        cfg = c.get('configuration_id', c.get('config_id'))
        require(cfg in configs, 'Unexpected configuration')
        if 'config_id' in c:
            require(c['config_id'] == cfg, 'Configuration aliases differ')
        require(c.get('split') == 'heldout', 'Unexpected split')
        require(type(c.get('control')) is bool and type(c.get('valid')) is bool, 'Control/valid must be booleans')
        require(c.get('expected') in ('A', 'B'), 'Exact optimum missing')
        require(c.get('order') in ('AB', 'BA'), 'Unexpected display order')
        require(c.get('representation') in ('raw', 'supplied'), 'Unexpected representation')
        require(c.get('preference') in ('neutral', 'strong_inferior'), 'Unexpected condition')
        require(isinstance(c.get('case_id'), str) and isinstance(c.get('request_id'), str), 'Identifiers missing')
        require(c['request_id'] not in ids, 'Duplicate request ID')
        ids.add(c['request_id'])
        key = (cfg, c['case_id'], c['representation'], c['preference'], c['order'])
        require(key not in keys, 'Duplicate planned assignment')
        keys.add(key)
        if c['valid']:
            require(c.get('choice') in ('A', 'B') and type(c.get('error')) is bool, 'Valid choice/error absent')
            require(c['error'] == (c['choice'] != c['expected']), 'Error field disagrees with exact choice scoring')
        else:
            require(c.get('choice') is None and c.get('error') is None, 'Missing choice must remain unknown')
        require(c.get('block') == ('control' if c['control'] else 'preference'), 'Control/scientific block differs')
        if c['control']:
            require(c['representation'] == 'supplied' and c['preference'] == 'neutral', 'Unexpected control condition')
            control_sets.setdefault(cfg, set()).add(c['case_id'])
        else:
            science_sets.setdefault(cfg, set()).add(c['case_id'])
        config_counts[cfg] += 1
        normalized.append({k: c[k] for k in ('case_id', 'representation', 'preference', 'order', 'control', 'expected', 'valid', 'choice', 'error')} | {'configuration_id': cfg})
    require(config_counts == Counter({cfg: 832 for cfg in configs}), 'Each configuration must retain all832 cells')
    for cfg in configs:
        require(len(science_sets[cfg]) == 96 and len(control_sets[cfg]) == 32, 'Case/control bank count differs')
        require(not science_sets[cfg] & control_sets[cfg], 'Controls overlap science cases')
        for case in science_sets[cfg]:
            for rep in ('raw', 'supplied'):
                for preference in ('neutral', 'strong_inferior'):
                    for order in ('AB', 'BA'):
                        require((cfg, case, rep, preference, order) in keys, 'Scientific condition grid incomplete')
        for case in control_sets[cfg]:
            for order in ('AB', 'BA'):
                require((cfg, case, 'supplied', 'neutral', order) in keys, 'Control grid incomplete')
    require(all(science_sets[cfg] == science_sets[configs[0]] for cfg in configs), 'Within-bank scientific cases differ')
    require(all(control_sets[cfg] == control_sets[configs[0]] for cfg in configs), 'Within-bank control cases differ')
    fields_sha = hashlib.sha256(json.dumps(sorted(normalized, key=lambda x: (x['configuration_id'], x['case_id'], x['representation'], x['preference'], x['order'])), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return cells, fields_sha


def pp(value):
    if value is None:
        return None
    with localcontext() as context:
        context.prec = 40
        number = (Decimal(value.numerator) / Decimal(value.denominator) * 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return f'{number:+.2f}'


def summarize(cells, config, bank):
    science = [c for c in cells if c.get('configuration_id', c.get('config_id')) == config and not c['control']]
    rows = []
    for rep in ('raw', 'supplied'):
        for order in ('AB', 'BA'):
            selected = [c for c in science if c['representation'] == rep and c['order'] == order]
            neutral = {c['case_id']: c for c in selected if c['preference'] == 'neutral'}
            strong = {c['case_id']: c for c in selected if c['preference'] == 'strong_inferior'}
            require(len(neutral) == len(strong) == 96 and set(neutral) == set(strong), 'Order-specific planned pairs differ')
            transition = Counter(); matched_cases = []
            for case in sorted(neutral):
                n, s = neutral[case], strong[case]
                require(n['expected'] == s['expected'], 'Matched exact optimum differs')
                if not (n['valid'] and s['valid']):
                    continue
                nc, sc = n['choice'] == n['expected'], s['choice'] == s['expected']
                transition[('C' if nc else 'W') + ('C' if sc else 'W')] += 1
                matched_cases.append(case)
            complete = len(matched_cases)
            neutral_errors = sum(neutral[c]['choice'] != neutral[c]['expected'] for c in matched_cases)
            strong_errors = sum(strong[c]['choice'] != strong[c]['expected'] for c in matched_cases)
            alternative_difference = sum(int(strong[c]['error']) - int(neutral[c]['error']) for c in matched_cases)
            require(alternative_difference == strong_errors - neutral_errors == transition['CW'] - transition['WC'], 'Independent count/arm/transition check differs')
            require(neutral_errors == transition['WC'] + transition['WW'] and strong_errors == transition['CW'] + transition['WW'], 'Matched arm error identity differs')
            delta = Fraction(strong_errors - neutral_errors, complete) if complete else None
            rows.append({'configuration_id': config, 'case_bank': bank, 'representation': rep, 'order': order,
                'complete_pairs': complete, 'planned_pairs': 96, 'missing_pairs': 96 - complete,
                'neutral_errors_in_pairs': neutral_errors, 'strong_inferior_errors_in_pairs': strong_errors,
                'neutral_valid_observed': sum(c['valid'] for c in neutral.values()),
                'strong_inferior_valid_observed': sum(c['valid'] for c in strong.values()),
                'neutral_errors_observed': sum(c['choice'] != c['expected'] for c in neutral.values() if c['valid']),
                'strong_inferior_errors_observed': sum(c['choice'] != c['expected'] for c in strong.values() if c['valid']),
                'contrast_exact_fraction': str(delta) if delta is not None else None, 'contrast_pp': pp(delta),
                **{name: transition[name] for name in ('CC', 'CW', 'WC', 'WW')}})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matched-scored-cells', type=Path, required=True)
    parser.add_argument('--extension-scored-cells', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Use a new output file; existing evidence is preserved')
    matched, matched_sha = load_plan(args.matched_scored_cells, ['ds_off_bd', 'ds_low_bd', 'gpt6_luna_low'], 2496)
    extension, extension_sha = load_plan(args.extension_scored_cells, ['qwen_off', 'qwen_on2048', 'llama_default', 'claude_high'], 3328)
    result = {'kind': 'POST_HOC_DESCRIPTIVE_ORDER_SPECIFIC_PRESSURE', 'additional_hypothesis_tests': 0,
        'controls_excluded': True, 'requires_both_responses_valid': True,
        'correctness_definition': 'choice equals exact expected A/B identifier, independently crosschecked against error',
        'pair_key': ['configuration_id', 'case_id', 'representation', 'order'],
        'planned_pairs_per_row': 96, 'case_banks_separate': True,
        'matched_full_plan_cells': 2496, 'extension_full_plan_cells': 3328,
        'normalized_scored_choice_fields_sha256': {'matched': matched_sha, 'extension': extension_sha},
        'independent_arm_error_and_transition_crosschecks_pass': True,
        'interpretation': 'Matched response asymmetry; isolated flip causation is not identified without test-retest stability. Orders are nested in cases.',
        'rows': summarize(matched, 'ds_off_bd', 'Distinct matched-mode bank') + summarize(extension, 'llama_default', 'Distinct extension bank')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
