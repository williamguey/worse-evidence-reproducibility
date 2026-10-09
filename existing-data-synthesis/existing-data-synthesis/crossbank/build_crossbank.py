#!/usr/bin/env python3
"""Extract existing pressure results; validate counts/means without new inference.

All inputs are already reproduced scientific outputs. This script does not import
scientific inference modules, send requests, or rewrite input files.
"""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path


INPUTS = {
    "original_analysis": "projection/followup-reproducibility/original/results/heldout/analysis.json",
    "matched_analysis": "projection/followup-reproducibility/baidu/results/new-native-holm4.json",
    "matched_holm10": "projection/followup-reproducibility/baidu/results/paper-holm10.json",
    "matched_cells": "projection/followup-reproducibility/baidu/results/new-scored-cells.json",
    "matched_pairs": "reproduction-output/transition-diagnostics.json",
    "popular_analysis": "reproduction-output/extension/reproduced-analysis.json",
    "popular_cells": "reproduction-output/extension/reproduced-cells.json",
    "popular_pairs": "reproduction-output/extension-transitions.json",
    "shared_analysis": "reproduction-output/construct-validation/analysis.json",
    "shared_cells": "reproduction-output/construct-validation/scored.json",
}
LABELS = {
    "deepseek/deepseek-v4-pro-0813": ("DeepSeek v4 Pro (off)", "deepseek/deepseek-v4-pro-0813", "off"),
    "google/gemini-3.8-flash": ("Gemini 3.8 Flash (low)", "google/gemini-3.8-flash", "low"),
    "openai/gpt-5.6-luna": ("GPT-5.6 Luna (off)", "openai/gpt-5.6-luna", "off"),
    "ds_off_bd": ("DeepSeek v4 Pro (off)", "deepseek/deepseek-v4-pro-0813", "off"),
    "ds_low_bd": ("DeepSeek v4 Pro (low)", "deepseek/deepseek-v4-pro-0813", "low"),
    "gpt6_luna_low": ("GPT-6 Luna (low)", "openai/gpt-6-luna", "low"),
    "llama_default": ("Llama 4 Maverick (default)", "meta-llama/llama-4-maverick", "default"),
    "claude_high": ("Claude Sonnet 5.5 (high)", "anthropic/claude-sonnet-5.5", "high"),
    "deepseek_off": ("DeepSeek v4 Pro (off)", "deepseek/deepseek-v4-pro-0813", "off"),
    "luna_off": ("GPT-5.6 Luna (off)", "openai/gpt-5.6-luna", "off"),
}
BANKS = {
    "original96": ("Original three-model bank (96 cases)", 96),
    "matched96": ("Matched-configuration bank (96 cases)", 96),
    "popular96": ("Popular-model bank (96 cases)", 96),
    "shared312": ("Shared-condition bank (312 cases)", 312),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(x):
    return Fraction(x["exact"]) if isinstance(x, dict) else Fraction(x)


def check_close(left, right, name):
    assert abs(float(left) - float(right)) < 1e-12, (name, left, right)


def derive(cells, bank, config, representation):
    """Direct count and exact case-level arithmetic over planned scored cells."""
    by_case = defaultdict(dict)
    plus_name, minus_name = ("bundle_bad", "neutral_2") if bank == "shared312" else ("strong_inferior", "neutral")
    for c in cells:
        if bank == "original96":
            block, rep, tag, cond = c["condition"]
            selected = c["model"] == config and block == "preference" and rep == representation and tag == "none"
        elif bank == "shared312":
            cond = c["condition"]
            selected = c["model_id"] == config and c["kind"] == "science"
        else:
            cond = c["preference"]
            selected = c["configuration_id"] == config and not c["control"] and c["representation"] == representation
        if not selected or cond not in (plus_name, minus_name):
            continue
        key = (cond, c["order"])
        assert key not in by_case[c["case_id"]], (bank, config, key)
        valid = c["error"] is not None if bank == "shared312" else c["valid"]
        if valid and "expected" in c:
            assert int(c["error"]) == int(c["choice"] != c["expected"])
        assert not valid or int(c["error"]) in (0, 1)
        by_case[c["case_id"]][key] = int(c["error"]) if valid else None
    n = BANKS[bank][1]
    assert len(by_case) == n, (bank, config, representation, len(by_case), n)
    values = {}
    totals = {"valid_pairs": 0, "missing_plus": 0, "missing_minus": 0,
              "valid_plus": 0, "valid_minus": 0, "errors_plus": 0, "errors_minus": 0,
              "CC": 0, "CW": 0, "WC": 0, "WW": 0}
    for case, slot in by_case.items():
        assert set(slot) == {(c, o) for c in (plus_name, minus_name) for o in ("AB", "BA")}
        lower = upper = Fraction(0)
        complete = True
        for order in ("AB", "BA"):
            p, m = slot[(plus_name, order)], slot[(minus_name, order)]
            for arm, v, sign in (("plus", p, 1), ("minus", m, -1)):
                if v is None:
                    totals["missing_" + arm] += 1
                    complete = False
                    lower += Fraction(min(0, sign), 2)
                    upper += Fraction(max(0, sign), 2)
                else:
                    totals["valid_" + arm] += 1
                    totals["errors_" + arm] += v
                    lower += Fraction(sign * v, 2)
                    upper += Fraction(sign * v, 2)
            if p is not None and m is not None:
                totals["valid_pairs"] += 1
                totals[("W" if m else "C") + ("W" if p else "C")] += 1
        values[case] = {"complete": complete, "lower": lower, "upper": upper,
                        "value": lower if complete else None}
    complete = [v["value"] for v in values.values() if v["complete"]]
    totals.update({"complete_cases": len(complete), "planned_cases": n,
                   "planned_pairs": 2 * n, "missing_pairs": 2 * n - totals["valid_pairs"],
                   "unweighted_case_mean": sum(complete, Fraction(0)) / len(complete),
                   "pair_mean": Fraction(totals["CW"] - totals["WC"], totals["valid_pairs"]),
                   "lower": sum((v["lower"] for v in values.values()), Fraction(0)) / n,
                   "upper": sum((v["upper"] for v in values.values()), Fraction(0)) / n})
    return values, totals


def weighted_mean(records, values):
    """Retain the native equal-eight-stratum complete-case descriptive target."""
    groups = defaultdict(list)
    for r in records:
        v = values[r["case_id"]]
        assert v["complete"] == r["complete"]
        assert v["lower"] == Fraction(r["error_lower"])
        assert v["upper"] == Fraction(r["error_upper"])
        if v["complete"]:
            assert v["value"] == Fraction(r["error_difference"])
            groups[tuple(r["stratum"])].append(v["value"])
    assert len(groups) == 8 and all(groups.values())
    return sum((sum(v, Fraction(0)) / len(v) for v in groups.values()), Fraction(0)) / 8


def row(bank, config, representation, native, data, source_id, selector, ci=None, family=None, primary=False):
    cells = data["original_analysis"]["cells"] if bank == "original96" else data[bank.replace("96", "").replace("312", "") + "_cells"]
    values, d = derive(cells, bank, config, representation)
    if bank == "shared312":
        check_close(d["unweighted_case_mean"], native["complete_case_descriptive"]["mean"], "shared native mean")
        check_close(d["lower"], native["identification_interval"][0], "shared lower")
        check_close(d["upper"], native["identification_interval"][1], "shared upper")
        mean = d["unweighted_case_mean"]
        weight = "equal weight over complete whole-case clusters; two display orders nested"
        assert d["complete_cases"] == native["complete_cases"]
    else:
        mean = exact(native["complete_case_mean_error_difference"])
        computed = weighted_mean(native["case_records"], values) if bank != "original96" else d["unweighted_case_mean"]
        assert computed == mean, (bank, config, representation, computed, mean)
        assert d["complete_cases"] == native["complete_cases"]
        assert d["planned_cases"] == native["planned_cases"]
        assert d["lower"] == exact(native["fixed_plan_error_bounds"]["lower"])
        assert d["upper"] == exact(native["fixed_plan_error_bounds"]["upper"])
        if bank == "original96":
            assert d["valid_pairs"] == native["complete_pairs"]
            assert d["missing_plus"] == native["missingness"]["plus"]
            assert d["missing_minus"] == native["missingness"]["minus"]
            weight = "equal weight over available complete whole-case clusters; two display orders nested"
        else:
            assert d["missing_plus"] + d["missing_minus"] == native["missing_requests"]
            assert d["unweighted_case_mean"] == exact(native["available_complete_case_unweighted_mean_error_difference"])
            weight = "equal eight-stratum weights over available complete whole-case clusters; two display orders nested"
        for r in native["case_records"]:
            v = values[r["case_id"]]
            assert v["complete"] == r["complete"]
            assert v["lower"] == Fraction(r["error_lower"])
            assert v["upper"] == Fraction(r["error_upper"])
    label, model, mode = LABELS[config]
    output = {"bank_id": bank, "bank_label": BANKS[bank][0], "configuration_id": config,
              "configuration_label": label, "model_id": model, "mode": mode,
              "representation": representation,
              "contrast": "inferior bundled endorsement minus second neutral repeat" if bank == "shared312" else "strong inferior endorsement minus neutral",
              "status": "frozen primary endpoint" if primary else "descriptive per-configuration contrast",
              "inference_family": family, "mean_target": weight,
              "mean_exact": str(mean), "mean_error_difference": float(mean), "mean_percentage_points": 100 * float(mean),
              "unweighted_complete_case_mean_exact": str(d["unweighted_case_mean"]),
              "valid_pair_mean_exact": str(d["pair_mean"]),
              "identification_lower_exact": str(d["lower"]), "identification_upper_exact": str(d["upper"]),
              "identification_lower_pp": 100 * float(d["lower"]), "identification_upper_pp": 100 * float(d["upper"]),
              "simultaneous_ci_lower_pp": 100 * ci[0] if ci is not None else None,
              "simultaneous_ci_upper_pp": 100 * ci[1] if ci is not None else None,
              "ci_role": "existing family-simultaneous 95% full-plan confidence envelope" if ci is not None else "no native per-configuration confidence interval; no new interval computed",
              "planned_cases": d["planned_cases"], "complete_cases": d["complete_cases"],
              "planned_pairs": d["planned_pairs"], "valid_pairs": d["valid_pairs"], "missing_pairs": d["missing_pairs"],
              "valid_neutral": d["valid_minus"], "valid_endorsement": d["valid_plus"],
              "missing_neutral": d["missing_minus"], "missing_endorsement": d["missing_plus"],
              "errors_neutral": d["errors_minus"], "errors_endorsement": d["errors_plus"],
              "harmful_pairs": d["CW"], "reverse_pairs": d["WC"],
              "native_source_id": source_id, "native_selector": selector,
              "ci_source_id": "matched_holm10" if bank == "matched96" and ci is not None else source_id if ci is not None else None,
              "case_reuse": "GPT-6 Luna assignments are reused once unchanged; repeated provider panels are not new cases" if bank == "matched96" else "none between the four distinct case banks",
              "independent_count_check": "PASS", "exact_mean_and_identification_check": "PASS"}
    return output, d


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reproduction-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audited-shared-analysis", type=Path)
    args = parser.parse_args()
    data = {k: json.loads((args.reproduction_root / v).read_text()) for k, v in INPUTS.items()}
    before = {k: sha(args.reproduction_root / v) for k, v in INPUTS.items()}
    if args.audited_shared_analysis:
        audited = json.loads(args.audited_shared_analysis.read_text())
        assert data["shared_analysis"]["arm_summaries"] == audited["arm_summaries"]
        for config in ["llama_default", "deepseek_off", "luna_off"]:
            reproduced = next(r for r in data["shared_analysis"]["primary"] if r["model_id"] == config and r["endpoint"] == "bundle_worsening")
            original = next(r for r in audited["primary"] if r["model_id"] == config and r["endpoint"] == "bundle_worsening")
            for field in ["model_id", "endpoint", "planned_cases", "complete_cases", "identification_interval", "family_95_envelope_ci", "holm9_p", "reject_positive_holm9"]:
                assert reproduced[field] == original[field], (config, field)
            assert reproduced["complete_case_descriptive"]["mean"] == original["complete_case_descriptive"]["mean"]
    rows, checks = [], []
    for config in ["deepseek/deepseek-v4-pro-0813", "openai/gpt-5.6-luna", "google/gemini-3.8-flash"]:
        for rep in ["raw", "supplied"]:
            sec = data["original_analysis"]["primaries"]["preference_primary"] if rep == "raw" else data["original_analysis"]["descriptive_secondary"]["preference_supplied_strong"]
            selector = ("primaries.preference_primary" if rep == "raw" else "descriptive_secondary.preference_supplied_strong") + ".per_model." + config
            r, d = row("original96", config, rep, sec["per_model"][config], data, "original_analysis", selector)
            rows.append(r)
    h10_names = {"ds_off_bd": "baidu.raw_pressure.off", "ds_low_bd": "baidu.raw_pressure.low", "gpt6_luna_low": "openai.raw_pressure.luna_low"}
    for config in h10_names:
        for rep in ["raw", "supplied"]:
            sec = "primaries" if rep == "raw" else "descriptive_supplied"
            key = rep + "_pressure::" + config
            native = data["matched_analysis"][sec][key]
            h10 = data["matched_holm10"]["primaries"][h10_names[config]] if rep == "raw" else None
            ci = h10["simultaneous_family_confidence_interval_95"] if h10 else None
            r, d = row("matched96", config, rep, native, data, "matched_analysis", sec + "." + key, ci, "Holm10" if h10 else None, bool(h10))
            diag = next(x["all_orders"] for x in data["matched_pairs"]["diagnostics"] if x["configuration_id"] == config and x["representation"] == rep)
            assert diag["complete_paired_response_slots"] == d["valid_pairs"]
            assert diag["transitions_neutral_to_pressure"]["CW"] == d["CW"]
            assert diag["transitions_neutral_to_pressure"]["WC"] == d["WC"]
            if h10:
                r["ci_selector"] = "primaries." + h10_names[config] + ".simultaneous_family_confidence_interval_95"
            rows.append(r)
    for config in ["llama_default", "claude_high"]:
        for rep in ["raw", "supplied"]:
            sec = "primaries" if rep == "raw" else "descriptive_supplied"
            key = rep + "_pressure::" + config
            native = data["popular_analysis"][sec][key]
            ci = native["inference"]["simultaneous_family_confidence_interval_95"] if rep == "raw" else None
            r, d = row("popular96", config, rep, native, data, "popular_analysis", sec + "." + key, ci, "Holm5" if ci else None, bool(ci))
            diag = next(x for x in data["popular_pairs"]["rows"] if x["configuration_id"] == config and x["representation"] == rep)
            assert diag["valid_pairs"] == d["valid_pairs"]
            assert diag["complete_cases_with_both_orders"] == d["complete_cases"]
            assert diag["CW"] == d["CW"] and diag["WC"] == d["WC"]
            rows.append(r)
    for config in ["llama_default", "deepseek_off", "luna_off"]:
        native = next(x for x in data["shared_analysis"]["primary"] if x["model_id"] == config and x["endpoint"] == "bundle_worsening")
        r, d = row("shared312", config, "supplied", native, data, "shared_analysis", "primary[model_id=" + config + ",endpoint=bundle_worsening]", native["family_95_envelope_ci"], "Holm9", True)
        for cond, arm in [("bundle_bad", "plus"), ("neutral_2", "minus")]:
            a = next(x for x in data["shared_analysis"]["arm_summaries"] if x["model_id"] == config and x["condition"] == cond)
            assert a["valid"] == d["valid_" + arm]
            assert a["errors"] == d["errors_" + arm]
            assert a["missing"] == d["missing_" + arm]
        rows.append(r)
    assert len(rows) == 19
    after = {k: sha(args.reproduction_root / v) for k, v in INPUTS.items()}
    assert before == after
    result = {
        "kind": "existing-audited-data cross-bank pressure forest input",
        "additional_requests": 0, "additional_hypothesis_tests": 0, "additional_inference": False,
        "row_count": len(rows), "configuration_bank_slots": 11,
        "four_separate_case_banks": {k: {"label": v[0], "cases": v[1]} for k, v in BANKS.items()},
        "pooling": "none; native bank-specific targets and multiplicity families retained",
        "contrast_limit": "Raw prompts require cost calculation; supplied prompts state expected totals. The 312-case bank tests a bundled endorsement against a second neutral repeat. These are different contrasts and cannot be interpreted as isolated deliberation or causal provider effects.",
        "missingness_limit": "Identification bounds allow arbitrary missing binary choices. They are not confidence intervals and do not correct shared-service dependence.",
        "ci_limit": "Only already published native family-simultaneous intervals are shown. Original per-model and older supplied contrasts have no native interval; absence of a CI is not precision or equivalence evidence.",
        "point_limit": "Native complete-case points can fall outside full-plan identification bounds when unavailable outcomes change the target or weighting; both are retained and distinguished.",
        "independence": "Confidence coverage assumes independence across whole-case clusters; configurations and display orders within each case are not independent cases.",
        "reuse": "The matched 96-case bank was repeated across retired provider stages; GPT-6 Luna records were reused exactly once unchanged. Repeated cases are not added to N.",
        "excluded_main_rows": "Partial Qwen, retired DeepInfra and unavailable CoreWeave endpoints remain in existing scientific supplements; no main forest row treats these as a completed evaluation.",
        "input_commitments": {k: {"relative_path": INPUTS[k], "sha256": before[k]} for k in INPUTS},
        "rows": rows,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "crossbank-pressure.json").write_text(json.dumps(result, indent=2) + "\n")
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (args.out / "crossbank-pressure.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    check = {"status": "EXACT_EXISTING_DATA_ARITHMETIC_CHECK_PASS", "rows_checked": len(rows),
             "checks": ["scored-cell uniqueness and four planned choice slots per case", "binary error equals choice mismatch where oracle is present", "case complete/planned counts", "exact native mean and native weighting", "exact fixed-plan missingness endpoints", "independent paired-summary counts for matched and popular banks", "36-arm source summaries for selected shared312 arms", "existing interval extraction only", "all input bytes unchanged"],
             "input_commitments": result["input_commitments"],
             "output_commitments": {p.name: sha(p) for p in [args.out / "crossbank-pressure.json", args.out / "crossbank-pressure.csv"]},
             "existing_data_only": True, "new_inference": False}
    if args.audited_shared_analysis:
        check["audited_shared_analysis_sha256"] = sha(args.audited_shared_analysis)
        check["shared_forest_fields_and_all_arm_counts_exactly_match_audited_analysis"] = True
        check["full_analysis_float_equality_not_asserted"] = "Offline reproduction differs only at floating-point rounding in other descriptive fields; plotted bundle means, counts, identification bounds and simultaneous intervals match exactly."
    (args.out / "crossbank-checks.json").write_text(json.dumps(check, indent=2) + "\n")
    print(json.dumps({"status": check["status"], "rows": len(rows), "input_bytes_unchanged": True}))


if __name__ == "__main__":
    main()
