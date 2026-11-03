"""Check a new full run and place its TSV files beside the older tables."""

import argparse
import importlib.metadata
import os
import platform
import sys
from pathlib import Path

import benchmark_common as common
import psutil


def read_status(folder):
    import json

    with (folder / "status.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def check_accuracy(folder):
    status = read_status(folder)
    if status["status"] != "complete" or status["sample_rows_per_dataset"] is not None:
        raise RuntimeError("Accuracy input is not a completed full run")

    new_summary = common.read_tsv(folder / "accuracy-results.tsv")
    old_summary = common.read_tsv(common.PACKAGE_DIR / "results" / "accuracy-results.tsv")
    if len(new_summary) != 18 or len(old_summary) != 18:
        raise RuntimeError("The accuracy summary does not have 18 conditions")

    old_by_key = {}
    for row in old_summary:
        key = (row["dataset"], row["method_id"])
        old_by_key[key] = row
    for row in new_summary:
        key = (row["dataset"], row["method_id"])
        previous = old_by_key[key]
        for field in ("evaluation_rows", "top1_hits", "top5_hits"):
            if row[field] != previous[field]:
                raise RuntimeError("Accuracy changed: " + str(key) + " " + field)
        if row["errors"] != "0":
            raise RuntimeError("Accuracy recorded an error: " + str(key))

    detailed = common.read_tsv(folder / "accuracy-per-row.tsv")
    by_id = {}
    for row in detailed:
        row_id = row["evaluation_row_id"]
        if row_id not in by_id:
            by_id[row_id] = {}
        method = row["method_id"]
        if method in by_id[row_id]:
            raise RuntimeError("Duplicate accuracy row: " + row_id + " " + method)
        by_id[row_id][method] = row
    if len(by_id) != 11693 or len(detailed) != 11693 * 6:
        raise RuntimeError("The accuracy detail has the wrong number of rows")

    previous_detail = common.read_tsv(common.PACKAGE_DIR / "raw" / "accuracy-per-row-ranks.tsv")
    if len(previous_detail) != 11693:
        raise RuntimeError("The old rank table has the wrong number of rows")

    columns = (
        "dataset", "evaluation_row_id", "source_id", "input_text", "gold_iri",
        "gold_in_target", "A_rank", "B2_rank", "E1_rank", "E2_rank",
        "E12_rank", "T_rank",
    )
    compact = []
    rank_changes = 0
    for previous in previous_detail:
        row_id = previous["evaluation_row_id"]
        methods = by_id[row_id]
        if len(methods) != 6:
            raise RuntimeError("A row is missing a method: " + row_id)
        entry = {}
        for field in ("dataset", "evaluation_row_id", "source_id", "input_text", "gold_iri", "gold_in_target"):
            entry[field] = previous[field]
        for method in common.METHODS:
            current = methods[method]
            if current["dataset"] != previous["dataset"]:
                raise RuntimeError("Dataset mismatch for " + row_id)
            if current["gold_iri"] != previous["gold_iri"]:
                raise RuntimeError("Gold IRI mismatch for " + row_id)
            new_rank = current["gold_rank"]
            if new_rank == "0":
                new_rank = ""
            entry[method + "_rank"] = new_rank
            if new_rank != previous[method + "_rank"]:
                rank_changes += 1
        compact.append(entry)
    return new_summary, columns, compact, rank_changes


def check_speed(folder):
    status = read_status(folder)
    if status["status"] != "complete" or status["sample"]:
        raise RuntimeError("Speed input is not a completed full run")
    if status["power_at_start"] != "mains" or status["power_at_end"] != "mains":
        raise RuntimeError("The speed run was not fully on AC power")

    raw = common.read_tsv(folder / "speed-timings.tsv")
    summary = common.read_tsv(folder / "speed-results.tsv")
    if len(raw) != 111 or len(summary) != 18:
        raise RuntimeError("The speed run has an unexpected number of rows")
    for row in raw:
        if row["status"] != "ok":
            raise RuntimeError("A speed call failed")
        if row["power_before"] != "mains" or row["power_after"] != "mains":
            raise RuntimeError("A speed call was not on AC power")
        if row["rank_mismatches"] != "0" or row["score_mismatches"] != "0":
            raise RuntimeError("A speed output differed from its reference")
    for row in summary:
        if row["successes"] != "5" or row["failures"] != "0":
            raise RuntimeError("A speed condition did not have five successful repeats")
    return summary, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accuracy_run", type=Path)
    parser.add_argument("speed_run", type=Path)
    args = parser.parse_args()

    accuracy, rank_columns, ranks, rank_changes = check_accuracy(args.accuracy_run)
    speed, raw_speed = check_speed(args.speed_run)
    result_dir = common.PACKAGE_DIR / "results"
    raw_dir = common.PACKAGE_DIR / "raw"

    common.write_tsv(result_dir / "accuracy-results-20261102.tsv", accuracy[0].keys(), accuracy)
    common.write_tsv(result_dir / "speed-results-20261102.tsv", speed[0].keys(), speed)
    common.write_tsv(raw_dir / "accuracy-per-row-ranks-20261102.tsv", rank_columns, ranks)
    common.write_tsv(raw_dir / "speed-timings-20261102.tsv", raw_speed[0].keys(), raw_speed)

    accuracy_status = read_status(args.accuracy_run)
    speed_status = read_status(args.speed_run)
    package_versions = {}
    for name in ("numpy", "scipy", "scikit-learn", "pandas", "text2term", "sparse-dot-topn", "psutil"):
        package_versions[name] = importlib.metadata.version(name)
    environment = {
        "accuracy_run": args.accuracy_run.name,
        "speed_run": args.speed_run.name,
        "python": speed_status["python"],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "physical_cpus": psutil.cpu_count(logical=False),
        "packages": package_versions,
        "pythonhashseed": "0",
        "power": "mains before and after each speed call",
        "ontology": "EFO 3.62.0",
        "ontology_owl_sha256": "f87fc3cdbae7fac68c5b2a470ae81da59bec3fa98ada908c5262dc89edcdb0bc",
        "target_terms": 29374,
        "max_mappings": 5,
        "speed_repeats": 5,
        "speed_warmups": 1,
        "speed_timer_excludes": "Imports, input loading, index loading, gc.collect and output checks",
        "operating_system_file_cache_cleared": False,
        "input_hashes": speed_status["input_hashes"],
        "accuracy_code_hashes_at_run": accuracy_status["code_hashes"],
        "speed_code_hashes_at_run": speed_status["code_hashes"],
    }
    environment_path = common.PACKAGE_DIR / "records" / "environment-20261102.json"
    common.write_json(environment_path, environment)

    report = {
        "accuracy_run": args.accuracy_run.name,
        "speed_run": args.speed_run.name,
        "accuracy_conditions_equal_old": 18,
        "accuracy_rows": len(ranks),
        "rank_changes_against_old": rank_changes,
        "speed_conditions": len(speed),
        "speed_calls": len(raw_speed),
        "speed_failures": 0,
        "power": "mains",
        "environment_sha256": common.sha256(environment_path),
        "files": {},
    }
    for folder in (result_dir, raw_dir):
        for path in sorted(folder.glob("*-20261102.tsv")):
            report["files"][path.name] = common.sha256(path)
    common.write_json(common.PACKAGE_DIR / "records" / "rerun-verification-20261102.json", report)
    print("Accuracy: 18 summary conditions match the earlier counts")
    print("Accuracy: 11,693 evaluation rows; rank changes:", rank_changes)
    print("Speed: 111 successful calls, 18 summary conditions, all on AC power")
    return 0


if __name__ == "__main__":
    sys.exit(main())
