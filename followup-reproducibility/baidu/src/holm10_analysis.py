"""Prospective ten-endpoint paper family with unavailable CoreWeave primaries.

The native panel analyses and source stay intact. Inputs are their raw
combined p-values and full-plan case-contrast intervals. Luna must be the
exact same endpoint in both panels and enters the final family once. The three CoreWeave main endpoints are retained as wholly unavailable; no
CoreWeave native result panel is fabricated. No provider-stage pooling or N>96.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "inference.py"
SOURCE_SHA256 = "123c58fe44e44599d221880c14360f03936cf0c8ee8194a0c206bb7ec98bd116"
ALPHA = .05
FAMILY = (
    "deepinfra.raw_pressure.off",
    "deepinfra.raw_pressure.low",
    "openai.raw_pressure.luna_low",
    "deepinfra.raw_reasoning_interaction.low_minus_off",
    "coreweave.raw_pressure.off",
    "coreweave.raw_pressure.low",
    "coreweave.raw_reasoning_interaction.low_minus_off",
    "baidu.raw_pressure.off",
    "baidu.raw_pressure.low",
    "baidu.raw_reasoning_interaction.low_minus_off",
)


def load_frozen():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError("Frozen inference source hash mismatch")
    spec = importlib.util.spec_from_file_location("h01_frozen_inference_holm7", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    if module.PRIMARY_FAMILY_SIZE != 4 or module.PLANNED_CASES != 96 or module.ALPHA != ALPHA:
        raise ValueError("Unexpected frozen inference constants")
    return module


def exact(value):
    if isinstance(value, (bool, float)) or not isinstance(value, (str, int)):
        raise ValueError("Case intervals require exact integer/rational inputs")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid rational case interval") from exc


def check_p(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("A raw combined p-value must be finite and in [0,1]")
    return float(value)


def holm10(raw_values: Mapping[str, float]):
    if set(raw_values) != set(FAMILY) or len(raw_values) != 10:
        raise ValueError("The paper family must contain exactly the ten named hypotheses")
    raw = {key: check_p(raw_values[key]) for key in FAMILY}
    order = sorted(FAMILY, key=lambda key: (raw[key], key))
    result, running = {}, 0.
    for rank, key in enumerate(order):
        running = max(running, (10-rank) * raw[key])
        adjusted = min(1., running)
        result[key] = {"raw_combined_p_value": raw[key], "holm_adjusted_p_value": adjusted,
                       "reject_at_0_05": adjusted <= ALPHA, "family_size": 10}
    return {key: result[key] for key in FAMILY}


def endpoint_rows(endpoint, amplitude, frozen):
    records = endpoint.get("case_records")
    if not isinstance(records, list) or len(records) != 96:
        raise ValueError("Each endpoint must retain all 96 planned cases")
    rows, identifiers = [], set()
    metadata_keys = ("stratum", "gap_band", "family", "gap", "normalized_gap")
    metadata = {}
    for record in records:
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in identifiers:
            raise ValueError("Missing or duplicate planned case identifier")
        identifiers.add(case_id)
        if any(key not in record for key in metadata_keys):
            raise ValueError("Full frozen case metadata is required")
        stratum = record["stratum"]
        if not isinstance(stratum, (list, tuple)) or tuple(stratum) not in frozen.STRATA:
            raise ValueError("Unplanned analysis stratum")
        lower, upper = exact(record["error_lower"]), exact(record["error_upper"])
        if not -amplitude <= lower <= upper <= amplitude:
            raise ValueError("Case interval violates its prespecified logical range")
        if record["gap_band"] not in frozen.GAPS or exact(record["gap"]) <= 0 or exact(record["normalized_gap"]) <= 0:
            raise ValueError("Invalid frozen gap metadata")
        row = dict(record, stratum=tuple(stratum), error_lower=lower, error_upper=upper)
        rows.append(row)
        metadata[case_id] = (tuple(stratum), record["gap_band"], record["family"],
                             exact(record["gap"]), exact(record["normalized_gap"]))
    rows.sort(key=lambda row: row["case_id"])
    counts = Counter(row["stratum"] for row in rows)
    gaps = Counter((row["stratum"], row["gap_band"]) for row in rows)
    if set(counts) != set(frozen.STRATA) or set(counts.values()) != {12} or set(gaps.values()) != {4} or len(gaps) != 24:
        raise ValueError("Require eight strata of 12 cases, four per gap band")
    # These unchanged functions validate all fixed weights and the betting grid.
    p_h = frozen.hoeffding_test(rows, outcome_range=(-amplitude, amplitude))["p_value"]
    p_b = frozen.betting_test(rows, outcome_range=(-amplitude, amplitude))["p_value"]
    raw = min(1., 2 * min(p_h, p_b))
    supplied = check_p(endpoint.get("inference", {}).get("p_value"))
    if supplied != raw:
        raise ValueError("Panel raw combined p-value disagrees with unchanged frozen computation")
    return {"rows": rows, "metadata": metadata, "p": supplied, "range": (-amplitude, amplitude)}


def read_panel(panel, off_id, low_id, luna_id, frozen):
    keys = (f"raw_pressure::{off_id}", f"raw_pressure::{low_id}", f"raw_pressure::{luna_id}",
            f"raw_reasoning_interaction::{low_id}-{off_id}")
    if len({off_id, low_id, luna_id}) != 3:
        raise ValueError("Panel requires three distinct configuration identifiers")
    if panel.get("confirmatory") is not True or panel.get("case_count") != 96 or panel.get("family_size") != 4:
        raise ValueError("Inputs must be frozen confirmatory 96-case Holm-4 panel analyses")
    primaries = panel.get("primaries", {})
    if set(primaries) != set(keys) or set(panel.get("primary_family", [])) != set(keys):
        raise ValueError("Panel primary family does not match its off/low/Luna configurations")
    endpoints = [endpoint_rows(primaries[key], 2 if index == 3 else 1, frozen) for index, key in enumerate(keys)]
    if any(endpoint["metadata"] != endpoints[0]["metadata"] for endpoint in endpoints):
        raise ValueError("Panel endpoints must use the same planned case bank")
    for off, low, interaction in zip(endpoints[0]["rows"], endpoints[1]["rows"], endpoints[3]["rows"]):
        if interaction["error_lower"] != low["error_lower"]-off["error_upper"] or interaction["error_upper"] != low["error_upper"]-off["error_lower"]:
            raise ValueError("Interaction bounds disagree with low-minus-off interval arithmetic")
    return endpoints


def unavailable_coreweave(template, terminal):
    """Logical full-support rows for the retired, never-queried main stage."""
    if not isinstance(terminal, dict) or terminal.get("schema_version") != 1 or terminal.get("protocol_version") != 6 \
            or terminal.get("collection_state") != "terminal" or terminal.get("all_active_calls_drained") is not True \
            or terminal.get("no_future_admissions") is not True:
        raise ValueError("CoreWeave must have an immutable drained terminal disposition")
    try:
        moment = datetime.datetime.fromisoformat(terminal["created_utc"])
        if moment.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError("CoreWeave terminal disposition needs an aware date") from None
    heldout = terminal.get("stages", {}).get("heldout", {})
    if heldout.get("status") != "not_started_terminal" or any(type(heldout.get(key)) is not int or heldout[key] != value
            for key, value in (("planned_paid_assignments", 1664), ("attempted", 0), ("never_reserved", 1664))):
        raise ValueError("Unavailable CoreWeave endpoints require zero main attempts and all 1664 cells unavailable")
    result = []
    for amplitude in (1, 1, 2):
        rows = []
        for original in template["rows"]:
            row = {key: original[key] for key in ("case_id", "stratum", "gap_band", "family", "gap", "normalized_gap")}
            row.update(error_lower=Fraction(-amplitude), error_upper=Fraction(amplitude),
                       complete=False, error_difference=None, observed_requests=0,
                       missing_requests=4 if amplitude == 1 else 8)
            rows.append(row)
        result.append({"rows": rows, "metadata": template["metadata"], "p": 1.,
                       "range": (-amplitude, amplitude), "unavailable": True})
    return result


def assemble(original_panel, baidu_panel, *, coreweave_terminal_metadata,
             old_off_id="ds_off", old_low_id="ds_low", new_off_id="ds_off_bd",
             new_low_id="ds_low_bd", luna_id="gpt6_luna_low"):
    frozen = load_frozen()
    old = read_panel(original_panel, old_off_id, old_low_id, luna_id, frozen)
    new = read_panel(baidu_panel, new_off_id, new_low_id, luna_id, frozen)
    if old[0]["metadata"] != new[0]["metadata"]:
        raise ValueError("Provider stages must retain the exact same 96-case bank")
    if old[2]["rows"] != new[2]["rows"] or old[2]["p"] != new[2]["p"]:
        raise ValueError("Luna case contrasts and raw p-value must be exactly identical in both panels")
    cw = unavailable_coreweave(old[0], coreweave_terminal_metadata)
    endpoints = (*old, *cw, new[0], new[1], new[3])
    decisions = holm10({name: endpoint["p"] for name, endpoint in zip(FAMILY, endpoints)})
    for name, endpoint in zip(FAMILY, endpoints):
        rows, outcome_range = endpoint["rows"], endpoint["range"]
        individual = frozen.combined_confidence_interval(rows, outcome_range=outcome_range, alpha=ALPHA)
        simultaneous = frozen.combined_confidence_interval(rows, outcome_range=outcome_range, alpha=ALPHA/10)
        decisions[name].update(case_count=96, logical_outcome_range=list(outcome_range),
                              confidence_interval_95=individual["interval"],
                              simultaneous_family_confidence_interval_95=simultaneous["interval"],
                              simultaneous_inversion=simultaneous,
                              endpoint_alpha=ALPHA/10, component_alpha=ALPHA/20,
                              observation_status="wholly_unavailable_planned_endpoint" if endpoint.get("unavailable") else "stage_specific_full_plan_inference")
        if endpoint.get("unavailable"):
            if endpoint["p"] != 1. or individual["interval"] != list(outcome_range) or simultaneous["interval"] != list(outcome_range):
                raise AssertionError("Unavailable stage must retain p=1 and full logical support")
            decisions[name].update(point_estimate=None, observed_main_requests=0,
                                   unavailable_reason="CoreWeave retired after failed operational smoke; no heldout calls")
    calibration = Path(__file__).with_name("holm10-reference-calibration.json")
    terminal_hash = hashlib.sha256(json.dumps(coreweave_terminal_metadata, sort_keys=True,
                                             ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return {"analysis_version": "h01-baidu-ten-endpoint-holm-v1",
            "role": "paper-level confirmatory family", "family_size": 10, "alpha": ALPHA,
            "primary_family": list(FAMILY), "primaries": decisions,
            "case_clusters_per_endpoint": 96, "case_bank_repeated_between_stages": True,
            "luna_endpoint_count": 1, "luna_exact_equality_verified": True,
            "original_panel_holm4_role": "original-protocol artifact; not an alternative paper claim rule",
            "new_panel_holm4_role": "native module intermediate; not a paper claim rule",
            "coreweave_role": "three prespecified unavailable endpoints retained as p=1; no native panel or results fabricated",
            "provider_interpretation": "dated provider/mode package; provider and collection stage/time confounded; no causal provider contrast or pooled estimand",
            "independence": "independent whole-case clusters across 96 cases; arbitrary within-case and test dependence; missingness bounds do not repair shared-provider dependence",
            "interval_basis": "unchanged frozen combined inversion: endpoint alpha/10 and component alpha/20; Bonferroni envelope, Holm10 decisions",
            "provenance": {"frozen_inference_sha256": SOURCE_SHA256,
                           "coreweave_terminal_metadata_canonical_sha256": terminal_hash,
                           "calibration_reference": calibration.name,
                           "calibration_sha256": hashlib.sha256(calibration.read_bytes()).hexdigest(),
                           "calibration_role": "outcome-free complete-data inactive-DI/CW p=1 reference, not actual-data forecast"}}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-panel", required=True, type=Path)
    parser.add_argument("--baidu-panel", required=True, type=Path)
    parser.add_argument("--coreweave-terminal-metadata", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    original = json.loads(args.original_panel.read_text(), object_pairs_hook=unique_object)
    new = json.loads(args.baidu_panel.read_text(), object_pairs_hook=unique_object)
    terminal = json.loads(args.coreweave_terminal_metadata.read_text(), object_pairs_hook=unique_object)
    result = assemble(original, new, coreweave_terminal_metadata=terminal)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output": str(args.output), "family_size": result["family_size"], "case_clusters_per_endpoint": 96}))


if __name__ == "__main__":
    main()
