"""Offline descriptive transitions for the full fixed extension scored-cell plan.

Input is a JSON list of 3328 scored cells, or {"cells": [...]}.
Use reproduced-cells.json from the public extension companion. Correctness is
computed from choice == expected and checked against each supplied error field.
Orders are nested within cases; these response-pair counts add no inference.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

CONFIGURATIONS = ("qwen_off", "qwen_on2048", "llama_default", "claude_high")
REPRESENTATIONS = ("raw", "supplied")
CONDITIONS = ("neutral", "strong_inferior")
STATES = ("CC", "CW", "WC", "WW")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compute(cells):
    require(isinstance(cells, list) and len(cells) == 3328, "Require all 3328 planned cells, including missing choices")
    groups = defaultdict(dict)
    requests = set()
    science_cases = set()
    control_cases = set()
    configuration_counts = Counter()
    control_keys = set()
    canonical_rows = []
    for cell in cells:
        required = ("request_id", "configuration_id", "case_id", "order", "representation", "preference", "control", "block", "split", "valid", "choice", "expected", "error")
        require(isinstance(cell, dict) and all(k in cell for k in required), "Missing required scored-cell field")
        cfg, case, order = cell["configuration_id"], cell["case_id"], cell["order"]
        require(cfg in CONFIGURATIONS and cell.get("config_id", cfg) == cfg, "Unexpected/inconsistent configuration")
        require(isinstance(case, str) and case and order in ("AB", "BA"), "Invalid case/order")
        require(cell["split"] == "heldout", "Require held-out cells")
        require(isinstance(cell["request_id"], str) and cell["request_id"] not in requests, "Duplicate/invalid request ID")
        requests.add(cell["request_id"])
        configuration_counts[cfg] += 1
        require(type(cell["valid"]) is bool and type(cell["control"]) is bool, "valid/control must be literal booleans")
        require(cell["expected"] in ("A", "B"), "Invalid exact-reference choice")
        if cell["valid"]:
            require(cell["choice"] in ("A", "B") and type(cell["error"]) is bool, "Invalid valid-choice/error field")
            require(cell["error"] == (cell["choice"] != cell["expected"]), "Error field conflicts with independent choice/reference comparison")
        else:
            require(cell["choice"] is None and cell["error"] is None, "A missing outcome must not carry a scored choice/error")
        canonical_rows.append({k: cell[k] for k in required})
        if cell["control"]:
            require(cell["block"] == "control" and cell["representation"] == "supplied" and cell["preference"] == "neutral", "Unexpected control condition")
            key = (cfg, case, order)
            require(key not in control_keys, "Duplicate control cell")
            control_keys.add(key)
            control_cases.add(case)
            continue
        require(cell["block"] == "preference" and cell["representation"] in REPRESENTATIONS and cell["preference"] in CONDITIONS, "Unexpected scientific condition")
        science_cases.add(case)
        key = (cfg, cell["representation"], case, order)
        require(cell["preference"] not in groups[key], "Duplicate scientific condition")
        groups[key][cell["preference"]] = cell
    require(configuration_counts == Counter({c: 832 for c in CONFIGURATIONS}), "Wrong configuration allocation")
    require(len(science_cases) == 96 and len(control_cases) == 32 and not science_cases & control_cases, "Require the fixed 96-case/32-control banks")
    require(control_keys == {(c, i, o) for c in CONFIGURATIONS for i in control_cases for o in ("AB", "BA")}, "Incomplete planned control grid")
    expected_keys = {(c, r, i, o) for c in CONFIGURATIONS for r in REPRESENTATIONS for i in science_cases for o in ("AB", "BA")}
    require(set(groups) == expected_keys, "Incomplete scientific case/order grid")
    for pair in groups.values():
        require(set(pair) == set(CONDITIONS), "Pair lacks a planned condition")
        require(pair["neutral"]["expected"] == pair["strong_inferior"]["expected"], "Matched prompt reference differs")
    rows = []
    for cfg in CONFIGURATIONS:
        for rep in REPRESENTATIONS:
            selected = {k: p for k, p in groups.items() if k[:2] == (cfg, rep)}
            counts = Counter({s: 0 for s in STATES})
            paired_keys = set()
            arm_valid = Counter()
            arm_errors = Counter()
            for key, pair in selected.items():
                for condition, cell in pair.items():
                    if cell["valid"]:
                        arm_valid[condition] += 1
                        arm_errors[condition] += int(cell["choice"] != cell["expected"])
                neutral, strong = pair["neutral"], pair["strong_inferior"]
                if neutral["valid"] and strong["valid"]:
                    state = ("C" if neutral["choice"] == neutral["expected"] else "W") + ("C" if strong["choice"] == strong["expected"] else "W")
                    counts[state] += 1
                    paired_keys.add(key)
            # Independent join/count using the audited error fields instead of choices.
            neutral = {k: p["neutral"] for k, p in selected.items() if p["neutral"]["valid"]}
            strong = {k: p["strong_inferior"] for k, p in selected.items() if p["strong_inferior"]["valid"]}
            joined = set(neutral) & set(strong)
            crosscheck = Counter({s: 0 for s in STATES})
            for key in joined:
                crosscheck[("W" if neutral[key]["error"] else "C") + ("W" if strong[key]["error"] else "C")] += 1
            require(counts == crosscheck and paired_keys == joined, "Independent transition count differs")
            require(counts["WC"] + counts["WW"] == sum(neutral[k]["error"] for k in joined), "Paired neutral-error count differs")
            require(counts["CW"] + counts["WW"] == sum(strong[k]["error"] for k in joined), "Paired endorsed-error count differs")
            require(arm_errors["neutral"] == sum(c["error"] for c in neutral.values()) and arm_errors["strong_inferior"] == sum(c["error"] for c in strong.values()), "Observed arm-error count differs")
            per_case = Counter(k[2] for k in paired_keys)
            rows.append({"configuration_id": cfg, "representation": rep,
                "planned_pairs": 192, "valid_pairs": len(joined), "missing_pairs": 192-len(joined),
                "CC": counts["CC"], "CW": counts["CW"], "WC": counts["WC"], "WW": counts["WW"],
                "cases_with_any_valid_pair": len(per_case), "complete_cases_with_both_orders": sum(n == 2 for n in per_case.values()),
                "neutral_errors": arm_errors["neutral"], "neutral_valid_responses": arm_valid["neutral"],
                "strong_inferior_errors": arm_errors["strong_inferior"], "strong_inferior_valid_responses": arm_valid["strong_inferior"],
                "paired_neutral_errors": counts["WC"]+counts["WW"], "paired_strong_inferior_errors": counts["CW"]+counts["WW"]})
    payload = json.dumps(sorted(canonical_rows, key=lambda c: c["request_id"]), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"kind": "POST_HOC_DESCRIPTIVE_TRANSITION_TABULATION", "planned_cells": 3328,
        "scientific_cases": 96, "control_cases_excluded": 32, "planned_pairs_per_row": 192,
        "pair_key": ["configuration_id", "representation", "case_id", "order"],
        "conditions": ["neutral", "strong_inferior"],
        "correctness_definition": "choice == expected", "requires_both_responses_valid": True,
        "scored_choice_fields_sha256": hashlib.sha256(payload).hexdigest(),
        "independent_join_error_field_and_arm_crosschecks_pass": True,
        "additional_hypothesis_tests": 0, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored-cells", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.scored_cells.read_text())
    cells = value.get("cells") if isinstance(value, dict) else value
    result = compute(cells)
    require(not args.output.exists(), "Use a new output file; existing evidence is preserved")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"kind": result["kind"], "rows": len(result["rows"]), "additional_hypothesis_tests": 0}))


if __name__ == "__main__":
    main()
