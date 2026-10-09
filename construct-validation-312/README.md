# H01 construct-validation offline reproduction

This package reconstructs the observed fixed-plan analysis for three frozen
model configurations, twelve conditions, two display orders and 312 numerical
cases. The plan also includes 192 neutral control calls. Every unavailable and
never-attempted cell is retained. The two orders are nested within cases.

Run with standard Python 3.10 or newer, without an API key or network:

    python3 -B reproduce.py

The script verifies all package hashes, independently enumerates exact report
scores, parses only retained final answer content, rebuilds every planned scored
cell, runs the frozen inference source and compares its full result with the
expected audited analysis. An API rerun is optional and nondeterministic; it is
not needed for numerical reproduction. Original request bodies are deduplicated
by their byte hash, and each plan row maps to its frozen body.

The unit of inference is a whole numerical case, conditional on the realized
bank. Three directional endpoints per configuration form Holm9. Missingness is
handled with fixed-plan lower/upper envelopes. Whole-case response independence
is an assumption; envelopes do not correct shared-service dependence. Guards or
simplification do not identify a psychological mechanism.

Acquisition metadata records request-intent/worker/terminal timestamps. They
are not physical wire-send times. Final answer content and receipt identities
are included; hidden reasoning content, credentials, monetary study totals,
review manuscripts, private notes and the shared accounting DB are excluded.
