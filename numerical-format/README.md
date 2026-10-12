# Neutral errors by numerical format

This addition reproduces post hoc descriptive summaries from the completed
312-case construct-validation experiment. It requires the existing
`construct-validation-312` directory from this repository. No model calls,
network access, API keys, or third-party Python packages are needed.

From the repository root, run Python 3.10 or newer:

```sh
python3 -B numerical-format/reproduce.py --package construct-validation-312 --out reproduced-numerical-format
```

For a standalone copy of this folder, supply the location of the existing
`construct-validation-312` directory with `--package`; `--out` selects a new
results directory. The script verifies the source package hashes, checks exact
report totals against the displayed prompts, retains every unavailable choice,
and reproduces all 3,744 planned neutral choices and 36 descriptive summary
rows. It requires exact equality with `expected.json` and writes
`numerical-format-results.json` only after verification succeeds.

The main paper uses neutral repeat 2, which supplies the baseline for the
primary contrast. The separate first repeat is also retained. Each case plans
two choices per configuration and repeat. Format groups compare equal versus
different reduced denominators in the two displayed total costs. The cost-gap
groups use the original fixed normalized-gap bands. Counts, observed error
rates, and full-plan missingness bounds are retained for every group.

`analysis-plan.txt` records the definitions set before this descriptive
computation. `expected.json` contains complete group counts and case attributes.
No new hypothesis tests are introduced. Format and gap groups contain different
cases; their associations do not isolate numerical difficulty, task engagement,
or an internal reasoning mechanism. The primary analyses remain unchanged.
