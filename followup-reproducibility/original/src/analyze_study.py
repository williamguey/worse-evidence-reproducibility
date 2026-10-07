"""Deterministic, case-clustered analysis of the frozen independent H01 plan.

This module makes no network requests. It analyzes every planned request,
including unsent, failed, and invalid completions. Pilot statistics are
descriptive; held-out primary error contrasts use a centered studentized
bootstrap in the 24 generator strata and Holm across two hypotheses. Sign
flipping is a separate symmetry-dependent sensitivity analysis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping

from decision_engine import evaluate_case, fraction_string, parameter_tuple, rational
from generate_cases import blocked_parameter_set, case_strata, regret_stratum

PROJECT_ID = "H01-EVACQ-20261006"
BOOTSTRAP_RESAMPLES = 10000
SIGNFLIP_DRAWS = 100000
BOOTSTRAP_SEED = 2026100601
SIGNFLIP_SEED = 2026100602
ORDERS = ("AB", "BA")
REPRESENTATIONS = ("raw", "supplied")
TAGS = ("opt_english", "opt_chinese")
PREFERENCES = ("neutral", "moderate_optimal", "moderate_inferior", "strong_optimal", "strong_inferior")
STRATUM_KEYS = ("optimal_cost", "regret", "state1_prevalence", "optimal_report")
from itertools import product
TRUE_STRATA = tuple(product(("cheaper", "more_expensive"), ("low", "moderate", "high"),
                           ("rare", "common"), ("A", "B")))

# name, block, representation, plus tag/preference, minus tag/preference
CONTRASTS = (
    ("source_primary", "source", "supplied", "opt_chinese", "neutral", "opt_english", "neutral"),
    ("preference_primary", "preference", "raw", "none", "strong_inferior", "none", "neutral"),
    ("source_raw", "source", "raw", "opt_chinese", "neutral", "opt_english", "neutral"),
    ("preference_supplied_strong", "preference", "supplied", "none", "strong_inferior", "none", "neutral"),
    ("preference_raw_moderate", "preference", "raw", "none", "moderate_inferior", "none", "neutral"),
    ("preference_supplied_moderate", "preference", "supplied", "none", "moderate_inferior", "none", "neutral"),
    ("bridge_raw_moderate_source", "bridge", "raw", "opt_chinese", "moderate_inferior", "opt_english", "moderate_inferior"),
    ("preference_raw_strong_optimal", "preference", "raw", "none", "strong_optimal", "none", "neutral"),
    ("preference_supplied_strong_optimal", "preference", "supplied", "none", "strong_optimal", "none", "neutral"),
    ("preference_raw_moderate_optimal", "preference", "raw", "none", "moderate_optimal", "none", "neutral"),
    ("preference_supplied_moderate_optimal", "preference", "supplied", "none", "moderate_optimal", "none", "neutral"),
)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Fraction):
        return fraction_string(value)
    raise TypeError(type(value).__name__)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def request_body_sha256(body: Any) -> str:
    """Match api_client.sha: sorted JSON with default spaces and UTF-8 text.

    Decimal numbers read from stored JSON are converted to the Python float
    representation used by the dispatcher before it wrote the receipt.
    """
    serialized = json.dumps(body, sort_keys=True, ensure_ascii=False,
                            default=lambda value: float(value) if isinstance(value, Decimal) else _json_default(value))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _duplicate_check(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal,
                      object_pairs_hook=_duplicate_check)


def _stat(value: Fraction | None) -> dict[str, Any] | None:
    return None if value is None else {"exact": fraction_string(value), "value": float(value)}


def _mean(values: Iterable[Fraction]) -> Fraction | None:
    values = list(values)
    return sum(values, Fraction(0)) / len(values) if values else None


def _condition(task: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return tuple(task[key] for key in ("block", "representation", "tag_assignment", "preference"))


def _condition_name(condition: tuple[str, ...]) -> str:
    return "|".join(condition)


def substantive_design() -> set[tuple[Any, ...]]:
    cells = set()
    for representation in REPRESENTATIONS:
        for order in ORDERS:
            cells.update(("source", representation, tag, "neutral", order) for tag in TAGS)
            cells.update(("preference", representation, "none", preference, order) for preference in PREFERENCES)
    cells.update(("bridge", "raw", tag, "moderate_inferior", order) for tag in TAGS for order in ORDERS)
    return cells


def validate_plan(index: Mapping[str, Any], split: str, *, expected_project_id: str = PROJECT_ID,
                  expected_case_count: int | None = None,
                  expected_control_case_count: int | None = None,
                  expected_model_ids: Iterable[str] | None = None) -> dict[str, Any]:
    """Reject mixed projects, conflicting case IDs, duplicate cells or lost plan cells."""
    if split not in ("pilot", "heldout"):
        raise ValueError("Analysis split must be pilot or heldout")
    if not isinstance(index, Mapping) or not index:
        raise ValueError("Request index must be a nonempty request-ID mapping")
    metadata, panel, design = {}, {}, defaultdict(set)
    seen_cells = set()
    for request_id, record in sorted(index.items()):
        if not isinstance(request_id, str) or not request_id or Path(request_id).name != request_id:
            raise ValueError("Request IDs must be plain filenames without directory traversal")
        task, model, body = record["task"], record["model"], record["body"]
        if task["project_id"] != expected_project_id or task["split"] != split:
            raise ValueError("The analysis accepts only this new project and the requested split")
        model_id = model["model"]
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("A model must have an explicit nonempty ID")
        if body.get("model") != model_id:
            raise ValueError("Planned request model differs from the fixed model configuration")
        if model_id in panel and _canonical(panel[model_id]) != _canonical(model):
            raise ValueError(f"Model configuration changes within the plan: {model_id}")
        panel[model_id] = model
        if task["order"] not in ORDERS or task["expected"] not in ("A", "B"):
            raise ValueError("Order and expected answer must retain the A/B identifiers")
        if not isinstance(task["control"], bool) or (task["block"] == "control") != task["control"]:
            raise ValueError("Control flag and block disagree")
        prompt = task["prompt"]
        if not isinstance(prompt, str) or hashlib.sha256(prompt.encode("utf-8")).hexdigest() != task["prompt_sha256"]:
            raise ValueError("Planned prompt SHA-256 differs from its exact text")
        messages = body.get("messages", [])
        if not any(message.get("role") == "user" and message.get("content") == prompt for message in messages):
            raise ValueError("Planned request does not contain the exact planned user prompt")
        gap, normalized_gap = rational(task["gap"]), rational(task["normalized_gap"])
        if gap <= 0 or normalized_gap <= 0:
            raise ValueError("Every numerical case must have a positive exact regret gap")
        case_id = task["case_id"]
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("Cases must have nonempty unique identifiers")
        case_record = {"family": task["family"], "gap": fraction_string(gap),
                       "normalized_gap": fraction_string(normalized_gap),
                       "expected": task["expected"], "control": task["control"]}
        if case_id in metadata and metadata[case_id] != case_record:
            raise ValueError(f"Case ID is reused for different numerical cases or answer keys: {case_id}")
        metadata[case_id] = case_record
        local = (*_condition(task), task["order"])
        cell = (case_id, model_id, *local)
        if cell in seen_cells:
            raise ValueError(f"Duplicate planned case/model/condition/order cell: {cell}")
        seen_cells.add(cell)
        design[(case_id, model_id)].add(local)
    model_ids = tuple(sorted(panel))
    if len(model_ids) != 3:
        raise ValueError("The fixed study panel requires all three models")
    if expected_model_ids is not None and set(model_ids) != set(expected_model_ids):
        raise ValueError("Request index differs from the fixed explicit model panel")
    scientific_ids = tuple(sorted(case_id for case_id, case in metadata.items() if not case["control"]))
    control_ids = tuple(sorted(case_id for case_id, case in metadata.items() if case["control"]))
    if not scientific_ids or not control_ids:
        raise ValueError("Substantive cases and separate control cases must both be planned")
    if expected_case_count is not None and len(scientific_ids) != expected_case_count:
        raise ValueError("Substantive case count differs from the frozen protocol")
    if expected_control_case_count is not None and len(control_ids) != expected_control_case_count:
        raise ValueError("Control case count differs from the frozen protocol")
    families = Counter(metadata[case_id]["family"] for case_id in scientific_ids)
    if len(families) != 4:
        raise ValueError("All four simulator families must remain in the study")
    if len(set(families.values())) != 1:
        raise ValueError("The four simulator families must retain their frozen equal quotas")
    expected_control = {("control", "supplied", "none", "neutral", order) for order in ORDERS}
    for case_id, case in metadata.items():
        expected = expected_control if case["control"] else substantive_design()
        for model_id in model_ids:
            if design.get((case_id, model_id), set()) != expected:
                raise ValueError(f"The planned design is incomplete or changed for case/model {case_id}/{model_id}")
    return {"project_id": expected_project_id, "split": split, "models": panel,
            "model_ids": model_ids, "cases": metadata, "scientific_case_ids": scientific_ids,
            "control_case_ids": control_ids, "family_counts": dict(sorted(families.items())),
            "substantive_cells_per_case_per_model": 32,
            "planned_substantive_requests": len(scientific_ids) * 32 * 3,
            "planned_control_requests": len(control_ids) * 2 * 3}


def validate_case_manifest(cases: Any, plan: dict[str, Any]) -> None:
    """Verify numeric identity and the actual generator quotas before analysis."""
    if isinstance(cases, Mapping) and "cases" in cases:
        cases = cases["cases"]
    if isinstance(cases, Mapping):
        records = list(cases.values())
    elif isinstance(cases, list):
        records = cases
    else:
        raise ValueError("cases.json must contain full generated case records")
    scientific_ids = set(plan["scientific_case_ids"])
    seen_ids, seen_tuples, strata_counts = set(), set(), Counter()
    blacklist = blocked_parameter_set()
    for case in records:
        case_id = case["case_id"]
        if case_id in seen_ids:
            raise ValueError(f"Duplicate case ID in cases.json: {case_id}")
        seen_ids.add(case_id)
        if case_id in plan["control_case_ids"]:
            continue
        if case_id not in scientific_ids:
            raise ValueError("Case manifest contains an unplanned or foreign scientific case")
        if case.get("project_id", plan["project_id"]) != plan["project_id"] or case["generation"].get("split", plan["split"]) != plan["split"]:
            raise ValueError("Case manifest belongs to a different project or split")
        signature = parameter_tuple(case)
        if signature in seen_tuples or signature in blacklist:
            raise ValueError("Numerical case tuple is duplicated or reuses a discovery case")
        seen_tuples.add(signature)
        truth = evaluate_case(case)
        derived = case_strata(case, truth)
        declared = case["generation"]["strata"]
        stratum = tuple(declared[key] for key in STRATUM_KEYS)
        if stratum not in TRUE_STRATA or any(derived[key] != declared[key] for key in STRATUM_KEYS):
            raise ValueError("Generator stratum differs from its actual numerical case")
        planned = plan["cases"][case_id]
        if (case["family"] != planned["family"] or truth["optimal_report"] != planned["expected"]
                or truth["regret_of_wrong_report"] != rational(planned["gap"])
                or truth["normalized_regret"] != rational(planned["normalized_gap"])):
            raise ValueError("Planned family, answer key or regret gap differs from cases.json")
        planned["stratum"] = stratum
        strata_counts[stratum] += 1
    if scientific_ids != seen_ids & scientific_ids:
        raise ValueError("Case manifest omits a planned scientific case")
    if set(strata_counts) != set(TRUE_STRATA) or len(set(strata_counts.values())) != 1:
        raise ValueError("The 24 generation strata must all be present with equal planned counts")
    plan["generator_stratum_keys"] = list(STRATUM_KEYS)
    plan["generator_stratum_counts"] = {"|".join(stratum): strata_counts[stratum] for stratum in TRUE_STRATA}


def parse_completion(raw: Any, model_id: str) -> tuple[str | None, str]:
    """Accept exactly one stopped completion containing only {'choice': A/B}."""
    if not isinstance(raw, Mapping):
        return None, "malformed_raw_response"
    if raw.get("error"):
        return None, "provider_error"
    if raw.get("model") != model_id:
        return None, "model_mismatch"
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        return None, "completion_count_invalid"
    completion = choices[0]
    if not isinstance(completion, Mapping) or completion.get("finish_reason") != "stop":
        return None, "finish_reason_not_stop"
    message = completion.get("message")
    if not isinstance(message, Mapping) or message.get("refusal") or message.get("tool_calls"):
        return None, "refusal_or_unexpected_tool_call"
    content = message.get("content")
    if not isinstance(content, str):
        return None, "content_not_string"
    try:
        output = json.loads(content, object_pairs_hook=_duplicate_check)
    except (ValueError, TypeError):
        return None, "output_not_strict_json"
    if not isinstance(output, dict) or set(output) != {"choice"} or output["choice"] not in ("A", "B"):
        return None, "choice_schema_invalid"
    return output["choice"], "valid"


def _money(value: Any) -> Fraction | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        return None
    return result if result >= 0 else None


def score_request(request_id: str, record: Mapping[str, Any], *, raw: Any = None,
                  failure: Any = None, saved_request: Any = None,
                  raw_exists: bool = False, failure_exists: bool = False,
                  request_exists: bool = False, raw_read_error: str | None = None,
                  request_read_error: str | None = None) -> dict[str, Any]:
    task, model = record["task"], record["model"]["model"]
    provenance = "not_saved"
    receipt_hash_status = "not_saved"
    if request_read_error:
        provenance = "unreadable_saved_request"
    elif request_exists:
        saved_body = saved_request
        if isinstance(saved_request, Mapping):
            saved_body = saved_request.get("body", saved_request.get("request", saved_request))
        provenance = "matches_plan" if _canonical(saved_body) == _canonical(record["body"]) else "request_differs_from_plan"
        supplied_hash = saved_request.get("sha256") if isinstance(saved_request, Mapping) else None
        receipt_hash_status = "matches_saved_body" if supplied_hash == request_body_sha256(saved_body) else "missing_hash" if supplied_hash is None else "hash_mismatch"
        if receipt_hash_status != "matches_saved_body":
            provenance = "request_hash_missing" if supplied_hash is None else "request_hash_mismatch"
        elif saved_request.get("call_id") != request_id:
            provenance = "request_receipt_id_mismatch"
    if raw_read_error:
        choice, status = None, "malformed_raw_response"
    elif raw_exists:
        choice, status = parse_completion(raw, model)
    elif failure_exists:
        choice, status = None, "failed_request"
    else:
        choice, status = None, "missing_output"
    if provenance in ("unreadable_saved_request", "request_differs_from_plan", "request_hash_missing",
                      "request_hash_mismatch", "request_receipt_id_mismatch") and raw_exists:
        choice, status = None, provenance
    valid = choice is not None
    error = choice != task["expected"] if valid else None
    usage = raw.get("usage", {}) if isinstance(raw, Mapping) else {}
    if not isinstance(usage, Mapping):
        usage = {}
    charge = _money(usage.get("cost"))
    gap, normalized_gap = rational(task["gap"]), rational(task["normalized_gap"])
    completion = raw.get("choices", [{}])[0] if isinstance(raw, Mapping) and isinstance(raw.get("choices"), list) and raw["choices"] else {}
    return {"request_id": request_id, "case_id": task["case_id"], "family": task["family"],
            "model": model, "condition": list(_condition(task)), "order": task["order"],
            "control": task["control"], "expected": task["expected"], "gap": fraction_string(gap),
            "normalized_gap": fraction_string(normalized_gap), "prompt_sha256": task["prompt_sha256"],
            "valid": valid, "choice": choice, "error": error,
            "regret": fraction_string(gap * int(error)) if valid else None,
            "normalized_regret": fraction_string(normalized_gap * int(error)) if valid else None,
            "status": status, "raw_present": raw_exists, "failure_present": failure_exists,
            "saved_request_present": request_exists, "request_provenance": provenance,
            "request_receipt_hash_status": receipt_hash_status,
            "planned_request_body_sha256": request_body_sha256(record["body"]),
            "attempt_evidence_present": raw_exists or failure_exists or request_exists,
            "reported_model": raw.get("model") if isinstance(raw, Mapping) else None,
            "finish_reason": completion.get("finish_reason") if isinstance(completion, Mapping) else None,
            "raw_usage": json.loads(_canonical(usage)),
            "raw_usage_charge_usd": fraction_string(charge) if charge is not None else None,
            "raw_read_error": raw_read_error, "request_read_error": request_read_error}


def load_cells(index: Mapping[str, Any], raw_dir: Path) -> list[dict[str, Any]]:
    cells = []
    for request_id, record in sorted(index.items()):
        loaded, errors, present = {}, {}, {}
        for name, suffix in (("request", ".request.json"), ("raw", ".json"), ("failure", ".failure.json")):
            path = raw_dir / (request_id + suffix)
            present[name] = path.is_file()
            if present[name]:
                try:
                    loaded[name] = read_json(path)
                except (ValueError, OSError, UnicodeError) as error:
                    errors[name] = f"{type(error).__name__}: {error}"
        cell = score_request(request_id, record, raw=loaded.get("raw"), failure=loaded.get("failure"),
                             saved_request=loaded.get("request"), raw_exists=present["raw"],
                             failure_exists=present["failure"], request_exists=present["request"],
                             raw_read_error=errors.get("raw"), request_read_error=errors.get("request"))
        cell["raw_path"] = str(raw_dir / (request_id + ".json"))
        cells.append(cell)
    return cells


def _counts(cells: list[Mapping[str, Any]]) -> dict[str, Any]:
    n, valid = len(cells), sum(cell["valid"] for cell in cells)
    errors = sum(int(cell["error"]) for cell in cells if cell["valid"])
    charge_values = [rational(cell["raw_usage_charge_usd"]) for cell in cells if cell["raw_usage_charge_usd"] is not None]
    regret_sum = sum((rational(cell["regret"]) for cell in cells if cell["valid"]), Fraction(0))
    missing_gap = sum((rational(cell["gap"]) for cell in cells if not cell["valid"]), Fraction(0))
    return {"planned": n, "valid": valid, "missing_or_invalid": n - valid,
            "validity_rate": _stat(Fraction(valid, n) if n else None),
            "observed_errors": errors, "observed_correct_valid": valid - errors,
            "observed_error_rate_valid_denominator": _stat(Fraction(errors, valid) if valid else None),
            "error_rate_fixed_plan_bounds": {"lower": _stat(Fraction(errors, n) if n else None),
                                             "upper": _stat(Fraction(errors + n - valid, n) if n else None)},
            "mean_regret_fixed_plan_bounds": {"lower": _stat(regret_sum / n if n else None),
                                              "upper": _stat((regret_sum + missing_gap) / n if n else None)},
            "statuses": dict(sorted(Counter(cell["status"] for cell in cells).items())),
            "raw_outputs": sum(cell["raw_present"] for cell in cells),
            "raw_usage_charges": {"reported_charge_count": len(charge_values),
                                  "total_reported_usd": _stat(sum(charge_values, Fraction(0))),
                                  "attempts_without_reported_charge": sum(cell["attempt_evidence_present"] and cell["raw_usage_charge_usd"] is None for cell in cells)},
            "token_usage": {key: sum(_token_count(cell["raw_usage"].get(key)) for cell in cells)
                            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}}


def _token_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        tokens = Fraction(str(value))
        return int(tokens) if tokens.denominator == 1 and tokens >= 0 else 0
    except (ValueError, ZeroDivisionError):
        return 0


def condition_counts(cells: list[Mapping[str, Any]]) -> dict[str, Any]:
    groups = defaultdict(list)
    for cell in cells:
        groups[(_condition_name(tuple(cell["condition"])), cell["model"])].append(cell)
    output = {}
    for (condition, model), group in sorted(groups.items()):
        output.setdefault(condition, {})[model] = _counts(group)
    return output


def case_contrasts(cells: list[Mapping[str, Any]], plan: Mapping[str, Any], contrast: tuple[str, ...],
                   *, model_ids: Iterable[str] | None = None,
                   orders: Iterable[str] = ORDERS,
                   case_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    _, block, representation, plus_tag, plus_preference, minus_tag, minus_preference = contrast
    plus_condition = (block, representation, plus_tag, plus_preference)
    minus_condition = (block, representation, minus_tag, minus_preference)
    models = tuple(plan["model_ids"] if model_ids is None else model_ids)
    selected_orders = tuple(orders)
    selected_cases = tuple(plan["scientific_case_ids"] if case_ids is None else case_ids)
    lookup = {(cell["case_id"], cell["model"], tuple(cell["condition"]), cell["order"]): cell
              for cell in cells if not cell["control"]}
    output = []
    for case_id in selected_cases:
        meta = plan["cases"][case_id]
        differences = []
        lower, upper = Fraction(0), Fraction(0)
        missing_plus = missing_minus = observed_plus = observed_minus = 0
        pair_rows = []
        for model in models:
            for order in selected_orders:
                plus = lookup[(case_id, model, plus_condition, order)]
                minus = lookup[(case_id, model, minus_condition, order)]
                plus_error = Fraction(int(plus["error"])) if plus["valid"] else None
                minus_error = Fraction(int(minus["error"])) if minus["valid"] else None
                missing_plus += plus_error is None
                missing_minus += minus_error is None
                observed_plus += plus_error or 0
                observed_minus += minus_error or 0
                pair_lower = (plus_error if plus_error is not None else 0) - (minus_error if minus_error is not None else 1)
                pair_upper = (plus_error if plus_error is not None else 1) - (minus_error if minus_error is not None else 0)
                lower += pair_lower
                upper += pair_upper
                difference = plus_error - minus_error if plus_error is not None and minus_error is not None else None
                if difference is not None:
                    differences.append(difference)
                pair_rows.append({"model": model, "order": order, "plus_request_id": plus["request_id"],
                                  "minus_request_id": minus["request_id"], "complete": difference is not None,
                                  "error_difference": fraction_string(difference) if difference is not None else None})
        pair_count = len(models) * len(selected_orders)
        complete = len(differences) == pair_count
        error_difference = _mean(differences) if complete else None
        gap = rational(meta["gap"])
        output.append({"case_id": case_id, "family": meta["family"], "gap": gap,
                       "stratum": meta["stratum"],
                       "margin_stratum": regret_stratum(meta["normalized_gap"]),
                       "complete": complete, "planned_pairs": pair_count,
                       "complete_pairs": len(differences), "pairs": pair_rows,
                       "any_discordant_matched_pair": any(difference != 0 for difference in differences),
                       "error_difference": error_difference,
                       "regret_difference": gap * error_difference if complete else None,
                       "available_pair_error_sum": sum(differences, Fraction(0)),
                       "error_lower": lower / pair_count, "error_upper": upper / pair_count,
                       "regret_lower": gap * lower / pair_count, "regret_upper": gap * upper / pair_count,
                       "missing_plus": missing_plus, "missing_minus": missing_minus,
                       "observed_errors_plus": int(observed_plus), "observed_errors_minus": int(observed_minus)})
    return output


def _stratum_statistics(rows: list[Mapping[str, Any]], metric: str = "error_difference") -> dict[str, Any]:
    groups = defaultdict(list)
    for row in rows:
        if row["complete"]:
            groups[tuple(row["stratum"])].append(row[metric])
    counts = {"|".join(stratum): len(groups[stratum]) for stratum in TRUE_STRATA}
    empty = ["|".join(stratum) for stratum in TRUE_STRATA if not groups[stratum]]
    if empty:
        return {"mean": None, "variance": None, "complete_counts": counts, "empty_strata": empty,
                "variance_unavailable_reason": "empty_generator_stratum"}
    mean = sum((_mean(groups[stratum]) for stratum in TRUE_STRATA), Fraction(0)) / 24
    insufficient = ["|".join(stratum) for stratum in TRUE_STRATA if len(groups[stratum]) < 2]
    if insufficient:
        variance, reason = None, "fewer_than_two_complete_cases_in_a_generator_stratum"
    else:
        variance = Fraction(0)
        for stratum in TRUE_STRATA:
            values = groups[stratum]
            within_mean = _mean(values)
            sample_variance = sum(((value - within_mean) ** 2 for value in values), Fraction(0)) / (len(values) - 1)
            variance += Fraction(1, 24) ** 2 * sample_variance / len(values)
        reason = None
    return {"mean": mean, "variance": variance, "complete_counts": counts, "empty_strata": [],
            "variance_unavailable_reason": reason}


def summarize_contrast(rows: list[Mapping[str, Any]], *, stratum_weighted: bool = False) -> dict[str, Any]:
    complete = [row for row in rows if row["complete"]]
    mean_error = _mean(row["error_difference"] for row in complete)
    mean_regret = _mean(row["regret_difference"] for row in complete)
    stratum_stats = _stratum_statistics(rows) if stratum_weighted else None
    stratum_regret = _stratum_statistics(rows, "regret_difference") if stratum_weighted else None
    planned_pairs = sum(row["planned_pairs"] for row in rows)
    complete_pairs = sum(row["complete_pairs"] for row in rows)
    plus_missing, minus_missing = sum(row["missing_plus"] for row in rows), sum(row["missing_minus"] for row in rows)
    return {"planned_cases": len(rows), "complete_cases": len(complete),
            "planned_pairs": planned_pairs, "complete_pairs": complete_pairs,
            "complete_case_mean_error_difference": _stat(stratum_stats["mean"] if stratum_weighted else mean_error),
            "complete_case_mean_regret_difference": _stat(stratum_regret["mean"] if stratum_weighted else mean_regret),
            "available_complete_case_unweighted_mean_error_difference": _stat(mean_error),
            "available_complete_case_unweighted_mean_regret_difference": _stat(mean_regret),
            "point_estimator": "equal 1/24 weights over generator strata; complete cases equally weighted within each stratum" if stratum_weighted else "descriptive equal available complete-case weights",
            "generator_stratum_complete_counts": stratum_stats["complete_counts"] if stratum_weighted else None,
            "empty_generator_strata": stratum_stats["empty_strata"] if stratum_weighted else None,
            "available_pair_mean_error_difference": _stat(sum((row["available_pair_error_sum"] for row in rows), Fraction(0)) / complete_pairs if complete_pairs else None),
            "fixed_plan_error_bounds": {"lower": _stat(_mean(row["error_lower"] for row in rows)),
                                        "upper": _stat(_mean(row["error_upper"] for row in rows))},
            "fixed_plan_regret_bounds": {"lower": _stat(_mean(row["regret_lower"] for row in rows)),
                                         "upper": _stat(_mean(row["regret_upper"] for row in rows))},
            "missingness": {"plus": plus_missing, "minus": minus_missing,
                            "plus_fraction": _stat(Fraction(plus_missing, planned_pairs) if planned_pairs else None),
                            "minus_fraction": _stat(Fraction(minus_missing, planned_pairs) if planned_pairs else None),
                            "difference_plus_minus": _stat(Fraction(plus_missing - minus_missing, planned_pairs) if planned_pairs else None),
                            "absolute_imbalance_le_one_percentage_point": abs(Fraction(plus_missing - minus_missing, planned_pairs)) <= Fraction(1, 100) if planned_pairs else False},
            "harmful_complete_case_increments": sum(row["error_difference"] > 0 for row in complete),
            "case_discordance_floor_summary": case_discordance_floor(rows) if stratum_weighted else None,
            "case_records": [{key: fraction_string(value) if isinstance(value, Fraction) else value for key, value in row.items()}
                             for row in rows]}


def case_discordance_floor(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Zero-event bound on average independent case-level discordance risk.

    Case probabilities need not be identical. With equal planned counts in
    all generator strata, AM-GM bounds the probability of zero independent
    events by (1-average probability)^N. Missing primary pairs disable it.
    """
    n = len(rows)
    any_discordant = sum(row["any_discordant_matched_pair"] for row in rows)
    complete_cohort = bool(rows) and all(row["complete"] for row in rows)
    strata = Counter(tuple(row["stratum"]) for row in rows)
    equal_strata = set(strata) == set(TRUE_STRATA) and len(set(strata.values())) == 1
    full_panel = all(row["planned_pairs"] == 6 for row in rows)
    eligible = complete_cohort and equal_strata and full_panel and any_discordant == 0
    upper = 1 - 0.05 ** (1 / n) if eligible else None
    return {"planned_cases": n, "cases_with_any_observed_discordant_matched_pair": any_discordant,
            "all_fixed_model_order_pairs_observed": complete_cohort,
            "zero_event_bound_available": eligible,
            "average_case_discordance_probability_upper_95_percent": upper,
            "formula": "1 - 0.05**(1/N)" if eligible else None,
            "justification": "Model-based under the independent generated-case assumption and equal stratum counts: a zero-event average-probability bound via AM-GM, without identical case-probability or binomial-iid assumptions." if eligible else None,
            "interpretation": "A case-level discordance bound, not equality, per-response equivalence, or an effect-size confidence interval."}


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    position = probability * (len(values) - 1)
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def stratified_bootstrap(rows: list[Mapping[str, Any]], *, resamples: int = BOOTSTRAP_RESAMPLES,
                         seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Centered studentized case bootstrap within the true 24 generator strata.

    Entire planned cases are resampled, including their missingness masks.
    Undefined replicate statistics count conservatively as exceedances; they
    are retained in the Monte Carlo denominator and explicitly disclosed.
    """
    from math import sqrt
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row["stratum"])].append((float(row["error_difference"]) if row["complete"] else None,
                                             float(row["regret_difference"]) if row["complete"] else None))
    observed = _stratum_statistics(rows)
    observed_mean, observed_variance = observed["mean"], observed["variance"]
    test_reason = observed["variance_unavailable_reason"]
    if observed_variance == 0 and observed_mean != 0:
        test_reason = "nonzero_mean_with_zero_within_stratum_variance_no_calibrated_mean_test"
    zero_mean_and_variance = observed_mean == 0 and observed_variance == 0
    observed_floor = zero_mean_and_variance and all(row["error_difference"] == 0 for row in rows if row["complete"])
    observed_t = float(observed_mean) / sqrt(float(observed_variance)) if observed_variance is not None and observed_variance > 0 else None
    rng = random.Random(seed)
    error_samples, regret_samples = [], []
    empty = unavailable_studentized = exceedances = 0
    for _ in range(resamples):
        error_total = regret_total = variance = 0.0
        empty_stratum = insufficient_variance = False
        for stratum in TRUE_STRATA:
            group = groups[stratum]
            sampled = [group[rng.randrange(len(group))] for _ in range(len(group))]
            available = [value for value in sampled if value[0] is not None]
            if not available:
                empty_stratum = True
                continue
            mean_error = sum(value[0] for value in available) / len(available)
            error_total += mean_error / 24
            regret_total += sum(value[1] for value in available) / len(available) / 24
            if len(available) < 2:
                insufficient_variance = True
            else:
                variance += sum((value[0] - mean_error) ** 2 for value in available) / (len(available) - 1) / len(available) / (24 ** 2)
        if empty_stratum:
            empty += 1
        else:
            error_samples.append(error_total)
            regret_samples.append(regret_total)
        if empty_stratum or insufficient_variance or variance == 0:
            unavailable_studentized += 1
            exceedances += 1
        elif observed_t is not None:
            centered = error_total - float(observed_mean)
            bootstrap_t = abs(centered) / sqrt(variance)
            exceedances += bootstrap_t >= abs(observed_t) - 1e-12
    error_samples.sort()
    regret_samples.sort()
    p = Fraction(1) if zero_mean_and_variance else None if test_reason else Fraction(exceedances + 1, resamples + 1)
    return {"method": "centered studentized case bootstrap stratified by the 24 generator strata",
            "resamples": resamples, "seed": seed, "confidence_level": 0.95,
            "stratum_sample_sizes": {"|".join(stratum): len(groups[stratum]) for stratum in TRUE_STRATA},
            "stratum_complete_cases": observed["complete_counts"], "empty_observed_strata": observed["empty_strata"],
            "observed_weighted_error_mean": _stat(observed_mean), "observed_mean_variance": _stat(observed_variance),
            "observed_studentized_statistic": observed_t,
            "p_value": _stat(p), "formal_mean_test_unavailable_reason": test_reason,
            "formal_mean_inference_available": p is not None,
            "calibration": "Approximate centered studentized bootstrap calibration",
            "monte_carlo_correction": "(exceedances+1)/(resamples+1)",
            "undefined_replicate_convention": "count as exceedance; retain in fixed resample denominator",
            "missingness_masks_preserved": True, "replicates_with_empty_stratum": empty,
            "replicates_with_unavailable_studentized_statistic": unavailable_studentized,
            "exceedances_including_unavailable_replicates": exceedances,
            "error_difference_interval": [_percentile(error_samples, 0.025), _percentile(error_samples, 0.975)],
            "regret_difference_interval": [_percentile(regret_samples, 0.025), _percentile(regret_samples, 0.975)],
            "interval_method": "percentiles of estimable stratum-weighted case bootstrap means",
            "percentile_intervals_descriptive_when_primary_test_unavailable": p is None,
            "observed_all_zero_floor": observed_floor,
            "zero_observed_mean_and_variance": zero_mean_and_variance,
            "floor_interpretation": "An all-zero interval describes the observed floor; it is not an equivalence bound." if observed_floor else None}


def signflip_test(rows: list[Mapping[str, Any]], *, draws: int = SIGNFLIP_DRAWS,
                  seed: int = SIGNFLIP_SEED) -> dict[str, Any]:
    """Two-sided exact-integer Monte Carlo signs under a symmetric-difference null."""
    groups = defaultdict(list)
    for row in rows:
        if row["complete"]:
            groups[tuple(row["stratum"])].append(row["error_difference"])
    values = [value / 24 / len(groups[stratum]) for stratum in TRUE_STRATA for value in groups[stratum]]
    empty_stratum = any(not groups[stratum] for stratum in TRUE_STRATA)
    if empty_stratum:
        values = []
    if not values:
        return {"p_value": None, "complete_cases": sum(row["complete"] for row in rows), "draws": draws, "seed": seed,
                "unavailable_reason": "empty_generator_stratum" if empty_stratum else "no_complete_cases",
                "null": "symmetric independent case-level paired differences", "treatment_randomization_test": False}
    denominator = 1
    from math import lcm
    for value in values:
        denominator = lcm(denominator, value.denominator)
    scaled = [int(value * denominator) for value in values if value]
    observed = abs(sum(scaled))
    rng = random.Random(seed)
    exceedances = 0
    for _ in range(draws):
        signs = rng.getrandbits(len(scaled))
        permuted = sum(value if (signs >> index) & 1 else -value for index, value in enumerate(scaled))
        exceedances += abs(permuted) >= observed
    p = Fraction(exceedances + 1, draws + 1)
    return {"p_value": _stat(p), "complete_cases": len(values), "nonzero_cases": len(scaled),
            "draws": draws, "seed": seed, "absolute_integer_sum_observed": observed,
            "integer_scale_denominator": denominator, "exceedances": exceedances,
            "monte_carlo_correction": "(exceedances+1)/(draws+1)",
            "null": "symmetric independent case-level paired differences", "treatment_randomization_test": False}


def holm_two(p_values: Mapping[str, Fraction | None]) -> dict[str, Any]:
    if len(p_values) != 2:
        raise ValueError("The frozen Holm family contains exactly two pooled primaries")
    p_values = {name: Fraction(1) if value is None else value for name, value in p_values.items()}
    ordered = sorted(p_values, key=lambda name: (p_values[name], name))
    first = min(Fraction(1), 2 * p_values[ordered[0]])
    second = max(first, p_values[ordered[1]])
    return {ordered[0]: _stat(first), ordered[1]: _stat(second)}


def pilot_gate(cells: list[Mapping[str, Any]], plan: Mapping[str, Any], primaries: Mapping[str, Any],
               *, materials_verified: bool, charges_verified: bool) -> dict[str, Any]:
    valid_checks, control_checks = {}, {}
    for model in plan["model_ids"]:
        scientific = [cell for cell in cells if cell["model"] == model and not cell["control"]]
        controls = [cell for cell in cells if cell["model"] == model and cell["control"]]
        valid_rate = Fraction(sum(cell["valid"] for cell in scientific), len(scientific))
        correct_rate = Fraction(sum(cell["valid"] and not cell["error"] for cell in controls), len(controls))
        valid_checks[model] = {"rate": _stat(valid_rate), "passes": valid_rate >= Fraction(99, 100)}
        control_checks[model] = {"correct_valid_over_all_planned_controls": _stat(correct_rate),
                                 "passes": correct_rate >= Fraction(99, 100)}
    imbalance_checks = {name: primary["pooled"]["missingness"]["absolute_imbalance_le_one_percentage_point"]
                        for name, primary in primaries.items()}
    source_models = {"positive": [], "negative": []}
    source_details, pressure_details = {}, {}
    for model in plan["model_ids"]:
        source = primaries["source_primary"]["per_model"][model]
        mean_stat = source["complete_case_mean_error_difference"]
        mean = rational(mean_stat["exact"]) if mean_stat is not None else None
        bounds = source["fixed_plan_error_bounds"]
        lower, upper = rational(bounds["lower"]["exact"]), rational(bounds["upper"]["exact"])
        direction = "positive" if mean is not None and mean >= Fraction(1, 20) and lower > 0 else "negative" if mean is not None and mean <= -Fraction(1, 20) and upper < 0 else None
        if direction:
            source_models[direction].append(model)
        source_details[model] = {"absolute_mean_at_least_5pp": mean is not None and abs(mean) >= Fraction(1, 20),
                                 "fixed_plan_bounds_preserve_mean_direction": mean is not None and ((mean > 0 and lower > 0) or (mean < 0 and upper < 0)),
                                 "qualifying_direction": direction}
        pressure = primaries["preference_primary"]["per_model"][model]
        pressure_stat = pressure["complete_case_mean_error_difference"]
        pressure_mean = rational(pressure_stat["exact"]) if pressure_stat is not None else None
        harmful = pressure["harmful_complete_case_increments"]
        pressure_lower = rational(pressure["fixed_plan_error_bounds"]["lower"]["exact"])
        pressure_details[model] = {"mean_at_least_10pp": pressure_mean is not None and pressure_mean >= Fraction(1, 10),
                                   "harmful_case_increments": harmful, "at_least_four_harmful_cases": harmful >= 4,
                                   "fixed_plan_lower_bound_positive": pressure_lower > 0,
                                   "qualifies": pressure_mean is not None and pressure_mean >= Fraction(1, 10) and harmful >= 4 and pressure_lower > 0}
    source_pass = any(len(models) >= 2 for models in source_models.values())
    pressure_pass = any(details["qualifies"] for details in pressure_details.values())
    operational = (materials_verified and charges_verified
                   and all(check["passes"] for check in valid_checks.values())
                   and all(check["passes"] for check in control_checks.values())
                   and all(imbalance_checks.values()))
    return {"passes": operational and (source_pass or pressure_pass),
            "operational_requirements_pass": operational,
            "verified_materials": materials_verified, "verified_charges": charges_verified,
            "validity_by_model": valid_checks, "controls_by_model": control_checks,
            "primary_missingness_imbalance_checks": imbalance_checks,
            "source_path": {"passes": source_pass, "coherent_models_by_direction": source_models, "model_checks": source_details},
            "preference_path": {"passes": pressure_pass, "model_checks": pressure_details},
            "heldout_panel_if_passed": list(plan["model_ids"]),
            "heldout_primaries_if_passed": ["source_primary", "preference_primary"],
            "interpretation": "Development expansion thresholds; no pilot significance or power claim."}


def analyze_cells(index: Mapping[str, Any], cells: list[Mapping[str, Any]], split: str, *,
                  case_manifest: Any,
                  materials_verified: bool = False, charges_verified: bool = False,
                  expected_project_id: str = PROJECT_ID, expected_case_count: int | None = None,
                  expected_control_case_count: int | None = None, expected_model_ids: Iterable[str] | None = None,
                  bootstrap_resamples: int = BOOTSTRAP_RESAMPLES,
                  signflip_draws: int = SIGNFLIP_DRAWS) -> dict[str, Any]:
    plan = validate_plan(index, split, expected_project_id=expected_project_id,
                         expected_case_count=expected_case_count,
                         expected_control_case_count=expected_control_case_count,
                         expected_model_ids=expected_model_ids)
    validate_case_manifest(case_manifest, plan)
    if len(cells) != len(index) or len({cell["request_id"] for cell in cells}) != len(cells) or {cell["request_id"] for cell in cells} != set(index):
        raise ValueError("Scored records must preserve exactly every planned request ID")
    cells = sorted(cells, key=lambda cell: cell["request_id"])
    primaries, secondary = {}, {}
    for offset, contrast in enumerate(CONTRASTS):
        name = contrast[0]
        rows = case_contrasts(cells, plan, contrast)
        summary = {"contrast": {"block": contrast[1], "representation": contrast[2],
                                 "plus": {"tag_assignment": contrast[3], "preference": contrast[4]},
                                 "minus": {"tag_assignment": contrast[5], "preference": contrast[6]}},
                   "pooled": summarize_contrast(rows, stratum_weighted=offset < 2),
                   "per_model": {model: summarize_contrast(case_contrasts(cells, plan, contrast, model_ids=(model,)))
                                 for model in plan["model_ids"]},
                   "per_order": {order: summarize_contrast(case_contrasts(cells, plan, contrast, orders=(order,))) for order in ORDERS},
                   "per_margin_stratum": {stratum: summarize_contrast([row for row in rows if row["margin_stratum"] == stratum])
                                           for stratum in ("low", "moderate", "high")},
                   "per_family": {family: summarize_contrast([row for row in rows if row["family"] == family])
                                  for family in sorted(plan["family_counts"])}}
        if offset < 2:
            summary["pooled"]["bootstrap"] = stratified_bootstrap(rows, resamples=bootstrap_resamples, seed=BOOTSTRAP_SEED) if split == "heldout" else None
            summary["pooled"]["signflip_symmetry_sensitivity"] = signflip_test(rows, draws=signflip_draws, seed=SIGNFLIP_SEED + offset) if split == "heldout" else None
            primaries[name] = summary
        else:
            secondary[name] = summary
    if split == "heldout":
        adjusted = holm_two({name: rational(summary["pooled"]["bootstrap"]["p_value"]["exact"])
                             if summary["pooled"]["bootstrap"]["p_value"] is not None else None
                             for name, summary in primaries.items()})
        for name, value in adjusted.items():
            primaries[name]["pooled"]["holm_adjusted_p_value"] = value
            primaries[name]["pooled"]["holm_unavailable_input_treated_as_one"] = primaries[name]["pooled"]["bootstrap"]["p_value"] is None
    else:
        for summary in primaries.values():
            summary["pooled"]["holm_adjusted_p_value"] = None
    request_provenance_verified = all(cell["request_provenance"] == "matches_plan" for cell in cells if cell["raw_present"])
    material_flag = materials_verified and request_provenance_verified
    return {"analysis_version": "h01-independent-analysis-v3-conservative-zero-variance", "project_id": plan["project_id"], "split": split,
            "deterministic_settings": {"bootstrap_resamples": bootstrap_resamples, "bootstrap_seed": BOOTSTRAP_SEED,
                                       "signflip_draws": signflip_draws, "source_signflip_seed": SIGNFLIP_SEED,
                                       "preference_signflip_seed": SIGNFLIP_SEED + 1},
            "plan": {key: value for key, value in plan.items() if key != "cases"},
            "outcome_accounting": _counts(cells),
            "substantive_outcome_accounting": _counts([cell for cell in cells if not cell["control"]]),
            "control_outcome_accounting": _counts([cell for cell in cells if cell["control"]]),
            "counts_by_condition_and_model": condition_counts(cells),
            "counts_by_model": {model: _counts([cell for cell in cells if cell["model"] == model]) for model in plan["model_ids"]},
            "primaries": primaries, "descriptive_secondary": secondary,
            "pilot_gate": pilot_gate(cells, plan, primaries, materials_verified=material_flag, charges_verified=charges_verified) if split == "pilot" else None,
            "provenance_audit": {"caller_materials_verified": materials_verified,
                                  "completed_raw_request_artifacts_match_plan": request_provenance_verified,
                                  "caller_charges_verified": charges_verified},
            "cells": cells}


def analyze_study(study_root: Path, split: str, *, materials_verified: bool = False,
                  charges_verified: bool = False) -> dict[str, Any]:
    data_dir = study_root / "data" / split
    index = read_json(data_dir / "request-index.json")
    case_manifest = read_json(data_dir / "cases.json")
    cells = load_cells(index, data_dir / "raw")
    return analyze_cells(index, cells, split, case_manifest=case_manifest, materials_verified=materials_verified,
                         charges_verified=charges_verified,
                         expected_case_count=24 if split == "pilot" else 96,
                         expected_control_case_count=8 if split == "pilot" else 16)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True, choices=("pilot", "heldout"))
    parser.add_argument("--study-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verified-materials", action="store_true", help="Assert external freeze/material verification is complete")
    parser.add_argument("--verified-charges", action="store_true", help="Assert budget ledger and charges/reservations are reconciled")
    args = parser.parse_args()
    analysis = analyze_study(args.study_root.resolve(), args.split,
                             materials_verified=args.verified_materials, charges_verified=args.verified_charges)
    destination = args.output or args.study_root / "results" / args.split / "analysis.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(analysis, indent=2, sort_keys=True, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")
    print(_canonical({"output": str(destination.resolve()), "split": args.split,
                      "planned": analysis["outcome_accounting"]["planned"],
                      "valid": analysis["outcome_accounting"]["valid"],
                      "pilot_gate_passes": analysis["pilot_gate"]["passes"] if analysis["pilot_gate"] else None}))


if __name__ == "__main__":
    main()
