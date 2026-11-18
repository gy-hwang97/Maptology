import argparse
import csv
import importlib.metadata
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil

import benchmark_common as common


METHODS = ("E12", "T")
FIELDS = ("dataset", "workload", "method_id", "repeat", "request_index", "row_id",
          "input_key", "input_rows_per_round", "group_id", "process_id", "first_search",
          "power_before", "power_after", "eligible", "status", "seconds", "candidates", "error")


def power_state():
    battery = psutil.sensors_battery()
    if battery is None:
        return "no_battery_reported"
    if battery.power_plugged:
        return "mains"
    return "battery"


def workload_size(workloads):
    if workloads == "full":
        return None
    text = str(workloads)
    if text.isdigit() and str(int(text)) == text and int(text) >= 1:
        return int(text)
    raise RuntimeError("--workloads must be a positive integer or full")


def plans(workloads, sample):
    sample_size = workload_size(workloads)
    result = []
    for dataset in common.DATASETS:
        rows = common.read_tsv(common.INPUT_DIR / ("eval-" + dataset + ".tsv"))
        if sample_size is None:
            workload = "All evaluation rows"
            chosen = rows
        else:
            workload = "N=%d sample" % sample_size
            by_text = {}
            for row in rows:
                text = row["input_key"]
                if text and text not in by_text:
                    by_text[text] = row
            if sample_size > len(by_text):
                raise RuntimeError("%s has %d distinct strings, which is fewer than %d" % (
                    dataset, len(by_text), sample_size))
            chosen = []
            for text in random.Random(20261021).sample(sorted(by_text), sample_size):
                chosen.append(by_text[text])
        if sample:
            workload = "Code check: " + workload
        items = []
        for position, row in enumerate(chosen, start=1):
            if sample and position > 3:
                break
            text = row["input_key"]
            if not text:
                raise RuntimeError("The fixed input contains an empty search string")
            row_id = row.get("evaluation_row_id", dataset + "-sample-" + str(position))
            items.append({"row_id": row_id, "input_key": text})
        result.append((dataset, workload, items))
    return result


