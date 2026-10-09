# Cross-bank pressure figure inputs

These 19 rows cover 11 configuration-by-bank slots across four separate case
banks. They include the completed Gemini evaluation and preserve both raw and
supplied-cost contrasts wherever those conditions were planned. They add no model
calls, hypothesis tests or confidence intervals.

`crossbank-pressure.json` is the figure input, `crossbank-pressure.csv` contains
the same flat rows, and `crossbank-checks.json` records arithmetic/count checks
and source commitments. `build_crossbank.py` uses only the Python standard
library and existing reproduced outputs. It verifies exact native weighting,
complete-case means, full-plan missingness bounds and cell counts. It extracts
existing intervals; it does not run scientific inference.

To rebuild, pass a root containing the relative source layout committed in the
JSON and a new output directory:

```text
python3 -B build_crossbank.py --reproduction-root REPRO_ROOT --out NEW_OUTPUT
```

An optional `--audited-shared-analysis ANALYSIS_JSON` checks exact equality of
the plotted 312-case bundle endpoint fields and every arm count against the
audited analysis. Other reproduced descriptive floating-point fields can differ
at rounding precision; full-file numerical equality is not asserted.

Eight rows have existing simultaneous 95% intervals: the three matched-bank raw
contrasts use Holm10-family simultaneous intervals, the two popular-bank raw
contrasts use Holm5-family intervals, and the three shared-bank supplied
bundle contrasts use Holm9-family confidence envelopes. Eleven descriptive
per-configuration rows have no native confidence interval. Their genuine
identification bounds remain available; absence of a confidence interval is
not evidence of precision or equivalence.

Points retain each source's published complete-case target. Original per-model
rows and the 312-case bank weight complete whole cases equally. Matched and
popular rows give each of eight strata equal weight, then weight available
complete cases equally within each stratum. The optional pair and unweighted
case mean columns prevent denominator confusion. In particular, matched GPT-6
Luna supplied has native mean -1/96, unweighted complete-case mean -1/95 and
valid-pair mean -2/191. These are different targets, not inconsistent data.

Raw prompts require cost calculation; supplied prompts explicitly state expected
totals. The shared 312-case bank compares the bundled inferior endorsement with
the second neutral repeat, rather than the older strong-endorsement condition.
Separate banks, versions and settings should therefore be visible in the figure.
The raw and supplied effects cannot be equated or interpreted as causal provider
effects or an isolated effect of deliberation. Seven distinct completed
configuration labels span six model identifiers and five model families; the
11 plotted bank slots do not represent 11 models or independent replications.

Display orders are nested within whole cases. The matched 96-case bank was
repeated across provider panels and GPT-6 Luna records were reused once
unchanged. Those repetitions add no independent cases. Full-plan identification
bounds allow arbitrary missing binary outcomes and do not correct dependence
from a shared service. Native confidence coverage assumes independence across
whole-case clusters. Partial Qwen, retired DeepInfra and unavailable CoreWeave
endpoints remain in the scientific supplement rather than appearing as completed
evaluations in this main figure.
