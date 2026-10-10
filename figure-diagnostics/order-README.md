Post hoc display-order diagnostics

Run using publicly reproduced scored cells:
python3 order_diagnostics.py --matched-scored-cells MATCHED/new-scored-cells.json --extension-scored-cells EXTENSION/reproduced-cells.json --output order-reproduced.json

The pure standard-library script checks the complete2496-cell matched-mode and3328-cell extension plans. It computes eight rows for matched DeepSeek off and Llama default, separately for raw/supplied inputs and AB/BA display order, excludes controls, requires both choices valid, and independently crosschecks exact-choice correctness against each error field. Planned pairs are96 per row. The two banks remain separate.

This post hoc descriptive table adds no hypothesis test and changes no primary inference. Response pairs and display orders are nested within numerical cases. The counts describe aggregate matched-response asymmetry; isolated flip causation is not identified without test-retest stability. No API, model query or third-party dependency is used. Input paths and non-scientific extras are omitted from deterministic output hashes.
