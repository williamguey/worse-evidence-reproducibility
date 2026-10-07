Offline H01 descriptive transition companion

This companion adds a post hoc descriptive diagnostic for the completed H01
follow-up. It reads the unchanged followup-reproducibility bundle and does not
replace or modify its frozen scientific artifacts or primary inference.

Files:
  descriptive_diagnostics.py   Portable Python standard-library script.
  transition-diagnostics.json  Genuine diagnostic output from the public baseline.
  README.txt                  These instructions.
  sha256-manifest.json         SHA256 hashes for the three files above and the
                             unchanged baseline ZIP; excludes the manifest itself.

Use Python 3.9 or later. Extract this companion next to the existing
followup-reproducibility directory. From descriptive-diagnostics/, run:

  python3 -B descriptive_diagnostics.py --bundle-root ../followup-reproducibility

To save a reproduction outside the input bundle, run:

  python3 -B descriptive_diagnostics.py --bundle-root ../followup-reproducibility --output reproduced-transition-diagnostics.json

The saved reproduction should be byte-identical to transition-diagnostics.json.
The script also accepts the baseline's baidu/ directory as --bundle-root. It
requires no packages, credentials, network access, or new model calls.

Each transition pairs neutral and strong-inferior-endorsement responses within
the same configuration, case, report order, and raw/supplied representation.
CC = correct to correct; CW = correct to wrong; WC = wrong to correct;
WW = wrong to wrong. Correctness is independently checked against exact-rational
case parameters and the published final raw answer, then checked for agreement
with the scored labels and published descriptive aggregates.

Each configuration and representation has 192 planned paired response slots,
formed by two report orders within the same 96 independent whole-case clusters.
The slots are not 192 independent cases. Controls are excluded. A transition
requires both responses to be frozen-scored valid. Planned and complete pair
denominators, missing pairs, report-order slices, and optimal-label slices are
explicit. Luna is reused from the preceding panel; its supplied diagnostic has
191 complete slots because one pressure response is missing.

All summaries are descriptive and post hoc. The script performs no inferential
tests or confidence-interval calculations. Final-output transitions do not
establish internal knowledge, intent, or a causal provider mechanism.
