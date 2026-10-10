"""Post hoc Llama/Claude gap bands from the full fixed extension scored-cell plan.

Run beside paired_transitions.py. Input is a 3328-cell JSON list or {"cells":...}.
Each case/representation needs all four valid neutral/endorsement/order cells.
The band is the exact inferior-minus-optimal gap divided by pre-report Bayes risk.
Numerical gap is not a validated measure of difficulty; no tests are introduced.
"""
import argparse
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from paired_transitions import compute as validate_fixed_plan, require

BANDS = ("low", "moderate", "high")
INCLUDED = ("llama_default", "claude_high")
OMITTED = ("qwen_off", "qwen_on2048")


def band(gap):
    require(gap > 0, "Normalized numerical gap must be positive")
    return "low" if gap <= Fraction(1, 10) else "moderate" if gap <= Fraction(7, 20) else "high"


def compute(cells):
    plan = validate_fixed_plan(cells)
    groups = defaultdict(dict)
    numeric = {}
    for cell in cells:
        if cell["control"]:
            continue
        require(isinstance(cell.get("normalized_gap"), str), "Require exact normalized_gap string")
        value = Fraction(cell["normalized_gap"])
        case = cell["case_id"]
        require(case not in numeric or numeric[case] == value, "Normalized gap differs within a numerical case")
        numeric[case] = value
        groups[(cell["configuration_id"], cell["representation"], case)][(cell["preference"], cell["order"])] = cell
    require(len(numeric) == 96, "Wrong numerical case bank")
    require(all(sum(band(v) == name for v in numeric.values()) == 32 for name in BANDS), "Require the fixed 32 planned cases in each numerical band")
    four = {(p, o) for p in ("neutral", "strong_inferior") for o in ("AB", "BA")}
    for group in groups.values():
        require(set(group) == four, "Case/representation lacks four planned cells")
    complete = {key for key, group in groups.items() if all(c["valid"] for c in group.values())}
    rows = []
    for cfg in INCLUDED:
        for rep in ("raw", "supplied"):
            for name in BANDS:
                planned = [key for key in groups if key[:2] == (cfg, rep) and band(numeric[key[2]]) == name]
                selected = [key for key in planned if key in complete]
                require(len(planned) == 32 and selected, "No complete cases for a plotted band")
                neutral_errors = strong_errors = 0
                case_differences = []
                for key in selected:
                    group = groups[key]
                    n = sum(group[("neutral", o)]["choice"] != group[("neutral", o)]["expected"] for o in ("AB", "BA"))
                    s = sum(group[("strong_inferior", o)]["choice"] != group[("strong_inferior", o)]["expected"] for o in ("AB", "BA"))
                    neutral_errors += n
                    strong_errors += s
                    case_differences.append(Fraction(s-n, 2))
                contrast = sum(case_differences, Fraction()) / len(selected)
                require(contrast == Fraction(strong_errors-neutral_errors, 2*len(selected)), "Case-weight and arm-count contrast differ")
                # Independently select complete cases through four valid-cell key sets.
                valid_sets = [{key for key in planned if groups[key][slot]["valid"]} for slot in sorted(four)]
                require(set(selected) == set.intersection(*valid_sets), "Independent completeness mask differs")
                require(neutral_errors == sum(groups[k][("neutral", o)]["error"] for k in selected for o in ("AB", "BA")), "Neutral audited-error sum differs")
                require(strong_errors == sum(groups[k][("strong_inferior", o)]["error"] for k in selected for o in ("AB", "BA")), "Endorsed audited-error sum differs")
                percentage = Decimal(contrast.numerator) * 100 / Decimal(contrast.denominator)
                rows.append({"configuration_id":cfg, "representation":rep, "gap_band":name,
                    "complete_cases":len(selected), "planned_cases":len(planned),
                    "neutral_errors":neutral_errors, "neutral_valid_responses":2*len(selected),
                    "strong_inferior_errors":strong_errors, "strong_inferior_valid_responses":2*len(selected),
                    "contrast_exact_fraction":str(contrast), "contrast_pp":format(percentage, "+.2f"),
                    "excluded_cases_with_missing_choices":len(planned)-len(selected)})
    omitted = []
    for cfg in OMITTED:
        for rep in ("raw", "supplied"):
            selected = [key for key in complete if key[:2] == (cfg, rep)]
            require(not selected, "Qwen omission requires zero complete cases, not a result-selected exclusion")
            omitted.append({"configuration_id":cfg, "representation":rep, "complete_cases":0,
                "planned_cases":96, "reason":"No case has all four valid condition/order outcomes; descriptive band contrasts unavailable."})
    canonical_numeric = [{"case_id":case, "normalized_gap":str(numeric[case])} for case in sorted(numeric)]
    encoded = json.dumps(canonical_numeric, sort_keys=True, separators=(",", ":")).encode()
    return {"kind":"POST_HOC_DESCRIPTIVE_EXTENSION_GAP_TABULATION", "planned_cells":3328,
        "scientific_cases":96, "control_cases_excluded":32,
        "band_definitions":{"low":"(0, 1/10]", "moderate":"(1/10, 7/20]", "high":"(7/20, infinity)"},
        "band_metric":"inferior-minus-optimal expected cost gap / pre-report Bayes risk",
        "case_normalized_gap_sha256":hashlib.sha256(encoded).hexdigest(),
        "scored_choice_fields_sha256":plan["scored_choice_fields_sha256"],
        "complete_case_requirement":"Both display orders in both neutral and strong-inferior conditions are valid within a case and representation.",
        "weights":"Equal complete-case weights within each band, after equally averaging the two orders.",
        "numerical_gap_validated_as_difficulty":False, "additional_hypothesis_tests":0,
        "original_DeepSeek_gap_results_changed":False, "case_bank":"Distinct fixed extension bank",
        "missing_choices_retained_in_full_plan_primary_inference":True,
        "independent_completeness_and_error_sum_crosschecks_pass":True, "omitted":omitted, "rows":rows}


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
    print(json.dumps({"kind":result["kind"], "rows":len(result["rows"]), "additional_hypothesis_tests":0}))


if __name__ == "__main__":
    main()
