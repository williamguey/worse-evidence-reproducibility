#!/usr/bin/env python3
"""Offline post hoc H01 diagnostics; Python standard library only.

Reads the distributed clean tree without rewriting its scientific artifacts.
Example:
  python3 -B descriptive_diagnostics.py --bundle-root /path/to/followup-reproducibility \
      --output /path/to/transition-diagnostics.json

Each transition is neutral -> strong_inferior in the same configuration,
case, report order, and representation. C/W are derived by comparing the final
raw response choice with an independently recomputed exact-rational oracle.
Frozen validity flags determine admissibility; controls and unscorable pairs
are excluded from the descriptive table, with planned denominators disclosed.
The 192 paired response slots per representation remain nested in 96 cases.
This script performs no network requests, new inference, or interval estimates.
"""

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys


CONFIGURATIONS = ("ds_off_bd", "ds_low_bd", "gpt6_luna_low")
REPRESENTATIONS = ("raw", "supplied")
ORDERS = ("AB", "BA")
PREFERENCES = ("neutral", "strong_inferior")
TRANSITIONS = ("CC", "CW", "WC", "WW")
PLANNED_CASES = 96


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def fraction_value(value):
    return {"exact": str(value), "value": float(value)}


def independent_oracle(case):
    """Bayes terminal loss + acquisition cost, without frozen engine imports."""
    p = case["parameters"]
    state1 = Fraction(p["prior_state1"])
    loss0 = Fraction(p["loss_ACT_state0"])
    loss1 = Fraction(p["loss_WAIT_state1"])
    totals = {}
    for label, report in p["reports"].items():
        sensitivity = Fraction(report["sensitivity"])
        specificity = Fraction(report["specificity"])
        plus_act = (1 - state1) * (1 - specificity) * loss0
        plus_wait = state1 * sensitivity * loss1
        minus_act = (1 - state1) * specificity * loss0
        minus_wait = state1 * (1 - sensitivity) * loss1
        totals[label] = Fraction(report["cost"]) + min(plus_act, plus_wait) + min(minus_act, minus_wait)
    require(set(totals) == {"A", "B"}, "Oracle requires exactly reports A and B")
    require(totals["A"] != totals["B"], "Tied oracle is outside the frozen case bank")
    label = min(totals, key=totals.get)
    require(label == case["oracle"]["optimal_report"], "Case oracle label mismatch")
    for report_label, total in totals.items():
        require(total == Fraction(case["oracle"]["reports"][report_label]["expected_total_score"]),
                "Case oracle total mismatch")
    gap = abs(totals["A"] - totals["B"])
    require(gap == Fraction(case["oracle"]["regret_of_wrong_report"]), "Case oracle gap mismatch")
    return label


def raw_choice(path, model):
    """Read only the published final answer, never a reasoning trace."""
    data = read_json(path)
    require(data.get("model") == model, "Raw response model mismatch: " + path.name)
    choices = data.get("choices")
    require(isinstance(choices, list) and len(choices) == 1, "Raw choice count mismatch: " + path.name)
    item = choices[0]
    message = item.get("message", {})
    require(item.get("finish_reason") == "stop" and not message.get("refusal"),
            "Unfinished/refused raw response: " + path.name)

    def unique_keys(items):
        answer = dict(items)
        require(len(answer) == len(items), "Duplicate final-answer JSON key")
        return answer

    answer = json.loads(message["content"], object_pairs_hook=unique_keys)
    require(isinstance(answer, dict) and set(answer) == {"choice"} and answer["choice"] in ("A", "B"),
            "Invalid final-answer JSON: " + path.name)
    return answer["choice"]


def condition_counts(rows):
    valid = [row for row in rows if row["valid"]]
    errors = sum(row["derived_wrong"] for row in valid)
    return {
        "planned_responses": len(rows),
        "valid_responses": len(valid),
        "missing_or_invalid_responses": len(rows) - len(valid),
        "observed_errors": errors,
        "observed_correct": len(valid) - errors,
        "observed_error_rate": fraction_value(Fraction(errors, len(valid))) if valid else None,
        "choices": {label: sum(row["verified_choice"] == label for row in valid) for label in ("A", "B")},
    }


