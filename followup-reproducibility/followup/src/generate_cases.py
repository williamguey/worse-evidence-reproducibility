"""Reusable provisional generator for independent H01 numerical cases.

This module generates parameters and their audited oracle metadata only.  It
does not build the experimental prompts, assign archive tags, run models, or
write results.  A complete 24-case cycle crosses optimal acquisition cost,
regret stratum, prevalence, and optimal report position.  Each complete
six-case block balances the binary factors and the three regret strata.
"""

from __future__ import annotations

import hashlib
import json
import random
from fractions import Fraction
from itertools import cycle
from typing import Any, Iterable, Mapping

from decision_engine import (evaluate_case, fraction_string, json_ready, parameter_tuple,
                             rational, serializable_parameters, verify_independent_oracle)
from parameter_codec import render_parameter_block, validate_rendered_source

GENERATOR_VERSION = "h01-independent-v1"

# Extracted only from the four discovery case parameter records.  No response
# data, discovery outcomes, or discovery oracle values are imported.  Sorting
# report tuples also excludes their A/B permutations from every new split.
SCREEN_PARAMETER_TUPLES = (
    ("1/2", "10", "10", ("9/10", "9/10", "2/5"), ("13/20", "13/20", "1/10")),
    ("1/5", "6", "18", ("11/20", "4/5", "3/20"), ("4/5", "9/10", "3/10")),
    ("7/10", "12", "4", ("7/10", "13/20", "1/10"), ("11/20", "3/5", "1/5")),
    ("7/20", "8", "15", ("19/20", "17/20", "11/5"), ("4/5", "17/20", "1/5")),
)

FAMILIES = (
    ("beacon", "fictional beacon alignment simulator"),
    ("navigation", "fictional navigation waypoint simulator"),
    ("computation", "fictional computation consistency simulator"),
    ("simulation", "fictional training gate simulator"),
)

PRIORS = {"rare": tuple(map(Fraction, ("1/20", "1/10", "3/20", "1/5", "1/4"))),
          "common": tuple(map(Fraction, ("2/5", "1/2", "3/5", "7/10", "4/5")))}
LOSSES = (4, 6, 8, 10, 12, 15, 16, 18, 20, 24, 30)
RATES = tuple(map(Fraction, ("11/20", "3/5", "13/20", "7/10", "3/4", "4/5",
                            "17/20", "9/10", "19/20", "49/50")))
LOW_REGRET_MAX = Fraction(1, 10)
MODERATE_REGRET_MAX = Fraction(7, 20)


def normalize_parameter_tuple(item: Any) -> tuple[Any, ...]:
    """Normalize a case mapping or the exported five-entry numeric tuple."""
    if isinstance(item, Mapping):
        return parameter_tuple(item)
    if len(item) != 5 or any(len(report) != 3 for report in item[3:]):
        raise ValueError("Blocked tuples must contain prior, two losses, and two (sensitivity, specificity, cost) tuples")
    head = tuple(fraction_string(value) for value in item[:3])
    reports = tuple(sorted(tuple(fraction_string(value) for value in report) for report in item[3:]))
    return (*head, *reports)


def blocked_parameter_set(blocked_tuples: Iterable[Any] = ()) -> set[tuple[Any, ...]]:
    """Always exclude the discovery screen, plus any previous new cases."""
    return {normalize_parameter_tuple(item) for item in (*SCREEN_PARAMETER_TUPLES, *blocked_tuples)}


def regret_stratum(normalized_regret: Any) -> str:
    regret = rational(normalized_regret)
    if regret <= 0:
        raise ValueError("Regret must be strictly positive for a unique optimal report")
    if regret <= LOW_REGRET_MAX:
        return "low"
    if regret <= MODERATE_REGRET_MAX:
        return "moderate"
    return "high"


def case_strata(case: Mapping[str, Any], oracle: Mapping[str, Any] | None = None) -> dict[str, str]:
    p = serializable_parameters(case)
    truth = evaluate_case(case) if oracle is None else oracle
    winner = truth["optimal_report"]
    if winner is None:
        raise ValueError("Generated cases must have a strictly unique optimal report")
    loser = "B" if winner == "A" else "A"
    winner_cost = rational(p["reports"][winner]["cost"])
    loser_cost = rational(p["reports"][loser]["cost"])
    if winner_cost == loser_cost:
        raise ValueError("Costs must differ for the cheaper/more-expensive balance")
    prior = rational(p["prior_state1"])
    if prior <= Fraction(1, 4):
        prevalence = "rare"
    elif prior >= Fraction(2, 5):
        prevalence = "common"
    else:
        raise ValueError("Prior is outside the provisional rare/common strata")
    policies = [tuple(truth["reports"][report_id]["signals"][signal]["optimal_actions"]
                      for signal in ("+", "-")) for report_id in ("A", "B")]
    action_changes = [policy[0] != policy[1] for policy in policies]
    loss_act, loss_wait = rational(p["loss_ACT_state0"]), rational(p["loss_WAIT_state1"])
    return {"optimal_cost": "cheaper" if winner_cost < loser_cost else "more_expensive",
            "regret": regret_stratum(truth["normalized_regret"]),
            "state1_prevalence": prevalence, "optimal_report": winner,
            "loss_asymmetry": "ACT_larger" if loss_act > loss_wait else "WAIT_larger" if loss_wait > loss_act else "symmetric",
            "policy_pattern": "both_signal_contingent" if all(action_changes) else "one_signal_contingent"}


