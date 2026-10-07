"""Exact oracle for compulsory acquisition of one of two binary reports.

All inputs use integers, Fraction objects, or rational strings.  There is no
third (no acquisition) option.  ACT costs loss_ACT_state0 when Z=0; WAIT costs
loss_WAIT_state1 when Z=1, and the other two terminal losses are zero.
Archive labels and prompt text are intentionally absent from this module.
"""

from __future__ import annotations

from fractions import Fraction
from itertools import product
from typing import Any, Mapping

REPORT_IDS = ("A", "B")
SIGNALS = ("+", "-")
ACTIONS = ("ACT", "WAIT")


def rational(value: Any) -> Fraction:
    """Parse an exact number; floating-point inputs are deliberately rejected."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("Use an integer, Fraction, or rational string, not a float/bool")
    if not isinstance(value, (int, str, Fraction)):
        raise TypeError(f"Unsupported rational input: {type(value).__name__}")
    return Fraction(value)


def fraction_string(value: Any) -> str:
    value = rational(value)
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def parameters(case: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a case, or its parameters object, to Fractions."""
    raw = case.get("parameters", case)
    p = rational(raw["prior_state1"])
    loss_act = rational(raw["loss_ACT_state0"])
    loss_wait = rational(raw["loss_WAIT_state1"])
    if not 0 < p < 1:
        raise ValueError("The prior must be strictly between zero and one")
    if loss_act <= 0 or loss_wait <= 0:
        raise ValueError("Both nonzero terminal losses must be positive")
    offered = raw["reports"]
    if set(offered) != set(REPORT_IDS):
        raise ValueError("Exactly two candidate reports, A and B, are required")
    reports = {}
    for report_id in REPORT_IDS:
        report = offered[report_id]
        sensitivity = rational(report["sensitivity"])
        specificity = rational(report["specificity"])
        cost = rational(report["cost"])
        if not (0 < sensitivity < 1 and 0 < specificity < 1):
            raise ValueError("Both signal likelihoods must be nondegenerate in both states")
        if cost < 0:
            raise ValueError("Acquisition cost cannot be negative")
        reports[report_id] = {"sensitivity": sensitivity, "specificity": specificity, "cost": cost}
    return {"prior_state1": p, "loss_ACT_state0": loss_act,
            "loss_WAIT_state1": loss_wait, "reports": reports}


def serializable_parameters(case: Mapping[str, Any]) -> dict[str, Any]:
    p = parameters(case)
    return {"prior_state1": fraction_string(p["prior_state1"]),
            "loss_ACT_state0": fraction_string(p["loss_ACT_state0"]),
            "loss_WAIT_state1": fraction_string(p["loss_WAIT_state1"]),
            "reports": {report_id: {k: fraction_string(v) for k, v in report.items()}
                        for report_id, report in p["reports"].items()}}


