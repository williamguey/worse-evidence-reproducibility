"""V11 fixed-plan, whole-case inference; no network or receipt parsing.

Directional primaries use a fixed six-point nonnegative betting mixture on
the lower missingness envelope. Independence is across whole cases, not
requests. AM-GM gives E-value validity under a weak average-mean null, including
nonidentical stratum means. Student t quantities are approximation diagnostics
only: sparse asymmetric lattice nulls demonstrate that they are unsuitable as
confirmatory tests. No bootstrap/sign-flip p-values are used.
"""
from __future__ import annotations

import argparse
import functools
import json
import math
import statistics
from fractions import Fraction
from pathlib import Path

MODELS = ('llama_default', 'deepseek_off', 'luna_off')
CONDITIONS = ('neutral_1', 'neutral_2', 'bundle_bad', 'bundle_good',
              'preference_bad_1', 'preference_bad_2', 'sponsor_bad',
              'commitment_bad', 'guard_bundle_bad', 'guard_neutral',
              'simple_neutral', 'simple_bundle_bad')
ORDERS = ('AB', 'BA')
PRIMARY = {
    'bundle_worsening': {'bundle_bad': 1, 'neutral_2': -1},
    'endorsement_direction': {'bundle_bad': 1, 'bundle_good': -1},
    'guard_attenuation': {'bundle_bad': 1, 'neutral_2': -1,
                          'guard_bundle_bad': -1, 'guard_neutral': 1},
}
SECONDARY = {
    **{c + '_worsening': {c: 1, 'neutral_2': -1} for c in
       ('preference_bad_1', 'preference_bad_2', 'sponsor_bad', 'commitment_bad')},
    'preference_paraphrase_difference': {'preference_bad_1': 1, 'preference_bad_2': -1},
    'guard_residual': {'guard_bundle_bad': 1, 'guard_neutral': -1},
    'simplification_attenuation': {'bundle_bad': 1, 'neutral_2': -1,
                                 'simple_bundle_bad': -1, 'simple_neutral': 1},
    'simplified_worsening': {'simple_bundle_bad': 1, 'simple_neutral': -1},
    'neutral_complexity_difference': {'neutral_2': 1, 'simple_neutral': -1},
    'neutral_repeat_difference': {'neutral_1': 1, 'neutral_2': -1},
}
ALPHA = .05
FAMILY_SIZE = 9
BETTING_RHOS = (.1, .2, .4, .6, .8, 1.)
REGRET_BOUND = 32.5  # fixed generator max terminal loss 30 + max acquisition 2.5


