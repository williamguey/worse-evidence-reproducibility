"""Canonical numeric source block, separate from the experimental prompt.

The root prompt builder may add the stipulated task, fictional scenario, and
archive label manipulation around this block.  No archive labels or choices
are generated here.  Parsing is deliberately strict so numeric omissions,
duplicates, and changed rational values fail an end-to-end source audit.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from decision_engine import serializable_parameters

_NUMBER = r"(?:[0-9]+(?:/[1-9][0-9]*)?)"
_BLOCK = re.compile(
    rf"Prior P\(Z=1\): (?P<prior>{_NUMBER})\n"
    rf"Loss ACT in state 0: (?P<loss_act>{_NUMBER})\n"
    rf"Loss WAIT in state 1: (?P<loss_wait>{_NUMBER})\n"
    rf"Report A: sensitivity=(?P<a_sens>{_NUMBER}); specificity=(?P<a_spec>{_NUMBER}); acquisition_cost=(?P<a_cost>{_NUMBER})\n"
    rf"Report B: sensitivity=(?P<b_sens>{_NUMBER}); specificity=(?P<b_spec>{_NUMBER}); acquisition_cost=(?P<b_cost>{_NUMBER})"
)


def render_parameter_block(case: Mapping[str, Any]) -> str:
    p = serializable_parameters(case)
    lines = [f"Prior P(Z=1): {p['prior_state1']}",
             f"Loss ACT in state 0: {p['loss_ACT_state0']}",
             f"Loss WAIT in state 1: {p['loss_WAIT_state1']}"]
    for report_id, report in p["reports"].items():
        lines.append(f"Report {report_id}: sensitivity={report['sensitivity']}; "
                     f"specificity={report['specificity']}; acquisition_cost={report['cost']}")
    return "\n".join(lines)


def parse_parameter_block(source: str) -> dict[str, Any]:
    match = _BLOCK.fullmatch(source)
    if match is None:
        raise ValueError("Source is not one complete canonical parameter block")
    groups = match.groupdict()
    raw = {"prior_state1": groups["prior"], "loss_ACT_state0": groups["loss_act"],
           "loss_WAIT_state1": groups["loss_wait"],
           "reports": {report_id: {"sensitivity": groups[f"{prefix}_sens"],
                                    "specificity": groups[f"{prefix}_spec"],
                                    "cost": groups[f"{prefix}_cost"]}
                       for report_id, prefix in (("A", "a"), ("B", "b"))}}
    return serializable_parameters(raw)


def validate_rendered_source(case: Mapping[str, Any], source: str) -> None:
    if parse_parameter_block(source) != serializable_parameters(case):
        raise ValueError("Rendered source parameters differ from the case record")
