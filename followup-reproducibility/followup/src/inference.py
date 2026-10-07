"""Prospectively fixed, missingness-robust inference for the fresh H01 panel.

No network calls and no dependency on discovery outcomes. Independent CASES,
not individual prompts, are the sampling units. Primary p-values combine
Hoeffding and a fixed-grid betting e-test by a prespecified Bonferroni rule;
neither component uses estimated variances or bootstrap calibration.
Bootstrap intervals are explicitly descriptive diagnostics.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from fractions import Fraction
from itertools import product
from pathlib import Path
from typing import Any, Iterable, Mapping

ANALYSIS_VERSION = "h01-fresh-hoeffding-betting-holm4-v4"
ALPHA = 0.05
CONFIGURATION_COUNT = 3
PRIMARY_FAMILY_SIZE = CONFIGURATION_COUNT + 1
PLANNED_CASES = 96
BOOTSTRAP_DRAWS = 5000
BOOTSTRAP_SEED = 2026100642
BETTING_GRID_STEPS = 20
STRATUM_KEYS = ("optimal_cost", "state1_prevalence", "optimal_report")
STRATA = tuple(product(("cheaper", "more_expensive"), ("rare", "common"), ("A", "B")))
ORDERS = ("AB", "BA")
REPRESENTATIONS = ("raw", "supplied")
PREFERENCES = ("neutral", "strong_inferior")
GAPS = ("low", "moderate", "high")


def _exact(value: Any) -> Fraction:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Exact outcome arithmetic requires integers or rational strings")
    return Fraction(value)


def _stat(value: Fraction | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"exact": str(value), "value": float(value)}


def _mean(values: Iterable[Fraction]) -> Fraction | None:
    values = list(values)
    return sum(values, Fraction(0)) / len(values) if values else None


def _stratum(case: Mapping[str, Any]) -> tuple[str, ...]:
    declared = case["generation"]["strata"]
    result = tuple(declared[key] for key in STRATUM_KEYS)
    if result not in STRATA or declared["regret"] not in GAPS:
        raise ValueError("Unknown prospective generation stratum")
    return result


def _case_records(cases: Any) -> list[Mapping[str, Any]]:
    if isinstance(cases, Mapping) and "cases" in cases:
        cases = cases["cases"]
    if isinstance(cases, Mapping):
        return list(cases.values())
    if isinstance(cases, list):
        return cases
    raise ValueError("Cases must be a list or a manifest mapping")


def _cell_key(cell: Mapping[str, Any]) -> tuple[str, ...]:
    return (cell["case_id"], cell["config_id"], cell["representation"],
            cell["preference"], cell["order"])


def validate_inputs(cases: Any, cells: list[Mapping[str, Any]], config_ids: Iterable[str],
                    deepseek_off_id: str, deepseek_on_id: str, *,
                    confirmatory: bool = True) -> tuple[dict[str, Any], dict[tuple[str, ...], Any]]:
    """Require all planned cells; invalid and missing outcomes remain in the panel.

    This checks the analysis interface. The separate material audit must verify
    oracle answers, numeric freshness, independent hash slots, request bodies,
    and receipts; this module does not replace those provenance checks.
    """
    configs = tuple(config_ids)
    if len(configs) != CONFIGURATION_COUNT or len(set(configs)) != CONFIGURATION_COUNT or any(not isinstance(c, str) or not c for c in configs):
        raise ValueError("The prospective V4 panel requires three distinct configuration IDs")
    if deepseek_off_id == deepseek_on_id or not {deepseek_off_id, deepseek_on_id} <= set(configs):
        raise ValueError("Distinct DeepSeek off/on configurations must belong to the panel")
    metadata: dict[str, Any] = {}
    for case in _case_records(cases):
        case_id = case["case_id"]
        if case_id in metadata:
            raise ValueError("Duplicate case ID")
        if case.get("control", False) or case.get("family") == "control":
            continue
        metadata[case_id] = {"case_id": case_id, "stratum": _stratum(case),
                             "gap_band": case["generation"]["strata"]["regret"],
                             "family": case["family"]}
    if not metadata:
        raise ValueError("No scientific cases")
    counts = Counter(meta["stratum"] for meta in metadata.values())
    gap_counts = Counter((*meta["stratum"], meta["gap_band"]) for meta in metadata.values())
    if confirmatory and (len(metadata) != PLANNED_CASES or set(counts) != set(STRATA)
                         or set(counts.values()) != {12}
                         or set(gap_counts) != {(*s, g) for s in STRATA for g in GAPS}
                         or set(gap_counts.values()) != {4}):
        raise ValueError("Main inference requires exactly 96 cases: 12 per analysis stratum, four per gap band")
    lookup: dict[tuple[str, ...], Any] = {}
    for cell in cells:
        if not isinstance(cell.get("control"), bool):
            raise ValueError("Every scored cell needs a Boolean control flag")
        if cell["control"]:
            continue
        key = _cell_key(cell)
        if key in lookup:
            raise ValueError("Duplicate scored scientific cell")
        if key[0] not in metadata or key[1] not in configs:
            raise ValueError("Unplanned case or configuration in scored cells")
        if key[2] not in REPRESENTATIONS or key[3] not in PREFERENCES or key[4] not in ORDERS:
            raise ValueError("Unplanned scientific condition")
        if not isinstance(cell.get("valid"), bool):
            raise ValueError("Every scored cell needs a Boolean validity flag")
        if cell["valid"] and not isinstance(cell.get("error"), bool):
            raise ValueError("A valid cell needs a Boolean error outcome")
        if not cell["valid"] and cell.get("error") is not None:
            raise ValueError("An invalid cell must retain an unknown error outcome")
        gap, normalized = _exact(cell["gap"]), _exact(cell["normalized_gap"])
        if gap <= 0 or normalized <= 0:
            raise ValueError("Every scientific case requires a positive regret gap")
        meta = metadata[key[0]]
        if "gap" in meta and (meta["gap"] != gap or meta["normalized_gap"] != normalized):
            raise ValueError("Case gap differs across scored cells")
        meta.update(gap=gap, normalized_gap=normalized)
        lookup[key] = cell
    expected = {(case_id, config, representation, preference, order)
                for case_id in metadata for config in configs
                for representation in REPRESENTATIONS for preference in PREFERENCES for order in ORDERS}
    if set(lookup) != expected:
        raise ValueError("Scored cells must retain exactly every planned scientific cell, including missing outcomes")
    return metadata, lookup


def contrast_rows(metadata: Mapping[str, Any], lookup: Mapping[tuple[str, ...], Any],
                  coefficients: Mapping[tuple[str, str], Fraction], representation: str,
                  *, orders: Iterable[str] = ORDERS) -> list[dict[str, Any]]:
    """Sharp algebraic bounds for each matched whole-case linear contrast."""
    selected_orders = tuple(orders)
    if not selected_orders or any(order not in ORDERS for order in selected_orders):
        raise ValueError("At least one fixed order is required")
    rows = []
    for case_id, meta in sorted(metadata.items()):
        lower = upper = Fraction(0)
        missing = observed = 0
        for (config, preference), coefficient in coefficients.items():
            coefficient /= len(selected_orders)
            for order in selected_orders:
                cell = lookup[(case_id, config, representation, preference, order)]
                if cell["valid"]:
                    contribution = coefficient * int(cell["error"])
                    lower += contribution
                    upper += contribution
                    observed += 1
                else:
                    lower += min(Fraction(0), coefficient)
                    upper += max(Fraction(0), coefficient)
                    missing += 1
        rows.append({**meta, "complete": missing == 0, "error_difference": lower if missing == 0 else None,
                     "error_lower": lower, "error_upper": upper,
                     "regret_difference": meta["gap"] * lower if missing == 0 else None,
                     "regret_lower": meta["gap"] * lower, "regret_upper": meta["gap"] * upper,
                     "normalized_regret_difference": meta["normalized_gap"] * lower if missing == 0 else None,
                     "normalized_regret_lower": meta["normalized_gap"] * lower,
                     "normalized_regret_upper": meta["normalized_gap"] * upper,
                     "missing_requests": missing, "observed_requests": observed})
    return rows


def planned_weights(rows: list[Mapping[str, Any]]) -> list[Fraction]:
    """Equal mass over the eight FIXED strata, then equal planned-case mass."""
    counts = Counter(tuple(row["stratum"]) for row in rows)
    if set(counts) != set(STRATA):
        raise ValueError("The fixed eight-stratum target requires cases in every stratum")
    return [Fraction(1, len(STRATA) * counts[tuple(row["stratum"])]) for row in rows]


def _weighted(rows: list[Mapping[str, Any]], key: str, weights: list[Fraction]) -> Fraction:
    return sum((weight * row[key] for weight, row in zip(weights, rows)), Fraction(0))


def hoeffding_test(rows: list[Mapping[str, Any]], *, outcome_range: tuple[float, float],
                   alpha: float = ALPHA) -> dict[str, Any]:
    """Two-sided test of zero mean, uniformly over missing binary assignments.

    For independent D_i in [a,b], with preassigned weights w_i summing to one,
    P(|sum w_i(D_i-E D_i)| >= t) <= 2 exp(-2t^2 / sum w_i^2(b-a)^2).
    The observed missingness bounds contain the full-plan statistic pointwise.
    Therefore replacing its absolute value by distance([L,U],0) can only make
    rejection harder, for arbitrary outcome-dependent missingness.
    """
    if not 0 < alpha < 1:
        raise ValueError("Alpha must be between zero and one")
    a, b = outcome_range
    if not a < b:
        raise ValueError("A nonzero prespecified logical outcome range is required")
    weights = planned_weights(rows)
    lower, upper = _weighted(rows, "error_lower", weights), _weighted(rows, "error_upper", weights)
    if lower < a or upper > b or lower > upper or any(row["error_lower"] < a or row["error_upper"] > b
                                                    or row["error_lower"] > row["error_upper"] for row in rows):
        raise ValueError("Case contrasts exceed their prespecified logical outcome range")
    distance = lower if lower > 0 else -upper if upper < 0 else Fraction(0)
    scale = float(sum((weight * weight for weight in weights), Fraction(0))) * (b - a) ** 2
    p_value = min(1.0, 2.0 * math.exp(-2.0 * float(distance) ** 2 / scale))
    radius = math.sqrt(scale * math.log(2.0 / alpha) / 2.0)
    family_radius = math.sqrt(scale * math.log(2.0 * PRIMARY_FAMILY_SIZE / alpha) / 2.0)
    return {"method": "two-sided Hoeffding bound; arbitrary missing binary outcomes",
            "null": "equal-weight average full-plan error contrast is zero",
            "p_value": p_value, "missingness_robust_statistic": _stat(distance),
            "fixed_plan_error_bounds": {"lower": _stat(lower), "upper": _stat(upper)},
            "logical_outcome_range": [a, b], "sum_weight_squared_range_squared": scale,
            "case_count": len(rows), "weights_use_planned_counts": True,
            "confidence_interval_95": [max(a, float(lower) - radius), min(b, float(upper) + radius)],
            "confidence_interval_95_radius": radius,
            "simultaneous_family_confidence_interval_95": [max(a, float(lower) - family_radius),
                                                            min(b, float(upper) + family_radius)],
            "simultaneous_family_confidence_interval_95_radius": family_radius,
            "confidence_interval_basis": "Hoeffding with missingness envelope; simultaneous interval uses Bonferroni four"}


def betting_log_e(lower: Iterable[float], upper: Iterable[float], amplitude: float) -> float:
    """Log of the missingness-robust lower bound on a fixed 40-bet e-value.

    For lambda>0 use every lower endpoint, and for lambda<0 every upper
    endpoint. All factors are nonnegative, so each product is no greater
    than that same lambda's product under any full-data completion.
    Endpoint factors equal to zero contribute a log-product of -infinity.
    """
    lower, upper = list(map(float, lower)), list(map(float, upper))
    if not math.isfinite(amplitude) or amplitude <= 0 or not lower or len(lower) != len(upper):
        raise ValueError("A positive finite amplitude and nonempty matched bounds are required")
    if any(not math.isfinite(lo) or not math.isfinite(hi) or not -amplitude <= lo <= hi <= amplitude
           for lo, hi in zip(lower, upper)):
        raise ValueError("Case bounds must lie in the fixed symmetric logical range")
    log_products = []
    for sign in (-1, 1):
        endpoints = lower if sign > 0 else upper
        for k in range(1, BETTING_GRID_STEPS + 1):
            lam = sign * k / (BETTING_GRID_STEPS * amplitude)
            total = 0.0
            for endpoint in endpoints:
                term = lam * endpoint
                if term == -1.0:
                    total = -math.inf
                    break
                total += math.log1p(term)
            log_products.append(total)
    maximum = max(log_products)
    if maximum == -math.inf:
        return -math.inf
    return maximum + math.log(sum(math.exp(value - maximum) for value in log_products)) - math.log(2 * BETTING_GRID_STEPS)


def betting_test(rows: list[Mapping[str, Any]], *, outcome_range: tuple[float, float]) -> dict[str, Any]:
    """Valid fixed-grid e-test for independent nonidentical zero-average cases.

    Write mu_i=E X_i. Independence gives E prod_i(1+lambda X_i)
    =prod_i(1+lambda mu_i). Under sum_i mu_i=0 its nonnegative factors
    have arithmetic mean 1; AM-GM bounds their product by 1. The fixed
    uniform 40-component mixture therefore has expectation at most 1.
    Markov's inequality makes min(1,1/E) a valid p-value. Equal case
    weights are essential to this particular arithmetic-mean proof.
    """
    a, b = outcome_range
    if a != -b or b <= 0:
        raise ValueError("The betting test requires a fixed symmetric range [-A,A]")
    weights = planned_weights(rows)
    if len(rows) != PLANNED_CASES or any(weight != Fraction(1, PLANNED_CASES) for weight in weights):
        raise ValueError("The frozen betting primary requires the balanced 96-case panel with equal weights")
    log_e = betting_log_e((row["error_lower"] for row in rows), (row["error_upper"] for row in rows), b)
    p_value = math.exp(-log_e) if log_e > 0 else 1.0
    e_value = math.exp(log_e) if log_e > -math.inf else 0.0
    return {"method": "fixed symmetric 40-component product-betting e-test; reciprocal e-value p",
            "null": "equal-case-weight average full-plan error contrast is zero",
            "p_value": p_value, "e_value_lower_bound": e_value, "log_e_value_lower_bound": log_e,
            "lambda_grid": [sign * k / (BETTING_GRID_STEPS * b) for sign in (-1, 1)
                            for k in range(1, BETTING_GRID_STEPS + 1)],
            "mixture_weights": "uniform 1/40, fixed before outcomes",
            "logical_outcome_range": [a, b], "case_count": len(rows),
            "missingness_rule": "positive lambda uses every lower endpoint; negative lambda uses every upper endpoint",
            "validity_basis": "independence, bounded factors, zero average mean, AM-GM, and Markov; no identical distribution or sign symmetry"}


def betting_log_e_at_mean(lower: Iterable[float], upper: Iterable[float], *,
                          outcome_range: tuple[float, float], null_mean: float) -> float:
    """Generalized fixed-grid e-value for inversion at a specified null mean.

    For a<mu<b the positive grid is k/[20(mu-a)] and negative grid is
    -k/[20(b-mu)]. Mixture weights stay fixed at 1/40. The equivalent factors
    (1-c)+c(L-a)/(mu-a) and (1-c)+c(b-U)/(b-mu), c=k/20, make positivity
    and the support boundary limits explicit. Boundary tests reject only
    when the observed envelope rules out that support endpoint.
    """
    lower, upper = list(map(float, lower)), list(map(float, upper))
    a, b = outcome_range
    if not math.isfinite(a) or not math.isfinite(b) or not a < b or not a <= null_mean <= b:
        raise ValueError("Finite logical range and a null mean within it are required")
    if not lower or len(lower) != len(upper) or any(not math.isfinite(lo) or not math.isfinite(hi)
                                                   or not a <= lo <= hi <= b for lo, hi in zip(lower, upper)):
        raise ValueError("Case bounds must be nonempty and within the logical range")
    if null_mean == a:
        return 0.0 if all(value == a for value in lower) else math.inf
    if null_mean == b:
        return 0.0 if all(value == b for value in upper) else math.inf
    log_products = []
    for endpoints, support_edge, distance, positive in (
            (lower, a, null_mean - a, True), (upper, b, b - null_mean, False)):
        ratios = [(value - support_edge if positive else support_edge - value) / distance for value in endpoints]
        for k in range(1, BETTING_GRID_STEPS + 1):
            c = k / BETTING_GRID_STEPS
            total = 0.0
            for ratio in ratios:
                factor = (1.0 - c) + c * ratio
                if factor == 0:
                    total = -math.inf
                    break
                # Direct factor arithmetic avoids cancellation for tiny ratios;
                # log1p retains precision when a factor is near one.
                total += math.log1p(c * (ratio - 1.0)) if ratio >= .5 else math.log(factor)
            log_products.append(total)
    maximum = max(log_products)
    return maximum + math.log(sum(math.exp(value - maximum) for value in log_products)) - math.log(2 * BETTING_GRID_STEPS)


def betting_confidence_interval(rows: list[Mapping[str, Any]], *, outcome_range: tuple[float, float],
                                alpha: float = ALPHA) -> dict[str, Any]:
    """Conservative closure of the fixed betting p-value's acceptance interval.

    Equal weights and the 96-case constraints are verified by betting_test.
    The e-value is convex in the hypothesized mean, and is at most one
    throughout [mean(L),mean(U)]. Bisection from their midpoint is therefore
    safe. Outward bracket endpoints preserve conservative coverage.
    """
    if not 0 < alpha < 1:
        raise ValueError("Alpha must be between zero and one")
    betting_test(rows, outcome_range=outcome_range)
    a, b = outcome_range
    lower = [float(row["error_lower"]) for row in rows]
    upper = [float(row["error_upper"]) for row in rows]
    anchor = (sum(lower) + sum(upper)) / (2 * len(rows))
    threshold = math.log(1.0 / alpha)
    def log_e(mu: float) -> float:
        return betting_log_e_at_mean(lower, upper, outcome_range=outcome_range, null_mean=mu)
    if log_e(anchor) > 1e-10:
        raise AssertionError("The missingness midpoint must be an accepted betting anchor")
    endpoints = []
    for support_endpoint in (a, b):
        if log_e(support_endpoint) <= threshold:
            endpoints.append(support_endpoint)
            continue
        outside, inside = support_endpoint, anchor
        for _ in range(80):
            midpoint = outside + (inside - outside) / 2
            if midpoint == outside or midpoint == inside:
                break
            if log_e(midpoint) > threshold:
                outside = midpoint
            else:
                inside = midpoint
        endpoints.append(outside)
    return {"interval": endpoints, "alpha": alpha, "method": "inverted fixed-grid betting reciprocal-e test",
            "anchor": anchor, "e_value_rejection_threshold": 1.0 / alpha,
            "endpoint_convention": "closed outward bisection bracket; equality endpoints included conservatively"}


def combined_confidence_interval(rows: list[Mapping[str, Any]], *, outcome_range: tuple[float, float],
                                 alpha: float = ALPHA) -> dict[str, Any]:
    """Intersect component intervals at alpha/2, matching the combined test."""
    hoeffding = hoeffding_test(rows, outcome_range=outcome_range, alpha=alpha / 2)
    betting = betting_confidence_interval(rows, outcome_range=outcome_range, alpha=alpha / 2)
    h_interval, b_interval = hoeffding["confidence_interval_95"], betting["interval"]
    interval = [max(h_interval[0], b_interval[0]), min(h_interval[1], b_interval[1])]
    if interval[0] > interval[1]:
        raise AssertionError("Both intervals must contain the fixed missingness envelope")
    return {"interval": interval, "alpha": alpha,
            "method": "intersection of Hoeffding and fixed-grid betting intervals, each at alpha/2",
            "component_intervals": {"hoeffding": h_interval, "betting": b_interval},
            "coverage": "at least 1-alpha under independent bounded whole-case clusters; uniform over missing codings",
            "endpoint_convention": betting["endpoint_convention"]}


def combined_primary_test(rows: list[Mapping[str, Any]], *, outcome_range: tuple[float, float]) -> dict[str, Any]:
    """Two prespecified valid component tests, Bonferroni within each endpoint."""
    hoeffding = hoeffding_test(rows, outcome_range=outcome_range)
    betting = betting_test(rows, outcome_range=outcome_range)
    p_value = min(1.0, 2.0 * min(hoeffding["p_value"], betting["p_value"]))
    interval = combined_confidence_interval(rows, outcome_range=outcome_range, alpha=ALPHA)
    simultaneous = combined_confidence_interval(rows, outcome_range=outcome_range, alpha=ALPHA / PRIMARY_FAMILY_SIZE)
    return {**hoeffding, "method": "prespecified Bonferroni minimum of Hoeffding and fixed-grid betting p-values",
            "p_value": p_value, "hoeffding_p_value": hoeffding["p_value"], "betting_p_value": betting["p_value"],
            "within_endpoint_component_tests": 2,
            "betting_e_value_lower_bound": betting["e_value_lower_bound"],
            "betting_log_e_value_lower_bound": betting["log_e_value_lower_bound"],
            "component_tests": {"hoeffding": hoeffding, "betting": betting},
            "hoeffding_only_confidence_interval_95": hoeffding["confidence_interval_95"],
            "hoeffding_only_simultaneous_family_confidence_interval_95": hoeffding["simultaneous_family_confidence_interval_95"],
            "confidence_interval_95": interval["interval"],
            "simultaneous_family_confidence_interval_95": simultaneous["interval"],
            "combined_confidence_interval_details": interval,
            "combined_simultaneous_family_confidence_interval_details": simultaneous,
            "confidence_interval_basis": "combined-test inversion via component intersections at alpha/2; simultaneous family uses alpha/4 first",
            "confidence_interval_interpretation": "Combined intervals match component-test inversion; simultaneous intervals use Bonferroni four, while primary decisions use Holm four",
            "confidence_interval_95_radius": None,
            "simultaneous_family_confidence_interval_95_radius": None,
            "hoeffding_only_confidence_interval_95_radius": hoeffding["confidence_interval_95_radius"],
            "hoeffding_only_simultaneous_family_confidence_interval_95_radius": hoeffding["simultaneous_family_confidence_interval_95_radius"]}


def holm_adjust(p_values: Mapping[str, float | None]) -> dict[str, dict[str, Any]]:
    """Holm across exactly the four frozen hypotheses; unknown p-values are one."""
    if len(p_values) != PRIMARY_FAMILY_SIZE:
        raise ValueError("The confirmatory Holm family must retain all four hypotheses")
    cleaned = {}
    for key, p in p_values.items():
        if p is not None and (not math.isfinite(p) or not 0 <= p <= 1):
            raise ValueError("P-values must be finite and between zero and one")
        cleaned[key] = 1.0 if p is None else p
    ordered = sorted(cleaned, key=lambda key: (cleaned[key], key))
    result: dict[str, dict[str, Any]] = {}
    running = 0.0
    for rank, key in enumerate(ordered):
        running = max(running, (PRIMARY_FAMILY_SIZE - rank) * cleaned[key])
        adjusted = min(1.0, running)
        result[key] = {"holm_adjusted_p_value": adjusted, "reject_at_0_05": adjusted <= ALPHA,
                       "unavailable_input_treated_as_one": p_values[key] is None,
                       "family_size": PRIMARY_FAMILY_SIZE}
    return result


def _percentile(ordered: list[float], q: float) -> float:
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def bootstrap_diagnostic(rows: list[Mapping[str, Any]], *, draws: int = BOOTSTRAP_DRAWS,
                         seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Complete-case, nonstudentized bootstrap within eight analysis strata.

    This estimates the observed complete-case distribution, NOT a primary
    test or a uniformly valid CI. No studentization, variance floor, zero-event
    equivalence claim, imputation, or reduction of the four-test family.
    """
    if draws <= 0:
        raise ValueError("Bootstrap draws must be positive")
    groups = {stratum: [row for row in rows if tuple(row["stratum"]) == stratum and row["complete"]]
              for stratum in STRATA}
    empty = ["|".join(stratum) for stratum, group in groups.items() if not group]
    output: dict[str, Any] = {"role": "descriptive only; unadjusted; no guaranteed coverage",
                              "method": "eight-stratum complete-case nonstudentized case bootstrap",
                              "draws": draws, "seed": seed,
                              "complete_counts": {"|".join(s): len(group) for s, group in groups.items()},
                              "unavailable_reason": "empty complete-case analysis stratum" if empty else None,
                              "empty_strata": empty, "p_value": None}
    if empty:
        output["error_percentile_interval_95"] = None
        output["regret_percentile_interval_95"] = None
        return output
    rng = random.Random(seed)
    errors, regrets = [], []
    for _ in range(draws):
        error_total = regret_total = 0.0
        for group in groups.values():
            selected = [group[rng.randrange(len(group))] for _ in group]
            error_total += sum(float(row["error_difference"]) for row in selected) / len(group) / len(STRATA)
            regret_total += sum(float(row["regret_difference"]) for row in selected) / len(group) / len(STRATA)
        errors.append(error_total)
        regrets.append(regret_total)
    errors.sort()
    regrets.sort()
    output.update(error_percentile_interval_95=[_percentile(errors, .025), _percentile(errors, .975)],
                  regret_percentile_interval_95=[_percentile(regrets, .025), _percentile(regrets, .975)],
                  degenerate_error_interval=errors[0] == errors[-1])
    return output


