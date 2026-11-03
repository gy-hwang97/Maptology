"""Measure E12 and text2term on fixed N=100 and whole-dataset inputs."""

import argparse
import gc
import importlib.metadata
import json
import os
import statistics
import sys
import time

import numpy as np

import benchmark_common as common


sys.path.insert(0, str(common.CODE_DIR / "method"))
import engines
from optimized import OptimizedE12


CONDITIONS = ("batch32_dedup", "batch32", "T")
RAW_COLUMNS = (
    "dataset", "workload", "method_id", "repeat", "warmup", "input_rows",
    "power_before", "power_after", "eligible", "status", "seconds",
    "rank_mismatches", "score_mismatches", "error",
)
SUMMARY_COLUMNS = (
    "dataset", "workload", "method_id", "method_name", "input_rows",
    "distinct_inputs", "primary_comparison", "repetitions", "successes",
    "failures", "median_seconds", "mean_seconds", "sample_sd_seconds",
    "min_seconds", "max_seconds", "rank_mismatches", "score_mismatches",
)


def make_workloads(dataset, sample):
    rows = common.input_rows(dataset)
    selected = common.read_tsv(common.INPUT_DIR / ("speed-sample-" + dataset + ".tsv"))

    ids = []
    texts = []
    for position, row in enumerate(selected):
        if sample and position >= 10:
            break
        ids.append("n" + str(position))
        texts.append(row["input_key"])
    first_name = "N=100 sample"
    if sample:
        first_name = "Code check: N=10"

    full_ids = []
    full_texts = []
    for position, row in enumerate(rows):
        if sample and position >= 50:
            break
        full_ids.append(row["evaluation_row_id"])
        full_texts.append(row["input_key"])
    second_name = "All evaluation rows"
    if sample:
        second_name = "Code check: first 50 rows"

    return [(first_name, ids, texts), (second_name, full_ids, full_texts)]


def signatures(method, output):
    signatures = []
    if method == "T":
        for item in output:
            pairs = []
            for iri, score in zip(item[1], item[2]):
                pairs.append((iri, float(score)))
            signatures.append(pairs)
    else:
        for candidates, _ in output:
            pairs = []
            for candidate in candidates:
                iri = candidate["Ontology Term URI"]
                score = float(candidate["Mapping Score"])
                pairs.append((iri, score))
            signatures.append(pairs)
    return signatures


def expected_signatures(texts, reference):
    expected = []
    for text in texts:
        rows, _ = reference[str(text).strip()]
        pairs = []
        for row in rows:
            pairs.append((row["Ontology Term URI"], float(row["Mapping Score"])))
        expected.append(pairs)
    return expected


def compare(actual, expected):
    rank_mismatches = 0
    score_mismatches = 0
    if len(actual) != len(expected):
        return 1, 1
    for ours, theirs in zip(actual, expected):
        if len(ours) != len(theirs):
            rank_mismatches += 1
            score_mismatches += 1
            continue
        rank_wrong = False
        score_wrong = False
        for first, second in zip(ours, theirs):
            if first[0] != second[0]:
                rank_wrong = True
                score_wrong = True
            elif not np.isclose(first[1], second[1], rtol=1e-12, atol=1e-12):
                score_wrong = True
        if rank_wrong:
            rank_mismatches += 1
        if score_wrong:
            score_mismatches += 1
    return rank_mismatches, score_mismatches


def run_call(method, ids, texts, searcher):
    if method == "T":
        frame = engines.t2t_map(texts, ids)
        return engines.t2t_relink(frame, ids, texts)
    dedup = method == "batch32_dedup"
    output, _ = searcher.many(texts, batch_size=32, dedup=dedup)
    return output


def measure(dataset, workload, method, repeat, ids, texts, searcher, reference, first_t, folder, rows):
    gc.collect()
    before = common.power_state()
    record = {
        "dataset": dataset,
        "workload": workload,
        "method_id": method,
        "repeat": repeat,
        "warmup": repeat == 0,
        "input_rows": len(texts),
        "power_before": before,
        "power_after": "",
        "eligible": False,
        "status": "not_run",
        "seconds": "",
        "rank_mismatches": 0,
        "score_mismatches": 0,
        "error": "",
    }

    output = None
    if before != "mains":
        record["status"] = "power_ineligible"
    else:
        start = time.perf_counter()
        try:
            output = run_call(method, ids, texts, searcher)
            record["seconds"] = time.perf_counter() - start
            record["status"] = "ok"
        except Exception as failure:
            record["status"] = "error"
            record["error"] = repr(failure).replace("\t", " ").replace("\n", " ")

    after = common.power_state()
    record["power_after"] = after
    record["eligible"] = before == "mains" and after == "mains"
    if output is not None:
        actual = signatures(method, output)
        if method == "T":
            key = (dataset, workload)
            if key not in first_t:
                first_t[key] = actual
            wanted = first_t[key]
            for item in output:
                if item[3] == "conflicting_outputs":
                    record["status"] = "output_conflict"
        else:
            wanted = expected_signatures(texts, reference)
        rank, score = compare(actual, wanted)
        record["rank_mismatches"] = rank
        record["score_mismatches"] = score
        if rank or score:
            record["status"] = "output_mismatch"

    rows.append(record)
    common.write_tsv(folder / "speed-timings.tsv", RAW_COLUMNS, rows)
    print(dataset, workload, method, "repeat", repeat, record["status"], record["seconds"], flush=True)
    if not record["eligible"] or record["status"] != "ok":
        raise RuntimeError("The timing stopped; see speed-timings.tsv")
    return record


