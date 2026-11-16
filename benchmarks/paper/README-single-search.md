This file explains the single-search speed test. E12 is Maptology with exact-match priority, separate names and synonyms, and character trigrams. Each method searches one string at a time. There are no warmup searches. The first search is included in the total. Preparation time is saved separately.

The older `README.md` and dated tables describe the previous batch tests. Use the commands in this file for the new single-search test. The code does not change the app or upload files.

Use Python 3.13 with the benchmark packages installed. The measured environment used text2term 4.5.0, NumPy 2.3.5, SciPy 1.18.0, scikit-learn 1.8.0, pandas 2.3.3, psutil 7.2.2, and sparse-dot-topn 1.2.0. Input and asset preparation also needs Bioregistry, ormsgpack, and the imports used by `build/build_all_caches.py`. The recorded package versions are in `records/speed-single-no-warmup-20261116.json`. text2term declares older dependency ranges than this environment uses. A fresh dependency installation has not been tested. Use a separate Python environment if you need to install these packages. The code checks the input and ontology hashes and stops if they differ.

Open a terminal in the repository folder. In Windows PowerShell, prepare the files once:

```powershell
cd benchmarks\paper
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONHASHSEED = '0'
$env:PYTHONUTF8 = '1'
Remove-Item Env:MAPTOLOGY_BENCHMARK_ASSETS -ErrorAction SilentlyContinue
python -B code\build_inputs.py
python -B code\prepare_assets.py
```

`build_inputs.py` downloads the three source tables from the fixed text2term evaluation commit. It applies the same selection rules and recreates the six input files. `prepare_assets.py` downloads EFO 3.62.0 and builds the local indexes, lookup, and text2term cache under `assets/`. It uses only EFO. Existing files are checked before reuse. These commands need internet access for files that are not already downloaded. The local preparation folders are excluded from Git.

To test 100 fixed strings from each dataset, run:

```powershell
python -B code\run_speed.py --workloads sample --repeats 1
```

This performs 600 measured searches: 100 strings from each of three datasets for each of two methods. It uses the same fixed sample strings as the earlier short tests.

To test every evaluation row, run:

```powershell
python -B code\run_speed.py --workloads full --repeats 1
```

This performs 23,386 measured searches: 899 UKBB-EFO rows, 796 Biomappings rows, and 9,998 OLS-EFO rows for each method. Repeated strings are searched again. The code does not reuse saved query results. The completed full test took several hours. The selected searches alone total about 8.6 hours on the reference laptop. Preparation, saving, verification, and discarded attempts add time. Other computers may take a different amount of time.

For macOS or Linux, use the same Python commands and set the environment variables this way before running them:

```sh
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export PYTHONUTF8=1
unset MAPTOLOGY_BENCHMARK_ASSETS
```

`--repeats 1` means one completed round per method and dataset. Use `--repeats 5` only if you want five rounds. `--workloads all` runs both sizes separately. Add `--estimate` to print an estimate without running searches. `--sample` is a different option: it checks the code on only three strings per dataset and is not the 100-string test.

Keep a laptop plugged into its power adapter and awake. The code checks power before and after preparation and every search. Computers without a reported battery are recorded as `no_battery_reported`. Each method and dataset starts in a new process. The process loads its existing index or ontology terms before timing, then runs the searches in order. A new process is not started for every string. The operating system file cache is not cleared.

E12 loads its index and lookup and prepares its scoring matrix before timing. text2term loads and filters its ontology terms and constructs its `TFIDFMapper` before timing. Each timed text2term call still performs the library's TF-IDF fitting. Both methods search the same 29,374 terms and return up to five suggestions. The timer includes candidate generation and initialization inside the first search. Imports, preparation, input loading, logging, and output checks are outside the search timer.

`code/run_speed.py` manages the run and writes the tables. `code/single_speed_worker.py` measures one method and dataset in a new process. `code/single_search.py` prepares the methods and runs a single search. `code/verify_speed_run.py` checks the completed run in a separate process. Verification searches happen after timing and are not warmups. `code/verify_single_search.py` provides an additional comparison with the reference implementations.

Each run prints a new folder under `runs/`. `speed-results.tsv` contains the totals and average time per search. `speed-rounds.tsv` contains each round's total. `setup-times.tsv` contains preparation time. `speed-timings.tsv` contains the individual requests. `status.json` records the environment and progress. `verification.json` must say `passed` before the run is accepted. The `groups/` folders contain live progress and request records. All times are in seconds. The average per search is the sum of request times divided by the number of measured requests. One round has no estimate of variation between rounds.

If power is disconnected or a run stops, its records stay on disk. Keep the code, inputs, assets, and options unchanged and use the printed run folder to resume. For example:

```powershell
python -B code\run_speed.py --workloads full --repeats 1 --resume runs\YOUR-RUN-FOLDER
```

Completed method-dataset groups are kept. An unfinished group starts again from its first input in a new process. Earlier attempts remain recorded with `selected_attempt=False` and are excluded from the final total. Do not use the older `prepare_upload.py` for single-search results. It expects the previous batch format.

The completed full results are in `results/speed-single-no-warmup-full-20261116.tsv`. The separate 100-string results are in `results/speed-single-no-warmup-sample-20261116.tsv`. Their round totals and preparation tables use the same names with `-rounds` and `-setup` added. The full results below are in seconds:

| Dataset | Inputs | E12 total | E12 average per search | text2term total | text2term average per search |
| --- | ---: | ---: | ---: | ---: | ---: |
| UKBB-EFO | 899 | 4.305 | 0.00479 | 3474.268 | 3.86459 |
| Biomappings | 796 | 3.212 | 0.00404 | 2485.216 | 3.12213 |
| OLS-EFO | 9998 | 41.422 | 0.00414 | 25044.520 | 2.50495 |
| All three datasets | 11693 | 48.939 | 0.00419 | 31004.004 | 2.65150 |

Both sizes completed with zero warmups and passed verification. All selected requests recorded the laptop plugged in before and after each search. The first full text2term OLS attempt stopped during request 2671 after power was disconnected. Its 2671 records are preserved but excluded. That condition was restarted, and all 9,998 requests completed. The other five completed conditions were kept. There is one completed round per condition.

The compressed TSV files under `raw/` retain each request's timing, power state, status, and attempt selection. They omit the source strings, identifiers, and candidate mappings. Match requests to the regenerated inputs using dataset, workload, and request index. Python can read these files with `gzip.open(path, 'rt', encoding='utf-8')`. The source run hashes, original verification results, export checks, and code hashes are in `records/speed-single-no-warmup-20261116.json`.

Only comments, description strings, and the estimate's reference table changed after the completed measurements. The export record checks that the search and timing function bodies are unchanged. The recorded full timings were not measured again for this upload. The shorter publication check is a code check and is not included in these results.

These results measure the search engine, not file upload, browser rendering, or human review. They do not replace the earlier accuracy tables. The datasets were used during development, so they are not independent accuracy validation. The existing accuracy table used batch calls. This timing test uses separate single-string calls.