def descriptive_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    complete = [row for row in rows if row["complete"]]
    groups = {s: [row for row in complete if tuple(row["stratum"]) == s] for s in STRATA}
    all_strata = all(groups.values())
    weights = planned_weights(rows)
    def complete_mean(metric: str) -> Fraction | None:
        return sum((_mean(row[metric] for row in group) for group in groups.values()), Fraction(0)) / len(STRATA) if all_strata else None
    output: dict[str, Any] = {"planned_cases": len(rows), "complete_cases": len(complete),
                              "complete_case_mean_error_difference": _stat(complete_mean("error_difference")),
                              "complete_case_mean_regret_difference": _stat(complete_mean("regret_difference")),
                              "complete_case_mean_normalized_regret_difference": _stat(complete_mean("normalized_regret_difference")),
                              "available_complete_case_unweighted_mean_error_difference": _stat(_mean(row["error_difference"] for row in complete)),
                              "complete_case_mean_target": "equal eight-stratum weights over observed complete cases; descriptive selection-dependent target",
                              "missing_requests": sum(row["missing_requests"] for row in rows),
                              "harmful_complete_cases": sum(row["error_difference"] > 0 for row in complete),
                              "protective_complete_cases": sum(row["error_difference"] < 0 for row in complete)}
    for metric in ("error", "regret", "normalized_regret"):
        output[f"fixed_plan_{metric}_bounds"] = {
            "lower": _stat(_weighted(rows, f"{metric}_lower", weights)),
            "upper": _stat(_weighted(rows, f"{metric}_upper", weights))}
    output["case_records"] = [{key: str(value) if isinstance(value, Fraction) else list(value) if isinstance(value, tuple) else value
                                 for key, value in row.items()} for row in rows]
    return output


