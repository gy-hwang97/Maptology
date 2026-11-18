import argparse
import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

import benchmark_common as common
import run_speed as speed
import single_search as searcher


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def close(actual, expected, message):
    require(math.isclose(float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12), message)


def verify(folder, api_queries):
    started = datetime.now(timezone.utc).isoformat()
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    settings = status["settings"]
    require(settings["protocol"] == "single-no-warmup-v1", "Unexpected protocol")
    require(settings["warmup_queries"] == 0, "Warmups must be zero")
    require(settings["code_hashes"] == common.code_hashes(), "Code changed during measurement")
    require(settings["input_hashes"] == common.input_hashes(), "Inputs changed during measurement")
    assets = common.check_assets(False)
    manifest = assets / "asset-manifest.json"
    if not manifest.is_file():
        manifest = common.PACKAGE_DIR / "records" / "required-assets.tsv"
    require(manifest.is_file(), "The asset manifest is missing")
    require(common.sha256(manifest) == settings["asset_manifest_sha256"], "Asset manifest changed")
    require(os.environ.get("PYTHONHASHSEED") == "0", "PYTHONHASHSEED must be 0")
    expected = {}
    schedule = speed.plans(settings["workloads"], settings["sample"])
    for dataset, workload, items in schedule:
        expected[(dataset, workload)] = items
    require(len(status["groups"]) == len(schedule) * 2 * settings["repeats"], "Wrong group count")
    seen_groups = set()
    processes = set()
    combined = {}
    e12_outputs = {}
    t2t_outputs = {}
    api_items = {}
    measured = 0
    failures = 0
    discarded = 0
    e12_rows = 0
    for group in status["groups"]:
        key = (group["dataset"], group["workload"], group["method_id"])
        unique = key + (group["repeat"],)
        require(unique not in seen_groups, "Duplicate group")
        seen_groups.add(unique)
        require(group["status"] == "measured", "Incomplete group")
        require(group["items"] == expected[key[:2]], "Group inputs differ from fixed inputs")
        require(group["method_id"] in speed.METHODS, "Unexpected method")
        require(1 <= group["repeat"] <= settings["repeats"], "Unexpected repeat")
        attempt = folder / group["attempts"][-1]
        worker = json.loads((attempt / "status.json").read_text(encoding="utf-8"))
        process = (worker["process_id"], worker["process_created_at"])
        require(process not in processes, "A search process was reused across groups")
        processes.add(process)
        require(worker["status"] == "complete", "Worker did not complete")
        require(worker["finished_at_utc"] <= started, "Verification started before measurement finished")
        require(worker["search_calls_before_first_search"] == 0, "Search before first timer")
        require(worker["search_calls"] == len(group["items"]), "Missing or extra search calls")
        require(worker["prepare_power_before"] != "battery" and worker["prepare_power_after"] != "battery", "Preparation on battery")
        if group["method_id"] == "E12":
            for name in ("E12_transforms_before_first_search", "E12_score_calls_before_first_search", "E12_inputs_before_first_search"):
                require(worker[name] == 0, "E12 computed queries before timing")
        rows = speed.selected_rows(folder, group)
        require(len(rows) == len(group["items"]), "Missing or extra output rows")
        values = []
        for position, (row, item) in enumerate(zip(rows, group["items"]), start=1):
            require(row["status"] == "ok" and row["eligible"] == "True", "Failed or ineligible request")
            require(row["power_before"] != "battery" and row["power_after"] != "battery", "Search on battery")
            require(int(row["request_index"]) == position and row["row_id"] == item["row_id"], "Incorrect row order or ID")
            require(row["input_key"] == item["input_key"], "Wrong search string")
            require(row["first_search"] == str(position == 1), "Wrong first-search marker")
            require(int(row["process_id"]) == worker["process_id"], "Wrong process ID")
            require(int(row["repeat"]) == group["repeat"] and row["group_id"] == group["group_id"], "Wrong group identity")
            require((row["dataset"], row["workload"], row["method_id"]) == key, "Wrong condition label")
            seconds = float(row["seconds"])
            require(math.isfinite(seconds) and seconds > 0, "Invalid request time")
            values.append(seconds)
            measured += 1
            candidates = json.loads(row["candidates"])
            require(len(candidates) <= 5, "Too many candidates")
            iris = set()
            for iri, score in candidates:
                require(isinstance(iri, str) and iri not in iris and math.isfinite(float(score)), "Invalid candidate")
                iris.add(iri)
            if key[2] == "E12":
                e12_rows += 1
                if item["input_key"] in e12_outputs:
                    require(searcher.same(candidates, e12_outputs[item["input_key"]]), "E12 repeated output changed")
                e12_outputs[item["input_key"]] = candidates
            else:
                if item["input_key"] in t2t_outputs:
                    require(searcher.same(candidates, t2t_outputs[item["input_key"]]), "text2term repeated output changed")
                t2t_outputs[item["input_key"]] = candidates
                if key[0] not in api_items:
                    api_items[key[0]] = []
                if len(api_items[key[0]]) < api_queries:
                    api_items[key[0]].append(item)
        if key not in combined:
            combined[key] = {"totals": [], "values": [], "first": [], "later": []}
        combined[key]["totals"].append(math.fsum(values))
        combined[key]["values"].extend(values)
        combined[key]["first"].append(values[0])
        combined[key]["later"].extend(values[1:])
        for old in group["attempts"][:-1]:
            path = folder / old / "speed-timings.tsv"
            if path.exists():
                for row in common.read_tsv(path):
                    discarded += 1
                    if row["status"] != "ok" or row["eligible"] != "True":
                        failures += 1
    summaries = common.read_tsv(folder / "speed-results.tsv")
    require(len(summaries) == len(combined), "Wrong number of summary rows")
    summary_keys = set()
    for row in summaries:
        key = (row["dataset"], row["workload"], row["method_id"])
        require(key not in summary_keys and key in combined, "Duplicate or unexpected summary")
        summary_keys.add(key)
        data = combined[key]
        require(int(row["successful_requests"]) == len(data["values"]), "Wrong successful count")
        require(int(row["complete_repeats"]) == settings["repeats"], "Incomplete summary")
        for source, middle in (("totals", "total"), ("values", "request"), ("first", "first_search"), ("later", "later_request")):
            values = data[source]
            if values:
                close(row["mean_" + middle + "_seconds"], statistics.mean(values), "Wrong mean: " + middle)
                close(row["median_" + middle + "_seconds"], statistics.median(values), "Wrong median: " + middle)
            else:
                require(row["mean_" + middle + "_seconds"] == "", "An empty group has a mean")
        close(row["min_total_seconds"], min(data["totals"]), "Wrong minimum total")
        close(row["max_total_seconds"], max(data["totals"]), "Wrong maximum total")
        if settings["repeats"] == 1:
            require(row["sample_sd_total_seconds"] == "", "Single-round SD must be blank")
        else:
            close(row["sample_sd_total_seconds"], statistics.stdev(data["totals"]), "Wrong sample SD")
    e12 = searcher.prepare_method("E12")
    texts = list(e12_outputs)
    outputs, _ = e12.many(texts, batch_size=32, dedup=True)
    for text, output in zip(texts, outputs):
        wanted = searcher.signature("E12", output, text, "verification")
        require(searcher.same(e12_outputs[text], wanted), "E12 differs from batch: " + text)
    api_checked = 0
    for dataset, items in api_items.items():
        for item in items:
            frame = searcher.engines.t2t_map([item["input_key"]], [item["row_id"]])
            wanted = searcher.signature("T", frame, item["input_key"], item["row_id"])
            require(searcher.same(t2t_outputs[item["input_key"]], wanted), "text2term differs from official API")
            api_checked += 1
    return {"status": "passed", "started_at_utc": started,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "measured_requests": measured, "completed_groups": len(seen_groups),
            "fresh_search_processes": len(processes), "warmup_searches": 0,
            "first_search_included_in_total": True, "raw_totals_and_means_match_summary": True,
            "code_inputs_and_assets_unchanged": True, "E12_rows_checked": e12_rows,
            "E12_distinct_inputs_checked": len(texts), "text2term_official_single_API_checks": api_checked,
            "candidate_order_and_score_mismatches": 0, "rtol": 1e-12, "atol": 1e-12,
            "discarded_attempt_requests": discarded, "failed_or_ineligible_attempt_requests": failures,
            "note": "Validation ran after all timing in a separate process. This is not an accuracy evaluation."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-folder", type=Path, required=True)
    parser.add_argument("--api-queries", type=int, default=3)
    args = parser.parse_args()
    if args.api_queries < 1:
        raise RuntimeError("At least one official API check is required per dataset")
    folder = args.run_folder.resolve()
    try:
        report = verify(folder, args.api_queries)
    except BaseException as error:
        common.write_json(folder / "verification.json", {"status": "failed", "error": type(error).__name__ + ": " + str(error)})
        raise
    common.write_json(folder / "verification.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
