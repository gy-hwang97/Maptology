This folder contains the code and result tables for a comparison between Maptology and text2term. The two main result files are `results/accuracy-results-20261102.tsv` and `results/speed-results-20261102.tsv`. The first reports how often the correct ontology term is the top suggestion or in the top-five suggestions. The second reports the time needed to suggest terms for 100 inputs or for every row in an evaluation file. Times are in seconds.

These benchmarks were performed using input TSV files from the [text2term evaluation repository](https://github.com/rsgoncalves/text2term-evaluation/tree/b999dbb670fa13c9ceb1ba631a7abc7557f3293b), which links to the [UK Biobank to EFO mappings](https://github.com/EBISPOT/EFO-UKB-mappings), [Biomappings](https://github.com/biopragmatics/biomappings), and [OLS mapping downloads](https://www.ebi.ac.uk/ols4/downloads). The local `inputs/eval-*.tsv` files contain the selected search strings and correct term IDs. The local `inputs/speed-sample-*.tsv` files contain 100 fixed strings per dataset. Selection rules, counts, and hashes are recorded in `records/environment-20261031.json` and `records/environment-20261102.json`. These input TSV files are not included in this Git repository while their redistribution terms remain unconfirmed.

`code/build_inputs.py` downloads the three source tables from the fixed text2term evaluation commit linked above. It saves them under `sources/`, checks their SHA-256 hashes, and creates the six input TSV files under `inputs/`. It checks the recreated inputs against the hashes in `records/environment-20261102.json`. If an existing source or input file has a different hash, the script stops instead of replacing it.

For UKBB-EFO, it keeps `MAPPING_TYPE == "Exact"` and excludes mapping cells containing a comma or `||`, selecting 899 of 1,565 rows. For Biomappings, it keeps EFO targets with `skos:exactMatch`, selecting 796 of 10,431 rows. For OLS-EFO, it skips the 112-line comment block and excludes rows without `object_label`, selecting 9,998 of 35,028 rows. It converts reference IDs to IRIs with Bioregistry. Unresolved references stay in the input with an empty IRI, and repeated rows are kept.

The three speed-sample files use the same 100 distinct strings as before, selected with `random.Random(20261021)` from sorted distinct strings. Each execution writes the source URLs, row counts, hashes, and package versions to `runs/inputs-<time>/input-verification.json`. The completed download check is recorded in `records/input-download-verification-20261109.json`: all three source files were downloaded, and all six generated inputs matched the earlier benchmark files exactly.

Input generation was tested with Python 3.13, pandas 2.3.3, and Bioregistry 0.13.31. From `benchmarks/paper`, run:

```powershell
python -B code\build_inputs.py
```

This command prepares the inputs. The search benchmarks are run separately using the commands below.

The accuracy test uses UKBB-EFO (899 rows), Biomappings (796 rows), and OLS-EFO (9,998 rows). All six methods search the same 29,374 terms from EFO 3.62.0 and return up to five suggestions. A correct term that is outside this search set stays in the test and counts as a miss.

The original Maptology method, called `A` in the result files, searches words in each ontology term's name and synonyms as one combined text. `B2` uses the same search technique but puts terms with an exact matching name or synonym first. `E1` starts with `B2` and then searches each name and synonym as a separate text instead of combining them. `E2` starts with `B2` and searches overlapping groups of three characters (3-grams) instead of whole words. `E12` uses both techniques: it searches each name and synonym separately using 3-grams, and it keeps the exact-match priority of `B2`. `T` is text2term 4.5.0, called through its official TF-IDF API. `E12` and text2term share some search ideas, but they use different implementations.

`code/run_accuracy.py` runs the six methods on the fixed inputs, checks their suggestions against the correct terms, and writes accuracy TSV files in the `results` directory. `code/run_speed.py` measures execution time for the `E12` and text2term methods and writes TSV files to the `results` directory.

`code/prepare_upload.py` checks a completed run against the earlier accuracy results and places the dated TSV files in `results/` and `raw/`. `code/benchmark_common.py` reads and writes files and checks their hashes.

`code/method/engines.py` runs the search methods and calls text2term. `optimized.py` processes `E12` inputs in groups of 32 and reuses repeated strings within one call. `paths.py` finds the saved indexes and cache. `common.py` connects the optimized code to the search code.

`raw/speed-timings-20261102.tsv` records every timed call, including warm-ups, power state, errors, and output differences. The local `raw/accuracy-per-row-ranks-20261102.tsv` records the correct term's rank for each evaluation row and method. It is not included in this Git repository because it repeats source labels and mappings. `records/environment-20261102.json` records versions, inputs, the ontology hash, and timing rules. `records/required-assets.tsv` lists the files needed to run the code, with sizes and hashes. `records/rerun-verification-20261102.json` records that all 18 accuracy conditions kept the earlier hit counts, all 11,693 row ranks matched the earlier run, and all 111 speed calls succeeded on AC power.

`results/optimized-method-equivalence.tsv` comes from the earlier `E12` optimization study. It checks whether the original and optimized `E12` code returned the same terms, order, and scores. Its checks found no difference on the recorded inputs. The current speed script also checks optimized `E12` output against saved original `E12` output before accepting each timing. This file is evidence about those tested inputs, not a promise about every future input.

The speed test uses the same strings for both tools. `E12` uses an index loaded before timing and searches in groups of 32. text2term uses its ontology cache and its normal `map_terms` call. Each condition has one warm-up and five measured runs on AC power. The timer includes the search call and candidate selection. It excludes imports, input loading, index loading, garbage collection before the call, and result checks. The operating system file cache was not cleared. This speed table covers 100 inputs and whole files; it does not cover a user's first search, a single search, or index construction.

The Python files were run with Python 3.13 and text2term 4.5.0. A full rerun also needs the local input TSV files and the saved indexes, cache, and reference predictions listed in `records/required-assets.tsv`. Those files are not copied into this Git repository. To run the scripts on the original Windows computer, set `MAPTOLOGY_BENCHMARK_ASSETS` to the existing `testing folder` that contains `published-benchmark-accuracy`, `ranking-experiments-20261021-034704`, and `e12-optimization-test-20261024`.

```powershell
$env:MAPTOLOGY_BENCHMARK_ASSETS = 'C:\path\to\testing folder'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '0'
$env:PYTHONUTF8 = '1'

python -B code\run_accuracy.py
python -B code\run_speed.py --repeats 5
```

The speed command requires AC power. It records a failed call without a time and then stops. Both commands write to new dated folders under `runs/` and leave earlier results unchanged. After both commands finish, replace the folder names in this command with the names that the scripts print:

```powershell
python -B code\prepare_upload.py runs\accuracy-20261102T172014490185Z runs\speed-20261102T172440749389Z
```

The dated TSV files in `results/` are the current paper results. The undated accuracy summary is an earlier result that `run_accuracy.py` and `prepare_upload.py` read during their checks. `prepare_upload.py` also needs the earlier local row rank file. The full `runs/` folders stay local and are excluded from Git.

These public evaluation sets were used during method development, so the results are not an independent validation. The text2term paper used version 4.1.2, while this benchmark used 4.5.0. The benchmark code is separate from the deployed Maptology app. The published code and TSV tables document the measurements. The fixed input files can now be recreated with `code/build_inputs.py`. A full benchmark run on another computer still requires the saved search assets listed in `records/required-assets.tsv`.
