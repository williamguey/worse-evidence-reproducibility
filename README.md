# When User Preferences Lead LLMs to Choose Worse Evidence

Reproduction materials for the paper by **William Guey**: fixed prompts and
settings, exact answer keys, projected model outputs and receipts, frozen
analysis code, and a post hoc descriptive transition companion.

## Run offline

Requires Python 3.9.6 or later and its standard library. No packages, credentials,
network access, or new model calls are needed.

```sh
cd followup-reproducibility
python3 -B offline_reproduce.py
```

This rewrites derived cohort results; copy the repository first to preserve the
distributed outputs. From the repository root, reproduce the additional
transition summaries with:

```sh
python3 -B descriptive-diagnostics/descriptive_diagnostics.py \
  --bundle-root followup-reproducibility \
  --output reproduced-transition-diagnostics.json
```

The transition output should be byte-identical to
`descriptive-diagnostics/transition-diagnostics.json`.

## Output-to-paper mappings

| Paper result | Reproduction output |
| --- | --- |
| Table 1: follow-up raw-pressure endpoints and Holm10 | `followup-reproducibility/baidu/results/paper-holm10.json` |
| Table 2: follow-up arm errors and regret | `followup-reproducibility/baidu/results/new-native-holm4.json`, `original-holm4.json`, and their `new-scored-cells.json` / `old-scored-cells.json` inputs |
| Table 3: paired choice transitions | `descriptive-diagnostics/transition-diagnostics.json` |
| Tables 4–8: initial cohort's model, arm, secondary and pooled contrasts | `followup-reproducibility/original/results/heldout/analysis.json` |
| Pilot expansion evidence | `followup-reproducibility/original/results/pilot/analysis.json` |

The initial cohort's failed source test and Holm2 family are retained. Follow-up
stages use the same 96 case clusters; the Luna assignments are exact reuse and
contribute only one endpoint to Holm10. Interrupted and unavailable stages are
retained, without pooling providers or counting repeated cases as new cases.
The transition companion is post hoc descriptive evidence, not a new test.

Each bundle's README explains its layout and record projections. Provenance and
public-file hashes are in
`followup-reproducibility/provenance/publication-manifest.json`;
`descriptive-diagnostics/sha256-manifest.json` identifies the companion and its
unchanged baseline archive.
