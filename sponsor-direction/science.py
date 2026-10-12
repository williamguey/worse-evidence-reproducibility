"""Independent offline V12 calculations, with no network or collection imports."""
import json
import math
from fractions import Fraction
from statistics import fmean

ARMS = ('neutral', 'sponsor_bad', 'sponsor_good')
ORDERS = ('AB', 'BA')
ENDPOINTS = (('endorsement_direction', 'sponsor_bad', 'sponsor_good'),
             ('sponsor_worsening', 'sponsor_bad', 'neutral'),
             ('sponsor_improvement', 'neutral', 'sponsor_good'))
RHOS = (.1, .2, .4, .6, .8, 1.)


def oracle(case):
    """Compute two per-signal Bayes risks directly, using exact rationals."""
    p = case['parameters']; prior = Fraction(p['prior_state1'])
    wrong_act = Fraction(p['loss_ACT_state0']); wrong_wait = Fraction(p['loss_WAIT_state1'])
    totals = {}
    for label in ('A', 'B'):
        report = p['reports'][label]
        sens, spec = Fraction(report['sensitivity']), Fraction(report['specificity'])
        plus = min((1-prior)*(1-spec)*wrong_act, prior*sens*wrong_wait)
        minus = min((1-prior)*spec*wrong_act, prior*(1-sens)*wrong_wait)
        totals[label] = Fraction(report['cost']) + plus + minus
    if totals['A'] == totals['B']: raise ValueError('Oracle tie')
    return min(totals, key=totals.get), totals, abs(totals['A']-totals['B'])


