Portable companion for the H01 descriptive normalized-gap table

Run with Python 3.9 or later and its standard library:

  python3 -B gap_band_diagnostics.py --repository /path/to/published-repository \
      --output /path/outside/repository/gap-band-table.json

--repository also accepts an extracted followup-reproducibility ZIP directory
containing original/ and baidu/. No install, network access or paid query is
needed. The script reads the public scored-choice tables and case banks; it
leaves the repository/bundle unchanged and requires an external output path.
Only the requested JSON is written.

The script independently recomputes rational case optima and normalized gaps,
checks frozen band membership and scored correctness, preserves frozen
validity, excludes controls, and nests AB/BA within each case. Contrasts average
strong-inferior-minus-neutral errors across both orders, then equally average
cases complete in all four responses in a band. Counts disclose planned cases,
complete cases, planned responses per arm, valid responses and errors. Exact
fractions accompany percentage-point values.

The bands were prespecified; this model/configuration-by-band tabulation is
post hoc descriptive. Numerical gap is not validated task difficulty. The
companion adds no tests, p-values, intervals or baseline-success subgroups.
Original H01 and Baidu cohorts remain separate. It reads no raw reasoning,
ledger, collection transport or private study records; it exports only four
public scientific input hashes and the descriptive result.

gap-band-table.json is the verified expected result. Its 12 rows match the
independently validated manuscript table exactly. The four scientific input hashes identify the released records. A CSV copy is
included for convenient inspection. No repository upload is performed by this companion.