def condition_summary(cells: list[Mapping[str, Any]]) -> dict[str, Any]:
    groups = defaultdict(list)
    for cell in cells:
        if not cell["control"]:
            groups[(cell["config_id"], cell["representation"], cell["preference"])].append(cell)
    result: dict[str, Any] = {}
    for (config, representation, preference), group in sorted(groups.items()):
        valid = [cell for cell in group if cell["valid"]]
        errors = sum(int(cell["error"]) for cell in valid)
        missing = len(group) - len(valid)
        result.setdefault(config, {}).setdefault(representation, {})[preference] = {
            "planned": len(group), "valid": len(valid), "missing_or_invalid": missing,
            "observed_errors": errors,
            "observed_error_rate": _stat(Fraction(errors, len(valid))) if valid else None,
            "fixed_plan_error_rate_bounds": {"lower": _stat(Fraction(errors, len(group))),
                                                "upper": _stat(Fraction(errors + missing, len(group)))}}
    return result


def analyze_scored_cells(cases: Any, cells: list[Mapping[str, Any]], config_ids: Iterable[str],
                         deepseek_off_id: str, deepseek_on_id: str, *, confirmatory: bool = True,
                         bootstrap_draws: int = BOOTSTRAP_DRAWS) -> dict[str, Any]:
    configs = tuple(config_ids)
    metadata, lookup = validate_inputs(cases, cells, configs, deepseek_off_id, deepseek_on_id,
                                       confirmatory=confirmatory)
    if set(meta["stratum"] for meta in metadata.values()) != set(STRATA):
        raise ValueError("Descriptive smoke analysis also requires all eight analysis strata")
    pressure = {config: {(config, "strong_inferior"): Fraction(1), (config, "neutral"): Fraction(-1)} for config in configs}
    interaction = {(deepseek_on_id, "strong_inferior"): Fraction(1), (deepseek_on_id, "neutral"): Fraction(-1),
                   (deepseek_off_id, "strong_inferior"): Fraction(-1), (deepseek_off_id, "neutral"): Fraction(1)}
    primary_rows: dict[str, Any] = {}
    specs: dict[str, Any] = {}
    for config in configs:
        name = f"raw_pressure::{config}"
        primary_rows[name] = contrast_rows(metadata, lookup, pressure[config], "raw")
        specs[name] = {"config_id": config, "representation": "raw", "plus": "strong_inferior", "minus": "neutral", "range": (-1.0, 1.0)}
    interaction_name = f"raw_reasoning_interaction::{deepseek_on_id}-{deepseek_off_id}"
    primary_rows[interaction_name] = contrast_rows(metadata, lookup, interaction, "raw")
    specs[interaction_name] = {"representation": "raw", "plus": deepseek_on_id, "minus": deepseek_off_id,
                               "within_config": "strong_inferior minus neutral", "range": (-2.0, 2.0)}
    primaries: dict[str, Any] = {}
    for offset, (name, rows) in enumerate(primary_rows.items()):
        summary = descriptive_summary(rows)
        summary["contrast"] = specs[name]
        summary["inference"] = combined_primary_test(rows, outcome_range=specs[name]["range"]) if confirmatory else None
        summary["bootstrap_diagnostic"] = bootstrap_diagnostic(rows, draws=bootstrap_draws, seed=BOOTSTRAP_SEED + offset)
        primaries[name] = summary
    if confirmatory:
        adjusted = holm_adjust({name: summary["inference"]["p_value"] for name, summary in primaries.items()})
        for name in primaries:
            primaries[name]["inference"].update(adjusted[name])
    supplied: dict[str, Any] = {}
    for config in configs:
        supplied[f"supplied_pressure::{config}"] = descriptive_summary(contrast_rows(metadata, lookup, pressure[config], "supplied"))
    supplied[f"supplied_reasoning_interaction::{deepseek_on_id}-{deepseek_off_id}"] = descriptive_summary(contrast_rows(metadata, lookup, interaction, "supplied"))
    return {"analysis_version": ANALYSIS_VERSION, "confirmatory": confirmatory,
            "primary_family": list(primaries), "family_size": PRIMARY_FAMILY_SIZE if confirmatory else None,
            "estimand": "equally weighted eight-stratum average of full-plan case error contrasts; two orders averaged within case",
            "independence_assumption": "Independent full-case clusters conditional on the frozen blocked set and preassigned hash slots; arbitrary heterogeneity and within-case dependence allowed",
            "missingness_interpretation": "Uniform over every binary coding of unscorable planned requests; no missing-at-random assumption",
            "case_count": len(metadata), "scientific_request_count": len(lookup),
            "analysis_stratum_counts": dict(sorted(Counter("|".join(meta["stratum"]) for meta in metadata.values()).items())),
            "primaries": primaries, "descriptive_supplied": supplied,
            "condition_counts": condition_summary(cells),
            "settings": {"alpha": ALPHA, "bootstrap_draws": bootstrap_draws, "bootstrap_seed": BOOTSTRAP_SEED,
                         "test_sidedness": "two-sided", "primary_method": "Bonferroni minimum of Hoeffding and fixed-grid betting, then Holm four",
                         "betting_grid_steps_each_sign": BETTING_GRID_STEPS, "within_endpoint_component_tests": 2,
                         "bootstrap_role": "descriptive only", "effect_based_collection_gate": False}}


def _duplicate_check(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"Duplicate JSON key: {key}")
        output[key] = value
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--cells", type=Path, required=True)
    parser.add_argument("--config-ids", nargs=CONFIGURATION_COUNT, required=True)
    parser.add_argument("--deepseek-off", required=True)
    parser.add_argument("--deepseek-on", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke-descriptive-only", action="store_true")
    parser.add_argument("--bootstrap-draws", type=int, default=BOOTSTRAP_DRAWS)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(), object_pairs_hook=_duplicate_check)
    cells = json.loads(args.cells.read_text(), object_pairs_hook=_duplicate_check)
    if isinstance(cells, Mapping):
        cells = cells["cells"]
    result = analyze_scored_cells(cases, cells, args.config_ids, args.deepseek_off, args.deepseek_on,
                                  confirmatory=not args.smoke_descriptive_only, bootstrap_draws=args.bootstrap_draws)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output.resolve()), "confirmatory": result["confirmatory"],
                      "case_count": result["case_count"], "family_size": result["family_size"]}))


if __name__ == "__main__":
    main()