def summarize_pairs(pairs):
    counts = Counter()
    complete_cases = Counter()
    missing = []
    for neutral, pressure in pairs:
        if neutral["valid"] and pressure["valid"]:
            transition = ("W" if neutral["derived_wrong"] else "C") + ("W" if pressure["derived_wrong"] else "C")
            counts[transition] += 1
            complete_cases[neutral["case_id"]] += 1
        else:
            missing.append({
                "case_id": neutral["case_id"], "order": neutral["order"],
                "optimal_label": neutral["expected"],
                "unscorable_responses": [
                    {"preference": row["preference"], "request_id": row["request_id"],
                     "reason": row.get("invalid_reason")}
                    for row in (neutral, pressure) if not row["valid"]
                ],
            })
    complete = sum(counts.values())
    case_ids = {neutral["case_id"] for neutral, _ in pairs}
    return {
        "planned_case_clusters": len(case_ids),
        "planned_paired_response_slots": len(pairs),
        "complete_paired_response_slots": complete,
        "excluded_missing_or_invalid_pair_slots": len(missing),
        "case_clusters_with_at_least_one_complete_slot": len(complete_cases),
        "transitions_neutral_to_pressure": {name: counts[name] for name in TRANSITIONS},
        "neutral_errors_among_complete_pairs": counts["WC"] + counts["WW"],
        "pressure_errors_among_complete_pairs": counts["CW"] + counts["WW"],
        "net_error_increase_among_complete_pairs": counts["CW"] - counts["WC"],
        "complete_pair_error_difference": fraction_value(Fraction(counts["CW"] - counts["WC"], complete)) if complete else None,
        "conditions_in_this_slice": {
            "neutral": condition_counts([n for n, _ in pairs]),
            "strong_inferior": condition_counts([p for _, p in pairs]),
        },
        "excluded_pairs": missing,
    }


def check_published_aggregates(aggregate, scientific, pairs_by_group, cases):
    """Compare descriptive margins and whole-case means; no inferential calls."""
    checks = []
    for config in CONFIGURATIONS:
        for representation in REPRESENTATIONS:
            for preference in PREFERENCES:
                selected = [r for r in scientific if r["config_id"] == config
                            and r["representation"] == representation and r["preference"] == preference]
                derived = condition_counts(selected)
                published = aggregate["condition_counts"][config][representation][preference]
                for ours, theirs in (("planned_responses", "planned"), ("valid_responses", "valid"),
                                     ("missing_or_invalid_responses", "missing_or_invalid"),
                                     ("observed_errors", "observed_errors")):
                    require(derived[ours] == published[theirs], "Published condition count mismatch")
                require(derived["observed_error_rate"]["exact"] == published["observed_error_rate"]["exact"],
                        "Published observed error rate mismatch")
                checks.append({"configuration": config, "representation": representation,
                               "preference": preference, "condition_counts_match": True})

            pairs = pairs_by_group[(config, representation)]
            by_case = defaultdict(list)
            for neutral, pressure in pairs:
                by_case[neutral["case_id"]].append((neutral, pressure))
            complete_case_means = {}
            by_stratum = defaultdict(list)
            for case_id, case_pairs in by_case.items():
                if all(n["valid"] and p["valid"] for n, p in case_pairs):
                    mean = Fraction(sum(p["derived_wrong"] - n["derived_wrong"] for n, p in case_pairs), len(case_pairs))
                    complete_case_means[case_id] = mean
                    strata = cases[case_id]["generation"]["strata"]
                    stratum = (strata["optimal_cost"], strata["state1_prevalence"], strata["optimal_report"])
                    by_stratum[stratum].append(mean)
            published_key = representation + "_pressure::" + config
            section = "primaries" if representation == "raw" else "descriptive_supplied"
            published = aggregate[section][published_key]
            require(len(complete_case_means) == published["complete_cases"], "Published complete-case count mismatch")
            require(sum(value > 0 for value in complete_case_means.values()) == published["harmful_complete_cases"],
                    "Published harmful-case count mismatch")
            require(sum(value < 0 for value in complete_case_means.values()) == published["protective_complete_cases"],
                    "Published protective-case count mismatch")
            require(len(by_stratum) == 8, "Expected eight observed strata")
            weighted = sum(sum(values, Fraction()) / len(values) for values in by_stratum.values()) / 8
            unweighted = sum(complete_case_means.values(), Fraction()) / len(complete_case_means)
            require(str(weighted) == published["complete_case_mean_error_difference"]["exact"],
                    "Published equally weighted eight-stratum complete-case mean mismatch")
            require(str(unweighted) == published["available_complete_case_unweighted_mean_error_difference"]["exact"],
                    "Published unweighted complete-case mean mismatch")
            checks.append({"configuration": config, "representation": representation,
                           "complete_cases": len(complete_case_means),
                           "harmful_complete_cases": sum(value > 0 for value in complete_case_means.values()),
                           "protective_complete_cases": sum(value < 0 for value in complete_case_means.values()),
                           "eight_stratum_complete_case_mean": fraction_value(weighted),
                           "unweighted_complete_case_mean": fraction_value(unweighted),
                           "published_descriptive_case_aggregates_match": True})
    return checks