def _beta_fraction(a, b, x):
    """Continued fraction for the regularized incomplete beta; finite guard."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1., a - 1.
    c, d = 1., 1. - qab * x / qap
    d = 1. / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 501):
        m2 = 2 * m
        for aa in (m * (b-m) * x / ((qam+m2)*(a+m2)),
                   -(a+m) * (qab+m) * x / ((a+m2)*(qap+m2))):
            d, c = 1. + aa*d, 1. + aa/c
            d = 1. / (d if abs(d) > tiny else tiny)
            c = c if abs(c) > tiny else tiny
            delta = d*c
            h *= delta
        if abs(delta-1.) < 3e-14:
            return h
    raise ArithmeticError('Incomplete beta failed to converge')


def _ibeta(a, b, x):
    if x <= 0: return 0.
    if x >= 1: return 1.
    bt = math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)
                  + a*math.log(x) + b*math.log1p(-x))
    if x < (a+1)/(a+b+2):
        return bt * _beta_fraction(a, b, x) / a
    return 1. - bt * _beta_fraction(b, a, 1.-x) / b


def t_survival(t, df):
    if df <= 0: raise ValueError('Positive t degrees of freedom required')
    tail = .5 * _ibeta(df/2., .5, df/(df+t*t))
    return tail if t >= 0 else 1.-tail


@functools.lru_cache(None)
def t_critical(alpha, df):
    if not 0 < alpha < .5: raise ValueError('Invalid tail alpha')
    lo, hi = 0., 1.
    while t_survival(hi, df) > alpha: hi *= 2
    for _ in range(70):
        mid = (lo+hi)/2
        if t_survival(mid, df) > alpha: lo = mid
        else: hi = mid
    return (lo+hi)/2


def holm(pvalues, alpha=ALPHA):
    """All planned endpoints retained; adjusted values are monotone in rank."""
    if any(not 0 <= p <= 1 for p in pvalues): raise ValueError('Invalid p-value')
    adjusted = [1.] * len(pvalues)
    running = 0.
    for rank, index in enumerate(sorted(range(len(pvalues)), key=pvalues.__getitem__)):
        running = max(running, (len(pvalues)-rank)*pvalues[index])
        adjusted[index] = min(1., running)
    return adjusted, [p <= alpha for p in adjusted]


def log_mixture(values, mu, lower):
    """Equal fixed weights, no outcome-adaptive betting or selected lambda.

    H0: average E(X_i)<=mu, X_i>=lower. For rho in [0,1], independence and
    AM-GM bound E product(1+rho*(X_i-mu)/(mu-lower)) by 1, even if individual
    means exceed mu. A fixed mixture of these products remains an E-value.
    """
    if mu < lower: raise ValueError('Null mean below support')
    if mu == lower:
        return math.inf if any(x > lower for x in values) else 0.
    logs = []
    for rho in BETTING_RHOS:
        total = 0.
        for x in values:
            factor = 1. + rho*(x-mu)/(mu-lower)
            if factor <= 0:
                total = -math.inf
                break
            total += math.log(factor)
        logs.append(total)
    maximum = max(logs)
    if maximum == -math.inf: return -math.inf
    return maximum + math.log(sum(math.exp(v-maximum) for v in logs)/len(logs))


def _lower_bound(values, lower, upper, alpha):
    """Invert monotone fixed-mixture tests; returned lower endpoint is closed."""
    target = -math.log(alpha)
    if log_mixture(values, lower, lower) < target: return lower
    lo, hi = lower, upper
    for _ in range(65):
        mid = (lo+hi)/2.
        if log_mixture(values, mid, lower) >= target: lo = mid
        else: hi = mid
    return (lo+hi)/2.


def mean_inference(values, bounds, alpha=ALPHA):
    """Finite-sample weak-mean inference under independent whole cases."""
    n = len(values)
    if len(bounds) != n: raise ValueError('Support length mismatch')
    if not n:
        return {'mean': None, 'ci': None, 'positive_p': 1., 'method': 'no_cases'}
    for x, (lo, hi) in zip(values, bounds):
        if not all(map(math.isfinite, (x, lo, hi))) or not lo <= x <= hi:
            raise ValueError('Nonfinite value or support violation')
    mean = statistics.fmean(values)
    lower, upper = min(b[0] for b in bounds), max(b[1] for b in bounds)
    support = [statistics.fmean(b[0] for b in bounds), statistics.fmean(b[1] for b in bounds)]
    sd = statistics.stdev(values) if n > 1 else 0.
    log_e = log_mixture(values, 0., lower) if lower <= 0 else math.inf
    p = min(1., math.exp(-log_e)) if log_e > 0 else 1.
    ci = [max(support[0], _lower_bound(values, lower, upper, alpha/2)),
          min(support[1], -_lower_bound([-x for x in values], -upper, -lower, alpha/2))]
    diagnostic = None
    if n > 1 and sd > 1e-12:
        se = sd/math.sqrt(n)
        radius = t_critical(alpha/2., n-1)*se
        diagnostic = {'ci': [max(support[0],mean-radius), min(support[1],mean+radius)],
                      'positive_p': t_survival(mean/se,n-1) if mean>0 else 1.,
                      'interpretation': 'approximation_only_not_confirmatory'}
    return {'n_cases': n, 'mean': mean, 'sd': sd, 'ci': ci,
            'positive_p': p, 'log_e_at_zero': log_e,
            'method': 'finite_fixed_mixture_Evalue_AMGM',
            'approximate_t_diagnostic': diagnostic}


def envelopes(cases, model, coefficients, errors, gaps=None):
    lo, hi, supports, complete = [], [], [], []
    for case in cases:
        lower = upper = 0.
        known = True
        weight = 1. if gaps is None else gaps[case]
        support_lo = sum(min(0, c) for c in coefficients.values()) * weight
        support_hi = sum(max(0, c) for c in coefficients.values()) * weight
        for condition, coefficient in coefficients.items():
            for order in ORDERS:
                value = errors.get((case, model, condition, order))
                if value is None:
                    known = False
                    lower += min(0, coefficient)*weight/2
                    upper += max(0, coefficient)*weight/2
                else:
                    lower += coefficient*value*weight/2
                    upper += coefficient*value*weight/2
        lo.append(lower); hi.append(upper)
        supports.append((support_lo, support_hi) if gaps is None else
                        (sum(min(0,c) for c in coefficients.values())*REGRET_BOUND,
                         sum(max(0,c) for c in coefficients.values())*REGRET_BOUND))
        complete.append(known)
    return lo, hi, supports, complete


def contrast(cases, model, coefficients, errors, gaps=None):
    lo, hi, supports, complete = envelopes(cases, model, coefficients, errors, gaps)
    lower = mean_inference(lo, supports)
    upper = mean_inference(hi, supports)
    simultaneous_lower = mean_inference(lo, supports, ALPHA/FAMILY_SIZE)
    simultaneous_upper = mean_inference(hi, supports, ALPHA/FAMILY_SIZE)
    selected = [i for i, ok in enumerate(complete) if ok]
    descriptive = mean_inference([lo[i] for i in selected], [supports[i] for i in selected])
    return {'coefficients': coefficients, 'planned_cases': len(cases),
            'complete_cases': len(selected), 'complete_case_descriptive': descriptive,
            'identification_interval': [lower['mean'], upper['mean']],
            'nominal_95_envelope_ci': [lower['ci'][0], upper['ci'][1]] if cases else None,
            'family_95_envelope_ci': [simultaneous_lower['ci'][0], simultaneous_upper['ci'][1]] if cases else None,
            'positive_p': lower['positive_p'], 'p_method': lower['method'],
            'missingness_policy': 'all_cases_lower_envelope_directional_test'}


def secondary_contrast(*args, **kwargs):
    """Only nominal intervals; no simultaneous-secondary-family claim."""
    result = contrast(*args, **kwargs)
    result.pop('family_95_envelope_ci')
    result['interval_scope'] = 'nominal_95_secondary_only'
    return result


def analyze(plan, scored, models=MODELS, gaps=None):
    """Plan is authoritative; absent or null scored errors are unavailable."""
    by_id = {}
    scientific = {}
    for row in plan:
        rid = row['request_id']
        if rid in by_id: raise ValueError('Duplicate planned request')
        by_id[rid] = row
        if row['kind'] == 'science':
            key = tuple(row[k] for k in ('case_id', 'model_id', 'condition', 'order'))
            if key in scientific: raise ValueError('Duplicate scientific cell')
            scientific[key] = rid
    cases = sorted({k[0] for k in scientific})
    expected = {(c, m, a, o) for c in cases for m in models for a in CONDITIONS for o in ORDERS}
    if not cases or set(scientific) != expected: raise ValueError('Incomplete or unexpected scientific plan')
    errors, seen = {}, set()
    for row in scored:
        rid = row['request_id']
        if rid not in by_id or rid in seen: raise ValueError('Unexpected or duplicate scored request')
        seen.add(rid)
        p = by_id[rid]
        for key in ('case_id', 'model_id', 'condition', 'order', 'kind'):
            if key in row and row[key] != p[key]: raise ValueError('Scored identity mismatch')
        value = row.get('error')
        if value is not None and (type(value) not in (int, float) or value not in (0, 1)):
            raise ValueError('Error must be 0, 1, or null')
        if p['kind'] == 'science':
            errors[tuple(p[k] for k in ('case_id', 'model_id', 'condition', 'order'))] = value
    primaries, secondary, stability = [], [], []
    for model in models:
        for name, coefficients in PRIMARY.items():
            primaries.append({'model_id': model, 'endpoint': name,
                              **contrast(cases, model, coefficients, errors)})
        for name, coefficients in SECONDARY.items():
            secondary.append({'model_id': model, 'endpoint': name,
                              'interpretation': 'secondary_nominal_CI_not_confirmatory',
                              **secondary_contrast(cases, model, coefficients, errors)})
        stable = [c for c in cases if all(errors.get((c, model, 'neutral_1', o)) == 0 for o in ORDERS)]
        stability.append({'model_id': model, 'selected_cases': len(stable),
                          'selection': 'both_neutral_1_orders_correct; never_neutral_2',
                          'interpretation': 'conditional_selected_sample_diagnostic_no_population_or_latent_certainty_claim',
                          **secondary_contrast(stable, model, PRIMARY['bundle_worsening'], errors)})
    if len(primaries) != FAMILY_SIZE: raise ValueError('Frozen family must contain nine endpoints')
    adjusted, rejected = holm([p['positive_p'] for p in primaries])
    for row, p, reject in zip(primaries, adjusted, rejected):
        row['holm9_p'], row['reject_positive_holm9'] = p, reject
    regret = []
    if gaps is not None:
        if set(gaps) != set(cases) or any(not math.isfinite(g) or not 0 < g <= REGRET_BOUND for g in gaps.values()):
            raise ValueError('Every main case needs its positive audited regret gap')
        for model in models:
            regret.append({'model_id': model, 'endpoint': 'bundle_regret_worsening',
                           'interpretation': 'secondary_nominal_CI_not_confirmatory',
                           **secondary_contrast(cases, model, PRIMARY['bundle_worsening'], errors, gaps)})
    arm_summaries = []
    for model in models:
        for condition in CONDITIONS:
            values = [errors.get((c, model, condition, o)) for c in cases for o in ORDERS]
            known = [v for v in values if v is not None]
            wrong = sum(known)
            arm_summaries.append({'model_id': model, 'condition': condition,
                                  'planned': len(values), 'valid': len(known),
                                  'errors': wrong, 'missing': len(values)-len(known),
                                  'full_plan_error_rate_bounds': [wrong/len(values),
                                     (wrong+len(values)-len(known))/len(values)]})
    return {'protocol': 'H01_V11', 'case_count': len(cases), 'models': list(models),
            'unit': 'whole_numerical_case; two_orders_nested', 'primary_family_size': FAMILY_SIZE,
            'assumptions': 'independent whole cases; fixed-mixture AM-GM weak-average-mean validity including nonidentical stratum means; arbitrary within-case dependence; no protection from shared-service dependence',
            'arm_summaries': arm_summaries, 'primary': primaries, 'secondary': secondary, 'stability': stability, 'regret': regret}


def read_rows(path):
    raw = Path(path).read_text()
    if raw.lstrip().startswith('['): return json.loads(raw)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', required=True)
    parser.add_argument('--scored', required=True)
    parser.add_argument('--cases')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    gaps = None
    if args.cases:
        cases = json.loads(Path(args.cases).read_text())
        gaps = {c['case_id']: float(Fraction(c['oracle']['regret_of_wrong_report'])) for c in cases}
    result = analyze(read_rows(args.plan), read_rows(args.scored), gaps=gaps)
    Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