def summarize(rows, plans):
    output = []
    for dataset in common.DATASETS:
        for workload in ("N=100 sample", "All evaluation rows"):
            for method in CONDITIONS:
                attempts = []
                values = []
                errors = 0
                rank = 0
                score = 0
                for row in rows:
                    if row["dataset"] != dataset or row["workload"] != workload:
                        continue
                    if row["method_id"] != method or row["warmup"]:
                        continue
                    attempts.append(row)
                    if row["status"] == "ok" and row["eligible"]:
                        values.append(float(row["seconds"]))
                        rank += row["rank_mismatches"]
                        score += row["score_mismatches"]
                    else:
                        errors += 1
                if not attempts:
                    continue
                name = common.NAMES["T"]
                primary = "yes"
                if method != "T":
                    name = common.NAMES["E12"]
                    if method == "batch32":
                        primary = "no"
                first = attempts[0]
                distinct = 0
                for plan_name, _, plan_texts in plans[dataset]:
                    if plan_name == workload:
                        cleaned = set()
                        for text in plan_texts:
                            cleaned.add(str(text).strip())
                        distinct = len(cleaned)
                summary = {
                    "dataset": dataset,
                    "workload": workload,
                    "method_id": method,
                    "method_name": name,
                    "input_rows": first["input_rows"],
                    "distinct_inputs": distinct,
                    "primary_comparison": primary,
                    "repetitions": len(attempts),
                    "successes": len(values),
                    "failures": errors,
                    "median_seconds": "",
                    "mean_seconds": "",
                    "sample_sd_seconds": "",
                    "min_seconds": "",
                    "max_seconds": "",
                    "rank_mismatches": rank,
                    "score_mismatches": score,
                }
                if values:
                    summary["median_seconds"] = statistics.median(values)
                    summary["mean_seconds"] = statistics.mean(values)
                    summary["min_seconds"] = min(values)
                    summary["max_seconds"] = max(values)
                if len(values) > 1:
                    summary["sample_sd_seconds"] = statistics.stdev(values)
                output.append(summary)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true", help="Code check only; not paper data")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    if os.environ.get("PYTHONHASHSEED") != "0":
        raise RuntimeError("Set PYTHONHASHSEED=0 before starting Python")
    if common.power_state() != "mains":
        raise RuntimeError("Connect AC power before measuring speed")
    common.check_assets(include_all_indexes=False)

    reference_path = common.ASSET_DIR
    reference_path = os.path.join(reference_path, "e12-optimization-test-20261024", "data")
    reference_path = os.path.join(reference_path, "verify-20261024T070858252278Z", "reference-predictions.json")
    with open(reference_path, "r", encoding="utf-8") as handle:
        reference = json.load(handle)

    state, lookup = engines.load_for("E12")
    searcher = OptimizedE12(state, lookup, "EFO-3.62.0-common-29374")
    import text2term

    label = "speed"
    if args.sample:
        label = "speed-sample"
    folder = common.new_run(label)
    status = {
        "status": "running",
        "power_at_start": common.power_state(),
        "python": sys.version,
        "text2term": importlib.metadata.version("text2term"),
        "sample": args.sample,
        "repeats": args.repeats,
        "input_hashes": common.input_hashes(),
        "code_hashes": common.code_hashes(),
        "assets_folder": common.ASSET_DIR,
        "timer": "One call; imports, input loading, index loading, output checks and gc.collect are outside.",
    }
    common.write_json(folder / "status.json", status)

    rows = []
    first_t = {}
    try:
        plans = {}
        for dataset in common.DATASETS:
            plans[dataset] = make_workloads(dataset, args.sample)

        pilot = {}
        pilot_workload, pilot_ids, pilot_texts = plans["OLS-EFO"][0]
        for method in CONDITIONS:
            record = measure("OLS-EFO", "Pilot", method, 0, pilot_ids, pilot_texts,
                             searcher, reference, first_t, folder, rows)
            pilot[method] = float(record["seconds"])

        estimate = 0.0
        for dataset in common.DATASETS:
            for _, _, texts in plans[dataset]:
                ratio = len(texts) / len(pilot_texts)
                estimate += (args.repeats + 1) * (pilot["T"] + ratio * (pilot["batch32"] + pilot["batch32_dedup"]))
        print("Estimated remaining minutes:", round(estimate / 60, 1), flush=True)

        for dataset in common.DATASETS:
            for workload, ids, texts in plans[dataset]:
                for repeat in range(args.repeats + 1):
                    shift = repeat % len(CONDITIONS)
                    order = CONDITIONS[shift:] + CONDITIONS[:shift]
                    for method in order:
                        measure(dataset, workload, method, repeat, ids, texts,
                                searcher, reference, first_t, folder, rows)
        status["status"] = "complete"
    except Exception as failure:
        status["status"] = "stopped"
        status["error"] = repr(failure)
        raise
    finally:
        if not args.sample:
            summaries = summarize(rows, plans)
            common.write_tsv(folder / "speed-results.tsv", SUMMARY_COLUMNS, summaries)
        status["power_at_end"] = common.power_state()
        status["timing_rows"] = len(rows)
        common.write_json(folder / "status.json", status)
        print("Output:", folder, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