def parse_choice(data):
    choices = data.get('choices')
    if not isinstance(choices, list) or len(choices) != 1: raise ValueError('Choice count')
    choice = choices[0]; message = choice.get('message') or {}
    if choice.get('finish_reason') != 'stop' or message.get('refusal'): raise ValueError('Response incomplete/refused')
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs): raise ValueError('Duplicate JSON key')
        return result
    value = json.loads(message['content'], object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {'choice'} or value['choice'] not in ('A', 'B'):
        raise ValueError('Response schema')
    return value['choice']


def log_e(values, candidate):
    """Independent fixed six-product implementation for support [-1, 1]."""
    if candidate == -1: return math.inf if any(x > -1 for x in values) else 0.
    products = []
    for rho in RHOS:
        factors = [1-rho + rho*(value+1)/(candidate+1) for value in values]
        products.append(-math.inf if any(v <= 0 for v in factors) else math.fsum(math.log(v) for v in factors))
    peak = max(products)
    if peak == -math.inf: return peak
    return peak + math.log(math.fsum(math.exp(value-peak) for value in products)/6)


def lower_bound(values, tail_alpha):
    cutoff = -math.log(tail_alpha)
    if log_e(values, -1) < cutoff: return -1.
    low, high = -1., 1.
    for _ in range(80):
        middle = (low+high)/2
        if log_e(values, middle) >= cutoff: low = middle
        else: high = middle
    return (low+high)/2


def inference(lower, upper, complete):
    if len(lower) != len(upper) or not lower: raise ValueError('Missing support')
    if any(not -1 <= lo <= hi <= 1 for lo, hi in zip(lower, upper)): raise ValueError('Support violation')
    log = log_e(lower, 0.)
    p = math.exp(-log) if log > 0 else 1.
    def interval(alpha):
        return [lower_bound(lower, alpha/2), -lower_bound([-x for x in upper], alpha/2)]
    known = [value for value, present in zip(lower, complete) if present]
    return {'planned_cases':len(lower), 'complete_cases':sum(complete),
            'complete_case_mean_descriptive':fmean(known) if known else None,
            'identification_interval':[fmean(lower), fmean(upper)],
            'nominal_95_envelope_ci':interval(.05), 'family_95_envelope_ci':interval(.05/3),
            'positive_p':p}


def calculate(cases, plan, outcomes):
    ids = sorted(case['case_id'] for case in cases)
    if len(set(ids)) != len(ids) or not ids: raise ValueError('Duplicate/absent cases')
    truths = {case['case_id']:oracle(case)[0] for case in cases}
    expected = {(case, arm, order) for case in ids for arm in ARMS for order in ORDERS}
    pmap = {}; cells = {}
    for entry in plan:
        rid = entry['request_id']; cell = tuple(entry[k] for k in ('case_id', 'condition', 'order'))
        if rid in pmap or cell in cells or cell not in expected: raise ValueError('Unexpected/duplicate planned cell')
        pmap[rid] = entry; cells[cell] = rid
    if set(cells) != expected: raise ValueError('Incomplete factorial plan')
    omap = {}
    for value in outcomes:
        rid = value['request_id']
        if rid not in pmap or rid in omap: raise ValueError('Unexpected/duplicate outcome')
        omap[rid] = value
    if set(omap) != set(pmap): raise ValueError('Missing planned outcome, including unavailable cell')
    errors = {}; scored = []
    for entry in plan:
        rid = entry['request_id']; value = omap[rid]; choice = value.get('choice'); state = value['state']
        if state == 'valid_unscored':
            if choice not in ('A', 'B'): raise ValueError('Valid outcome lacks choice')
            error = int(choice != truths[entry['case_id']])
        elif state.startswith('missing_'):
            if choice is not None: raise ValueError('Missing outcome carries a choice')
            error = None
        else: raise ValueError('Unknown outcome state')
        cell = tuple(entry[k] for k in ('case_id', 'condition', 'order')); errors[cell] = error
        scored.append({'request_id':rid, **dict(zip(('case_id','condition','order'),cell)), 'state':state, 'choice':choice, 'error':error})
    endpoints = []
    for name, positive, negative in ENDPOINTS:
        lower, upper, complete = [], [], []
        for case in ids:
            lo = hi = 0.; known = True
            for arm, sign in ((positive, 1), (negative, -1)):
                for order in ORDERS:
                    error = errors[(case, arm, order)]
                    if error is None:
                        known = False
                        lo += (-.5 if sign < 0 else 0); hi += (.5 if sign > 0 else 0)
                    else: lo += sign*error/2; hi += sign*error/2
            lower.append(lo); upper.append(hi); complete.append(known)
        endpoints.append({'endpoint':name,'coefficients':{positive:1,negative:-1}, **inference(lower,upper,complete)})
    order = sorted(range(3), key=lambda i:endpoints[i]['positive_p']); largest = 0
    for rank, i in enumerate(order):
        largest = max(largest, (3-rank)*endpoints[i]['positive_p'])
        adjusted = min(1., largest)
        endpoints[i].update(holm3_p=adjusted,reject_positive_holm3=adjusted <= .05)
    summaries = []
    for arm in ARMS:
        for order in ('both', *ORDERS):
            values = [errors[(case,arm,o)] for case in ids for o in (ORDERS if order=='both' else (order,))]
            known = [v for v in values if v is not None]; n = len(values); missing = n-len(known); wrong = sum(known)
            summaries.append({'condition':arm,'order':order,'planned':n,'valid':len(known),'missing':missing,'errors':wrong,
                              'valid_response_error_rate':wrong/len(known) if known else None,
                              'full_plan_error_rate_bounds':[wrong/n,(wrong+missing)/n]})
    return {'case_count':len(ids),'fresh_case_count':0,'primary_family_size':3,'arm_summaries':summaries,'primary':endpoints,
            'technical_quality_passes':all(s['valid']/s['planned'] >= .95 for s in summaries if s['order']=='both'), 'scored':scored}


def compare(expected, observed, path='result', tol=2e-10):
    """Expected structure may be a projection of the more verbose analysis."""
    if isinstance(expected, dict):
        if not isinstance(observed, dict): raise AssertionError(path+': expected mapping')
        for key, value in expected.items():
            if key not in observed: raise AssertionError(path+': missing '+key)
            compare(value, observed[key], path+'.'+key, tol)
    elif isinstance(expected, list):
        if not isinstance(observed,list) or len(expected) != len(observed): raise AssertionError(path+': list shape')
        for index, (a,b) in enumerate(zip(expected,observed)): compare(a,b,path+'['+str(index)+']',tol)
    elif type(expected) in (int,float) and type(observed) in (int,float):
        if not math.isfinite(observed) or abs(expected-observed) > tol*max(1,abs(expected)):
            raise AssertionError(path+': numerical disagreement')
    elif expected != observed or (isinstance(expected,bool) and type(observed) is not bool):
        raise AssertionError(path+': value disagreement')
