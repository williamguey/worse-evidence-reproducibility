Offline descriptive transition, coverage and numerical-gap addendum

Unpack code.zip and data.zip into the same new directory. Use Python 3.12.14
and its standard library. No network, credentials or new model calls are used.
First reproduce the fixed popular-model extension, then tabulate its pairs
and complete-case numerical-gap bands:

  python3 -B popular-model-extension/reproduce.py \
      --repository popular-model-extension --output /new/external/extension-results
  python3 -B figure-diagnostics/paired_transitions.py \
      --scored-cells /new/external/extension-results/reproduced-cells.json \
      --output /new/external/extension-transitions.json
  python3 -B figure-diagnostics/gap_bands.py \
      --scored-cells /new/external/extension-results/reproduced-cells.json \
      --output /new/external/extension-gap-bands.json

Use genuinely new output paths. Both summaries must be byte-identical to
their included expected JSON files in figure-diagnostics/. The standalone
addendum ZIP has this README, both portable scripts and both expected outputs;
it requires reproduced-cells.json from the unchanged extension companion.
Keep both scripts together: gap_bands.py imports paired_transitions.py.

Transitions match neutral and strong-inferior endorsement within a
configuration, representation, case and AB/BA report order. CC means correct
to correct, CW correct to wrong, WC wrong to correct, and WW wrong to wrong.
A pair requires both responses to be valid. Every row discloses all 192
planned pair slots, valid slots and missing slots. Those slots nest within
96 cases, not 192 independent cases. Controls are excluded. The full
3328-cell plan, including unavailable Qwen outcomes, is left unchanged.

Numerical-gap bands use exact inferior-minus-optimal expected cost divided
by pre-report Bayes risk: (0, .10], (.10, .35] and (.35, infinity). Each band
has 32 planned cases. A case/representation enters a band mean only if both
conditions are valid in both display orders. Cases receive equal weights
after the two orders are equally averaged. Arm counts concern those same
complete cases. Claude has one incomplete raw case, excluded only from its
descriptive band mean; it remains in the full-plan primary inference.
Qwen has no four-outcome complete cases, so its band means are unavailable.
Numerical gap is not a validated measure of task difficulty.

Both companions are post hoc descriptive. They add no hypothesis tests,
p-values, intervals or primary inference changes. Incomplete Qwen coverage
is not a null finding. Different case banks are not pooled. Transitions do
not establish internal knowledge, intent or a causal provider mechanism.
All earlier archive members retain their exact bytes. Earlier DeepSeek
descriptions remain unchanged. Older reproduction commands and pinned
runtimes remain documented in their existing READMEs.
