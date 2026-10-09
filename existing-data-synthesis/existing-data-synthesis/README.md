# Existing-data synthesis companion

This editable offline companion supplies five post hoc descriptive summaries and
three grayscale scientific figures. It adds no model calls, hypothesis tests or
confidence intervals. The shared bank retains all 22,656 planned choices,
312 scientific cases and 32 controls, with two display orders nested in each
case. Every planned missing choice remains unavailable in the CSV.

## Reproduce with Python 3.9 or newer

Use a fresh output directory (the script never overwrites a prior diagnostics run):

```
python3 diagnostics/compute.py --output new-diagnostics
python3 crossbank/build_crossbank.py --reproduction-root crossbank/portable-inputs --out new-crossbank
python3 figures/build_rates.py
python3 figures/build_forest.py
```

The diagnostics JSON must match `diagnostics/expected-synthesis-diagnostics.json`
exactly. The cross-bank JSON and CSV must match the committed files in
`crossbank/` exactly. Existing scientific input files are minimally projected;
their original and projected SHA256 commitments are retained in
`crossbank/portable-inputs/projection-manifest.json`. No private accounting,
credentials, provider request IDs, receipt data, model reasoning or manuscripts are needed.

Compile `figures/endorsement-rates.tex`, `figures/cross-bank-standalone.tex`, and
`figures/wording-components.tex` using an existing LaTeX installation with
standalone, lmodern, PGFPlots and capt-of, for example:

```
tectonic --only-cached figures/endorsement-rates.tex
tectonic --only-cached figures/cross-bank-standalone.tex
tectonic --only-cached figures/wording-components.tex
```

The figure sources contain literal coordinates and need no external image/data
at compile time. Wrapped inline versions use `choices-priority.tex`,
`cross-bank.tex` and `cue-components.tex`. The five table source generator is
included for transparency; bound endpoints are rounded outward using exact
integer fractions. Data tables also retain unrounded fractions/proportions.

## What the numbers mean

Neutral identity, first-numerically-displayed, endorsement following, control
type/order and both-order following rates are descriptive realized choices.
First numerical position is distinct from first lexical mention. The guard
neutral comparison is post hoc, with no new test or confidence interval.
Binary identification bounds retain every planned unavailable outcome; they
are not confidence intervals and do not correct shared-service dependence.

The forest keeps four case banks separate. Older strong-endorsement contrasts
and the shared-bank bundle contrast, raw and supplied-cost prompts, and
different configurations are not pooled. Seven completed configuration labels
span six model identifiers and five model families, across eleven bank slots.
Eight existing confidence intervals retain their original Holm10/Holm5/Holm9
families and independent whole-case assumptions. Eleven descriptive contrasts
explicitly have no reported confidence interval. No new inference is computed.
Full valid/planned/missing denominators and native weighting are in the JSON/CSV.
Partly stopped/unavailable provider panels and Qwen remain in the unchanged
scientific supplement, not as completed forest rows. Repeated matched-bank
cases and the reused GPT-6 Luna observations do not increase independent N.

Do not infer internal motives, a causal effect of provider/reasoning, general
insensitivity from one template, elimination of all error under the guard,
or exclusion of prompt-length/competence/noise mechanisms from these summaries.
