# Minimal portable cross-bank inputs

This directory contains scientific field projections of ten existing reproduced
source files, preserving their relative layout for the unchanged
`build_crossbank.py`. The projection keeps only the 19 plotted contrasts,
selected scored choices, case weighting, required missing-response counts and
existing confidence intervals. It excludes controls, unrelated historical
analyses, pricing, usage tokens, request identifiers, receipts, local paths,
reviews and hidden reasoning.

From a parent directory containing the builder and this directory:

```text
python3 -B build_crossbank.py --reproduction-root portable-inputs --out reproduced-output
```

The script uses only the Python standard library. It counts and joins existing
choices, checks exact native means and identification bounds, then copies native
confidence intervals. It sends no model requests and computes no new inference.
An exact rebuilding check already matched every field of all 19 scientific rows
to the full-source version, including all eight rows with existing simultaneous
intervals. The CSV is byte identical. JSON input commitments differ because they
truthfully identify these smaller projected inputs.

`projection-manifest.json` binds each projected file to both its original source
hash and projected hash. The separate equality receipt records the observed
offline check. The original source files and previously finalized forest files
remain unchanged. Separate case banks, incomplete outcomes and native weighting
are retained; no case pooling or new completed model evaluation is asserted.