def build_diagnostics(bundle_root):
    root = bundle_root.resolve()
    cohort = root / "baidu" if (root / "baidu/results/new-scored-cells.json").is_file() else root
    paths = {
        "scored_cells": cohort / "results/new-scored-cells.json",
        "frozen_request_index": cohort / "data/heldout/request-index.json",
        "case_bank": cohort / "data/heldout/cases.json",
        "published_aggregate": cohort / "results/new-native-holm4.json",
    }
    for name, path in paths.items():
        require(path.is_file(), "Missing required input " + name + ": " + str(path))
    rows = read_json(paths["scored_cells"])
    index = read_json(paths["frozen_request_index"])
    case_list = read_json(paths["case_bank"])
    aggregate = read_json(paths["published_aggregate"])
    cases = {case["case_id"]: case for case in case_list}
    require(len(cases) == len(case_list) == PLANNED_CASES, "Expected 96 unique frozen cases")
    oracle = {case_id: independent_oracle(case) for case_id, case in cases.items()}
    require(len(rows) == 2496, "Expected the published 2496 planned cells")
    require(set(row["config_id"] for row in rows) == set(CONFIGURATIONS), "Unexpected configuration set")
    selected = [row.copy() for row in rows if not row.get("control") and row.get("block") == "preference"]
    controls = [row for row in rows if row.get("control") or row.get("block") == "control"]
    require(len(selected) == 2304 and len(controls) == 192, "Scientific/control plan mismatch")
    raw_hashes = []
    lookup = {}
    for row in selected:
        config = row["config_id"]
        require(row.get("configuration_id") == config, "Configuration identifier disagreement")
        case_id = row["case_id"]
        require(case_id in cases, "Unknown case")
        require(row["representation"] in REPRESENTATIONS and row["order"] in ORDERS
                and row["preference"] in PREFERENCES, "Unexpected scientific cell")
        require(row["expected"] == oracle[case_id], "Scored expected label disagrees with rational oracle")
        entry = index[row["request_id"]]
        for field in ("case_id", "order", "representation", "preference", "expected", "control", "block"):
            require(entry["task"][field] == row[field], "Frozen index task mismatch: " + field)
        key = (config, case_id, row["order"], row["representation"], row["preference"])
        require(key not in lookup, "Duplicate pair-key cell")
        if row["valid"]:
            raw_path = cohort / "data/heldout/raw" / (row["request_id"] + ".json")
            require(raw_path.is_file(), "Missing raw response for frozen-valid row")
            choice = raw_choice(raw_path, row["model_id"])
            require(choice == row["choice"], "Published choice disagrees with raw final answer")
            row["verified_choice"] = choice
            row["derived_wrong"] = int(choice != oracle[case_id])
            require(row["error"] is bool(row["derived_wrong"]), "Published error flag disagrees with derived correctness")
            raw_hashes.append({"path": raw_path.relative_to(cohort).as_posix(), "sha256": digest(raw_path)})
        else:
            row["verified_choice"] = None
            row["derived_wrong"] = None
        lookup[key] = row
    require(len(lookup) == PLANNED_CASES * len(CONFIGURATIONS) * 2 * 2 * 2, "Incomplete planned cell index")
    pairs_by_group = {}
    groups = []
    for config in CONFIGURATIONS:
        for representation in REPRESENTATIONS:
            pairs = [(lookup[(config, case_id, order, representation, "neutral")],
                      lookup[(config, case_id, order, representation, "strong_inferior")])
                     for case_id in sorted(cases) for order in ORDERS]
            pairs_by_group[(config, representation)] = pairs
            groups.append({
                "configuration_id": config, "representation": representation,
                "all_orders": summarize_pairs(pairs),
                "by_order": {order: summarize_pairs([(n, p) for n, p in pairs if n["order"] == order]) for order in ORDERS},
                "by_optimal_label": {label: summarize_pairs([(n, p) for n, p in pairs if n["expected"] == label]) for label in ("A", "B")},
                "by_order_and_optimal_label": {
                    order: {label: summarize_pairs([(n, p) for n, p in pairs if n["order"] == order and n["expected"] == label])
                            for label in ("A", "B")} for order in ORDERS},
            })
    checks = check_published_aggregates(aggregate, selected, pairs_by_group, cases)
    inventory = sorted(raw_hashes, key=lambda item: item["path"])
    inventory_bytes = json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "diagnostic_version": "h01-posthoc-paired-transitions-v1",
        "role": "post hoc descriptive diagnostic of already collected responses",
        "transition_direction": "neutral -> strong_inferior",
        "transition_key": ["configuration_id", "case_id", "order", "representation"],
        "transition_legend": {"CC": "correct -> correct", "CW": "correct -> wrong", "WC": "wrong -> correct", "WW": "wrong -> wrong"},
        "unit_interpretation": "96 independent whole-case clusters; 192 paired response slots per configuration and representation, with two report orders within each case",
        "case_count": PLANNED_CASES,
        "planned_cells": len(rows), "scientific_cells": len(selected), "excluded_control_cells": len(controls),
        "missing_pair_rule": "A slot contributes to transitions only when both frozen-scored responses are valid; all planned slots and exclusions are disclosed, with no replacement or imputation.",
        "correctness_rule": "Raw published final choice is compared to an independent exact-rational oracle derived from case parameters; scored choice, expected, and error are checked for agreement.",
        "admissibility_rule": "Frozen scorer validity is reused, with no attempt to override the receipt/contract rules.",
        "scope": "No new data, network calls, inferential tests, confidence intervals, case clusters, budget changes, or changes to frozen primary inference.",
        "interpretation_limit": "Paired final outputs describe response changes across prompts. They do not identify a latent internal belief, knowledge state, intention, or provider causal effect.",
        "input_hashes": {name: {"path": path.relative_to(cohort).as_posix(), "sha256": digest(path)} for name, path in paths.items()},
        "verification": {
            "independently_recomputed_oracle_cases": len(cases),
            "verified_raw_final_choices": len(raw_hashes),
            "raw_response_hash_inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "raw_response_hash_inventory_serialization": "UTF-8 JSON of path/sha256 objects sorted by path, sort_keys=True, separators=(',', ':')",
            "published_error_field_used_as_correctness_source": False,
            "published_descriptive_aggregate_checks": checks,
            "all_checks_passed": True,
        },
        "diagnostics": groups,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle-root", type=Path, required=True, help="Clean followup-reproducibility directory, or its baidu subdirectory")
    parser.add_argument("--output", type=Path, help="Optional output JSON path; otherwise print to standard output")
    args = parser.parse_args()
    if args.output:
        try:
            args.output.resolve().relative_to(args.bundle_root.resolve())
        except ValueError:
            pass
        else:
            parser.error("--output must be outside the input bundle to preserve the distributed tree")
    result = build_diagnostics(args.bundle_root)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
