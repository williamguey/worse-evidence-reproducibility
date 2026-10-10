# When User Preferences Lead LLMs to Choose Worse Evidence

Code and data to reproduce the paper's results offline: fixed case banks,
prompts and settings, exact answer keys, retained responses, unavailable cells,
and analysis scripts. Manuscripts, reviews, private accounting and credentials
are excluded.

## Results and data

| Case bank or summary | Location and output |
| --- | --- |
| Initial study, including the original Holm2 family and failed source test | `followup-reproducibility/original/results/heldout/analysis.json` |
| Matched 96-case evaluations and Holm10 | `followup-reproducibility/baidu/results/paper-holm10.json`; native panels and scored cells in the same results directory |
| Separate 96-case popular-model evaluation and Holm5 | `popular-model-extension/expected-analysis.json`, `expected-controls.json`, and projected responses in `outcomes.json` |
| Shared 312-case construct validation and Holm9 | `construct-validation-312/expected-analysis.json`; cases, full plan, exact request bodies and responses in the same directory |
| Paired transitions, display-order diagnostics and regret by numerical gap | `descriptive-diagnostics/`, `figure-diagnostics/`, `gap-band-description/` |
| Existing-data summaries and editable scientific figures | `existing-data-synthesis/existing-data-synthesis/` |

The case banks and their testing families remain separate. Matched evaluations
reuse the same 96 cases; reused Luna responses count once. Partly collected Qwen
and other unavailable outcomes remain in their planned cells. Descriptive
summaries add no hypothesis tests or confidence intervals. Each module's README
explains its estimands, missingness and file commitments.

## Reproduce offline

Only Python and its standard library are needed. No API calls, credentials or
network access are required. The original and matched analyses were produced
with Python 3.9.6; use that version for byte-stable reproduction. The remaining
commands were checked with Python 3.12.14; construct validation requires Python
3.10 or newer.

Start from a disposable copy: the older reproduction command rewrites derived
results inside its bundle. From the repository root:

```sh
(cd followup-reproducibility && python3.9 -B offline_reproduce.py)

mkdir -p ../h01-reproduced
python3.12 -B descriptive-diagnostics/descriptive_diagnostics.py \
  --bundle-root followup-reproducibility \
  --output ../h01-reproduced/transition-diagnostics.json
python3.12 -B popular-model-extension/reproduce.py \
  --repository popular-model-extension --output ../h01-reproduced/extension
python3.12 -B gap-band-description/gap_band_diagnostics.py \
  --repository . --output ../h01-reproduced/gap-band-table.json
python3.12 -B figure-diagnostics/paired_transitions.py \
  --scored-cells ../h01-reproduced/extension/reproduced-cells.json \
  --output ../h01-reproduced/extension-transitions.json
python3.12 -B figure-diagnostics/gap_bands.py \
  --scored-cells ../h01-reproduced/extension/reproduced-cells.json \
  --output ../h01-reproduced/extension-gap-bands.json
python3.12 -B figure-diagnostics/order_diagnostics.py \
  --matched-scored-cells followup-reproducibility/baidu/results/new-scored-cells.json \
  --extension-scored-cells ../h01-reproduced/extension/reproduced-cells.json \
  --output ../h01-reproduced/order-diagnostics.json
python3.12 -B construct-validation-312/reproduce.py
```

The popular-model and 312-case scripts verify their committed inputs, independently
check exact answer keys, and compare regenerated analyses with the expected
results. Construct validation retains all 22,656 planned cells, with 312
scientific cases, three configurations, twelve conditions, two display orders
and 192 separate control responses. Its outputs are
`construct-validation-312/reproduced/analysis.json` and `scored.json`.

The regenerated diagnostic JSON files match the corresponding committed files
in `descriptive-diagnostics/`, `figure-diagnostics/` and `gap-band-description/`.
For the synthesis tables and figures, follow
[the companion README](existing-data-synthesis/existing-data-synthesis/README.md).
Compiling its editable figure sources also requires LaTeX with PGFPlots; this is
optional for numerical reproduction.