def parameter_tuple(case: Mapping[str, Any]) -> tuple[Any, ...]:
    """Numeric identity, invariant to swapping report A/B or changing prose."""
    p = serializable_parameters(case)
    reports = tuple(sorted(tuple(p["reports"][report_id][key]
                                 for key in ("sensitivity", "specificity", "cost"))
                           for report_id in REPORT_IDS))
    return (p["prior_state1"], p["loss_ACT_state0"], p["loss_WAIT_state1"], *reports)


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Use joint probability masses to compute exact report acquisition scores.

    score(T) = cost(T) + sum_s min(L_ACT * P(Z=0,s), L_WAIT * P(Z=1,s)).
    Return Fractions.  Ties are explicit so callers cannot manufacture a key.
    """
    p = parameters(case)
    prior1 = p["prior_state1"]
    prior0 = 1 - prior1
    loss_act, loss_wait = p["loss_ACT_state0"], p["loss_WAIT_state1"]
    reports = {}
    for report_id, report in p["reports"].items():
        sensitivity, specificity = report["sensitivity"], report["specificity"]
        joint = {"+": {0: prior0 * (1 - specificity), 1: prior1 * sensitivity},
                 "-": {0: prior0 * specificity, 1: prior1 * (1 - sensitivity)}}
        signal_results = {}
        terminal_loss = Fraction(0)
        for signal, states in joint.items():
            mass = states[0] + states[1]
            contributions = {"ACT": loss_act * states[0], "WAIT": loss_wait * states[1]}
            minimum = min(contributions.values())
            optimal_actions = tuple(action for action in ACTIONS if contributions[action] == minimum)
            signal_results[signal] = {
                "joint_state0": states[0], "joint_state1": states[1],
                "signal_probability": mass, "posterior_state1": states[1] / mass,
                "ACT_loss_contribution": contributions["ACT"],
                "WAIT_loss_contribution": contributions["WAIT"],
                "optimal_actions": optimal_actions, "optimal_loss_contribution": minimum}
            terminal_loss += minimum
        reports[report_id] = {"cost": report["cost"], "signals": signal_results,
                              "expected_terminal_loss": terminal_loss,
                              "expected_total_score": report["cost"] + terminal_loss}
    best_score = min(report["expected_total_score"] for report in reports.values())
    optimal_reports = tuple(report_id for report_id in REPORT_IDS
                            if reports[report_id]["expected_total_score"] == best_score)
    gap = abs(reports["A"]["expected_total_score"] - reports["B"]["expected_total_score"])
    # The pre-report risk is a scale descriptor, never an offered alternative.
    pre_report_risk = min(loss_act * prior0, loss_wait * prior1)
    return {"reports": reports, "optimal_reports": optimal_reports,
            "optimal_report": optimal_reports[0] if len(optimal_reports) == 1 else None,
            "optimal_score": best_score, "regret_of_wrong_report": gap,
            "pre_report_terminal_risk_scale": pre_report_risk,
            "normalized_regret": gap / pre_report_risk}


def enumerate_posterior_policies(case: Mapping[str, Any]) -> dict[str, Any]:
    """Independent verification via all four signal-contingent action policies.

    This route forms P(s) from conditional likelihoods, applies Bayes' rule,
    and enumerates every (+ action, - action) policy using conditional losses.
    It does not call evaluate_case or take minima of joint loss masses.
    """
    p = parameters(case)
    prior = {0: 1 - p["prior_state1"], 1: p["prior_state1"]}
    terminal_losses = {"ACT": {0: p["loss_ACT_state0"], 1: Fraction(0)},
                       "WAIT": {0: Fraction(0), 1: p["loss_WAIT_state1"]}}
    answers = {}
    for report_id, report in p["reports"].items():
        likelihoods = {0: {"+": 1 - report["specificity"], "-": report["specificity"]},
                       1: {"+": report["sensitivity"], "-": 1 - report["sensitivity"]}}
        probabilities = {}
        conditional_losses = {}
        for signal in SIGNALS:
            probability = sum(prior[state] * likelihoods[state][signal] for state in (0, 1))
            posterior = {state: prior[state] * likelihoods[state][signal] / probability
                         for state in (0, 1)}
            probabilities[signal] = probability
            conditional_losses[signal] = {
                action: sum(posterior[state] * terminal_losses[action][state] for state in (0, 1))
                for action in ACTIONS}
        policies = {}
        for plus_action, minus_action in product(ACTIONS, repeat=2):
            policy_name = f"+:{plus_action},-:{minus_action}"
            policies[policy_name] = (report["cost"]
                                     + probabilities["+"] * conditional_losses["+"][plus_action]
                                     + probabilities["-"] * conditional_losses["-"][minus_action])
        best = min(policies.values())
        answers[report_id] = {"expected_total_score": best, "policy_scores": policies,
                              "optimal_policies": tuple(name for name, score in policies.items() if score == best)}
    return answers


def json_ready(value: Any) -> Any:
    """Recursively turn exact components into portable JSON values."""
    if isinstance(value, Fraction):
        return fraction_string(value)
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_ready(item) for item in value]
    return value


def verify_independent_oracle(case: Mapping[str, Any]) -> dict[str, Any]:
    direct = evaluate_case(case)
    independent = enumerate_posterior_policies(case)
    for report_id in REPORT_IDS:
        if direct["reports"][report_id]["expected_total_score"] != independent[report_id]["expected_total_score"]:
            raise AssertionError(f"Oracle disagreement for report {report_id}")
    return direct


def validate_supplied_oracle(case: Mapping[str, Any], supplied: Mapping[str, Any]) -> None:
    """Reject a supplied answer key or component record that differs from truth."""
    expected = json_ready(verify_independent_oracle(case))
    if supplied != expected:
        differing = sorted(key for key in set(expected) | set(supplied)
                           if expected.get(key) != supplied.get(key))
        raise ValueError("Supplied oracle differs from exact independently verified truth: " + ", ".join(differing))