def _target_schedule(rng: random.Random):
    """Each 24 targets forms a full 2 x 3 x 2 x 2 factorial."""
    cycle_number = 0
    while True:
        regrets = ["low", "moderate", "high"]
        rng.shuffle(regrets)
        for pairing in (0, 1):
            for regret in regrets:
                pair = [("rare", "cheaper" if pairing == 0 else "more_expensive"),
                        ("common", "more_expensive" if pairing == 0 else "cheaper")]
                if rng.randrange(2):
                    pair.reverse()
                regret_index = ("low", "moderate", "high").index(regret)
                rare_winner = "A" if (regret_index + pairing + cycle_number) % 2 == 0 else "B"
                for prevalence, cost_relation in pair:
                    winner = rare_winner if prevalence == "rare" else ("B" if rare_winner == "A" else "A")
                    yield {"regret": regret, "state1_prevalence": prevalence,
                           "optimal_cost": cost_relation, "optimal_report": winner}
        cycle_number += 1


def _draw_parameters(rng: random.Random, prevalence: str) -> dict[str, Any]:
    prior = rng.choice(PRIORS[prevalence])
    loss_act, loss_wait = rng.choice(LOSSES), rng.choice(LOSSES)
    costs = rng.sample(range(1, 51), 2)
    return {"prior_state1": fraction_string(prior), "loss_ACT_state0": str(loss_act),
            "loss_WAIT_state1": str(loss_wait),
            "reports": {report_id: {"sensitivity": fraction_string(rng.choice(RATES)),
                                    "specificity": fraction_string(rng.choice(RATES)),
                                    "cost": fraction_string(Fraction(cost, 20))}
                        for report_id, cost in zip(("A", "B"), costs)}}


def generate(seed: int, n: int, blocked_tuples: Iterable[Any] = ()) -> list[dict[str, Any]]:
    """Generate n deterministic, unique, audited cases, excluding all old tuples.

    Caller-supplied blocked tuples should include any previously generated
    development/pilot/heldout cases.  Alternatively use generate_splits, which
    enforces this automatically.  Strata are provisional until method review.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    rng = random.Random(seed)
    excluded = blocked_parameter_set(blocked_tuples)
    schedule = _target_schedule(rng)
    families = list(FAMILIES)
    rng.shuffle(families)
    family_schedule = cycle(families)
    cases = []
    for index in range(n):
        target = next(schedule)
        for attempt in range(1, 20001):
            p = _draw_parameters(rng, target["state1_prevalence"])
            signature = parameter_tuple(p)
            if signature in excluded:
                continue
            truth = evaluate_case(p)
            if truth["optimal_report"] is None:
                continue
            # Terminal ties complicate interpretation and are excluded from
            # the provisional pool. At least the optimal report must change
            # the optimal downstream action across its two signal outcomes.
            if any(len(signal["optimal_actions"]) != 1 for report in truth["reports"].values()
                   for signal in report["signals"].values()):
                continue
            winner = truth["optimal_report"]
            optimal_actions = [truth["reports"][winner]["signals"][signal]["optimal_actions"][0]
                               for signal in ("+", "-")]
            if optimal_actions[0] == optimal_actions[1]:
                continue
            strata = case_strata(p, truth)
            if any(strata[key] != value for key, value in target.items()):
                continue
            audited = verify_independent_oracle(p)
            validate_rendered_source(p, render_parameter_block(p))
            family, scenario = next(family_schedule)
            fingerprint = hashlib.sha256(json.dumps(signature, separators=(",", ":")).encode("ascii")).hexdigest()
            case = {"case_id": "H01N_" + fingerprint[:16], "family": family,
                    "scenario": scenario, "parameters": p,
                    "generation": {"generator_version": GENERATOR_VERSION, "seed": seed,
                                   "index": index, "draws_for_case": attempt,
                                   "parameter_tuple": json_ready(signature),
                                   "parameter_sha256": fingerprint, "strata": strata,
                                   "regret_definition": "absolute score gap / pre-report Bayes terminal risk",
                                   "regret_boundaries": {"low_max_inclusive": "1/10", "moderate_max_inclusive": "7/20"}},
                    "constraints": {"candidate_report_count": 2, "mandatory_acquisition_count": 1,
                                    "downstream_actions": ["ACT", "WAIT"],
                                    "optimal_downstream_actions_stipulated": True,
                                    "no_acquisition_option": False, "abstention_option": False,
                                    "report_delivery": "fully readable canonical English",
                                    "delivery_speed_equal": True, "effort_equal": True,
                                    "archive_label_has_cost_or_comprehension_effect": False},
                    "oracle": json_ready(audited)}
            cases.append(case)
            excluded.add(signature)
            break
        else:
            raise RuntimeError(f"Could not generate stratum {target} within 20000 independent draws")
    return cases


def generate_splits(seed: int, split_sizes: Mapping[str, int],
                    blocked_tuples: Iterable[Any] = ()) -> dict[str, list[dict[str, Any]]]:
    """Generate disjoint named splits, extending exclusions after each split."""
    excluded = blocked_parameter_set(blocked_tuples)
    output = {}
    for index, (split_name, size) in enumerate(split_sizes.items()):
        if not isinstance(split_name, str) or not split_name:
            raise ValueError("Split names must be nonempty strings")
        split_seed = seed + (index + 1) * 1000003
        cases = generate(split_seed, size, excluded)
        for case in cases:
            case["generation"]["split"] = split_name
        output[split_name] = cases
        excluded.update(parameter_tuple(case) for case in cases)
    return output