def append_row(path, fields, row):
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def write_rows(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def selected_rows(folder, group):
    if not group["attempts"]:
        return []
    path = folder / group["attempts"][-1] / "speed-timings.tsv"
    if not path.exists():
        return []
    return common.read_tsv(path)


def summarize(folder, status):
    raw = []
    rounds = []
    setup = []
    combined = {}
    for group in status["groups"]:
        selected = ""
        if group["attempts"]:
            selected = group["attempts"][-1]
        failures = 0
        discarded = 0
        for attempt in group["attempts"]:
            path = folder / attempt / "speed-timings.tsv"
            if path.exists():
                for row in common.read_tsv(path):
                    row["attempt"] = attempt
                    row["selected_attempt"] = str(attempt == selected)
                    raw.append(row)
                    if row["status"] != "ok" or row["eligible"] != "True":
                        failures += 1
                    if attempt != selected:
                        discarded += 1
            metadata = folder / attempt / "status.json"
            if metadata.exists():
                record = json.loads(metadata.read_text(encoding="utf-8"))
                setup.append({"group_id": group["group_id"], "dataset": group["dataset"],
                              "workload": group["workload"], "method_id": group["method_id"],
                              "repeat": group["repeat"], "attempt": attempt,
                              "selected_attempt": str(attempt == selected), "status": record["status"],
                              "process_id": record["process_id"], "prepare_seconds": record.get("prepare_seconds", ""),
                              "power_before": record.get("prepare_power_before", ""),
                              "power_after": record.get("prepare_power_after", "")})
        values = []
        later = []
        first = ""
        indices = set()
        for row in selected_rows(folder, group):
            if row["status"] == "ok" and row["eligible"] == "True":
                index = int(row["request_index"])
                if index in indices:
                    raise RuntimeError("Duplicate request in " + group["group_id"])
                indices.add(index)
                seconds = float(row["seconds"])
                values.append(seconds)
                if index == 1:
                    first = seconds
                else:
                    later.append(seconds)
        complete = group["status"] == "measured" and len(values) == len(group["items"])
        total = ""
        if complete:
            total = math.fsum(values)
        rounds.append({"dataset": group["dataset"], "workload": group["workload"],
                       "method_id": group["method_id"], "repeat": group["repeat"],
                       "group_id": group["group_id"], "input_rows": len(group["items"]),
                       "successful_requests": len(values), "complete": complete,
                       "total_search_seconds": total, "first_search_seconds": first,
                       "attempts": len(group["attempts"]), "discarded_attempt_requests": discarded,
                       "failed_or_ineligible_requests": failures})
        key = (group["dataset"], group["workload"], group["method_id"])
        if key not in combined:
            distinct = set()
            for item in group["items"]:
                distinct.add(item["input_key"])
            combined[key] = {"totals": [], "values": [], "later": [], "first": [],
                             "input_rows": len(group["items"]), "distinct_inputs": len(distinct),
                             "failures": 0, "discarded": 0}
        data = combined[key]
        data["values"].extend(values)
        data["later"].extend(later)
        data["failures"] += failures
        data["discarded"] += discarded
        if first != "":
            data["first"].append(first)
        if complete:
            data["totals"].append(total)
    summaries = []
    for key, data in combined.items():
        entry = {"dataset": key[0], "workload": key[1], "method_id": key[2],
                 "method_name": "Maptology E12", "input_rows": data["input_rows"],
                 "distinct_inputs": data["distinct_inputs"], "planned_repeats": status["settings"]["repeats"],
                 "complete_repeats": len(data["totals"]), "successful_requests": len(data["values"]),
                 "failed_or_ineligible_requests": data["failures"],
                 "discarded_attempt_requests": data["discarded"],
                 "median_total_seconds": "", "mean_total_seconds": "", "sample_sd_total_seconds": "",
                 "min_total_seconds": "", "max_total_seconds": "",
                 "median_request_seconds": "", "mean_request_seconds": "",
                 "median_first_search_seconds": "", "mean_first_search_seconds": "",
                 "median_later_request_seconds": "", "mean_later_request_seconds": ""}
        if key[2] == "T":
            entry["method_name"] = "text2term TF-IDF with preloaded terms and mapper"
        for source, middle in (("totals", "total"), ("values", "request"),
                               ("first", "first_search"), ("later", "later_request")):
            values = data[source]
            if values:
                entry["median_" + middle + "_seconds"] = statistics.median(values)
                entry["mean_" + middle + "_seconds"] = statistics.mean(values)
        if data["totals"]:
            entry["min_total_seconds"] = min(data["totals"])
            entry["max_total_seconds"] = max(data["totals"])
        if len(data["totals"]) > 1:
            entry["sample_sd_total_seconds"] = statistics.stdev(data["totals"])
        summaries.append(entry)
    write_rows(folder / "speed-timings.tsv", FIELDS + ("attempt", "selected_attempt"), raw)
    write_rows(folder / "speed-rounds.tsv", rounds[0].keys(), rounds)
    write_rows(folder / "speed-results.tsv", summaries[0].keys(), summaries)
    if setup:
        write_rows(folder / "setup-times.tsv", setup[0].keys(), setup)
    return summaries


def make_groups(schedule, repeats):
    groups = []
    for repeat in range(1, repeats + 1):
        for index, (dataset, workload, items) in enumerate(schedule):
            order = METHODS
            if (repeat + index) % 2 == 0:
                order = ("T", "E12")
            for method in order:
                groups.append({"group_id": "group-" + str(len(groups) + 1).zfill(3),
                               "dataset": dataset, "workload": workload, "method_id": method,
                               "repeat": repeat, "items": items, "attempts": [], "status": "pending"})
    return groups


def estimate(schedule, repeats):
    path = common.PACKAGE_DIR / "results" / "speed-single-no-warmup-full-20261116.tsv"
    rates = {}
    if path.exists():
        for row in common.read_tsv(path):
            rates[(row["dataset"], row["method_id"])] = float(row["mean_request_seconds"])
    seconds = 0.0
    requests = 0
    for dataset, workload, items in schedule:
        for method in METHODS:
            requests += len(items) * repeats
            if (dataset, method) not in rates:
                return {"seconds": None, "source": "No previous timing table is available"}
            seconds += len(items) * repeats * rates[(dataset, method)]
    return {"seconds": seconds, "measured_requests": requests,
            "source": "Recorded no-warmup timings on the reference laptop; no searches run for this estimate"}


def main():
    parser = argparse.ArgumentParser(description="Time single-string searches without warmups")
    parser.add_argument("--workloads", default="500",
                        help="Positive integer (strings sampled per dataset) or full")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--warmup-queries", type=int, choices=(0,), default=0)
    parser.add_argument("--sample", action="store_true", help="Code check only: three strings per dataset")
    parser.add_argument("--estimate", "--pilot-only", action="store_true", dest="estimate")
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        raise RuntimeError("Repeats must be positive")
    workload_size(args.workloads)
    schedule = plans(args.workloads, args.sample)
    prediction = estimate(schedule, args.repeats)
    print("Estimate:", json.dumps(prediction), flush=True)
    if args.estimate:
        return
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise RuntimeError("Set PYTHONHASHSEED=0 before starting Python")
    if power_state() == "battery":
        raise RuntimeError("Connect the laptop power adapter before measuring")
    for dataset in common.DATASETS:
        eval_path = common.INPUT_DIR / ("eval-" + dataset + ".tsv")
        if not eval_path.is_file():
            raise RuntimeError("Missing evaluation input: " + eval_path.name)
    assets = common.check_assets(False)
    asset_manifest = assets / "asset-manifest.json"
    if not asset_manifest.is_file():
        asset_manifest = common.PACKAGE_DIR / "records" / "required-assets.tsv"
    if not asset_manifest.is_file():
        raise RuntimeError("The asset manifest is missing")
    settings = {"protocol": "single-no-warmup-v1", "workloads": args.workloads,
                "repeats": args.repeats, "sample": args.sample, "warmup_queries": 0,
                "input_hashes": common.input_hashes(), "code_hashes": common.code_hashes(),
                "asset_manifest_sha256": common.sha256(asset_manifest)}
    if args.resume:
        folder = args.resume.resolve()
        status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        if status["settings"] != settings:
            raise RuntimeError("Resume settings, inputs, assets or code differ from this run")
        if status["status"] == "complete":
            print("Already complete:", folder)
            return
    else:
        folder = common.new_run("speed-single-cold")
        packages = {}
        for name in ("text2term", "numpy", "scipy", "scikit-learn", "pandas", "psutil", "sparse-dot-topn"):
            packages[name] = importlib.metadata.version(name)
        status = {"settings": settings, "status": "starting", "python": sys.version,
                  "platform": platform.platform(), "processor": platform.processor(), "packages": packages,
                  "logical_cpus": os.cpu_count(), "physical_cpus": psutil.cpu_count(logical=False),
                  "power_at_start": power_state(), "search_target": "EFO 3.62.0, 29,374 common terms",
                  "max_mappings": 5, "text2term_min_score": 0.0, "deduplicate_requests": False,
                  "process_policy": "New process for each method, dataset, workload and repeat; retained across its requests",
                  "cold_start_definition": "First search after loading existing assets in a new process; no earlier search in that process",
                  "timer_includes": "One search and candidate generation, including any lazy first-search initialization",
                  "timer_excludes": "Imports, input loading, index and ontology loading, mapper construction, matrix preparation, output serialization and validation",
                  "text2term_call": "TFIDFMapper.map on one input; TF-IDF fitting remains inside each call",
                  "maptology_call": "OptimizedE12.single on one input; no saved query results",
                  "os_file_cache_cleared": False, "hard_per_query_timeout_seconds": None,
                  "estimate": prediction, "groups": make_groups(schedule, args.repeats)}
    print("Run:", folder, flush=True)
    common.write_json(folder / "status.json", status)
    try:
        for group in status["groups"]:
            if group["status"] == "measured":
                continue
            if power_state() == "battery":
                raise RuntimeError("Connect the laptop power adapter")
            attempt = "groups/" + group["group_id"] + "/attempt-" + str(len(group["attempts"]) + 1).zfill(3)
            destination = folder / attempt
            destination.mkdir(parents=True)
            group["attempts"].append(attempt)
            group["status"] = "running"
            status["status"] = "measuring"
            status["active_group"] = group["group_id"]
            common.write_json(destination / "job.json", group)
            common.write_json(folder / "status.json", status)
            command = [sys.executable, "-B", str(common.CODE_DIR / "single_speed_worker.py"),
                       "--job", str(destination / "job.json")]
            print("Timing:", group["dataset"], group["method_id"], "round", group["repeat"],
                  "requests", len(group["items"]), flush=True)
            with (destination / "stdout.log").open("w", encoding="utf-8") as stdout:
                with (destination / "stderr.log").open("w", encoding="utf-8") as stderr:
                    result = subprocess.run(command, stdout=stdout, stderr=stderr)
            worker_status = destination / "status.json"
            if result.returncode != 0 or not worker_status.exists():
                group["status"] = "failed"
                raise RuntimeError("Search process failed; see " + str(destination))
            worker = json.loads(worker_status.read_text(encoding="utf-8"))
            if worker["status"] != "complete" or worker["successful_requests"] != len(group["items"]):
                group["status"] = "failed"
                raise RuntimeError("Incomplete search group: " + group["group_id"])
            group["status"] = "measured"
            common.write_json(folder / "status.json", status)
            summarize(folder, status)
        status["status"] = "validating"
        common.write_json(folder / "status.json", status)
        command = [sys.executable, "-B", str(common.CODE_DIR / "verify_speed_run.py"), "--run-folder", str(folder)]
        with (folder / "verification-stdout.log").open("w", encoding="utf-8") as stdout:
            with (folder / "verification-stderr.log").open("w", encoding="utf-8") as stderr:
                result = subprocess.run(command, stdout=stdout, stderr=stderr)
        if result.returncode != 0:
            raise RuntimeError("Post-measurement verification failed; see verification logs")
        verification = json.loads((folder / "verification.json").read_text(encoding="utf-8"))
        if verification["status"] != "passed":
            raise RuntimeError("Post-measurement verification did not pass")
        status["status"] = "complete"
        status.pop("error", None)
    except BaseException as error:
        status["status"] = "stopped"
        status["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        status["power_at_end"] = power_state()
        status["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        common.write_json(folder / "status.json", status)
        summarize(folder, status)
        print("Output:", folder, flush=True)


if __name__ == "__main__":
    main()
