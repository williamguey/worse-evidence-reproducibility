# Shared 312-case reproduction

The `construct-validation-312/` directory reproduces the shared 312-case study: three frozen configurations, twelve prompt conditions, both display orders, and 192 separate neutral controls. All 22,656 planned cells remain, including unavailable outcomes.

Run offline with standard Python 3.10 or newer:

```sh
cd construct-validation-312
python3 -B reproduce.py
```

No credentials, network, packages or new model calls are required. The command verifies file and request-body hashes, independently enumerates exact purchase scores, rebuilds scored cells, runs the frozen inference, and compares the complete result with `expected-analysis.json`. It writes a new `reproduced/` directory.

## Output mapping

| Scientific content | File |
| --- | --- |
| Exact numerical bank, controls and purchase costs | `cases.json`, `controls.json` |
| Full fixed plan, conditions, display orders and exact request bodies | `plan.json`, `bodies/`, `settings.json` |
| Retained final answers and unavailable cells | `responses.jsonl` |
| Nine primary tests, Holm correction, missingness bounds, all arms and secondary diagnostics | `expected-analysis.json`; regenerated `reproduced/analysis.json` |
| Cellwise choices, errors and exact expected regret | regenerated `reproduced/scored.json` |
| Protocol, estimands, inference and acquisition provenance | `protocol.md`, `analysis.md`, `inference.py`, `audit-summary.json` |

The existing `followup-reproducibility/` and `descriptive-diagnostics/` directories are unchanged and remain separate banks. This addition does not pool them, reinterpret their testing families, or replace unavailable outcomes. Figure numbers depend on the manuscript edition; this guide maps scientific quantities rather than stale figure numbering. Hidden reasoning, credentials, accounting databases, manuscript drafts, reviews and study expenditure are excluded.
