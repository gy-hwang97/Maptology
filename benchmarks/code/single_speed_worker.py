import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

import benchmark_common as common
import run_speed as speed
import single_search as searcher


def measure(job_path):
    folder = job_path.parent
    if (folder / "speed-timings.tsv").exists() or (folder / "status.json").exists():
        raise RuntimeError("This measurement attempt already exists")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    method = job["method_id"]
    record = {"status": "preparing", "process_id": os.getpid(),
              "process_created_at": psutil.Process().create_time(),
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "successful_requests": 0, "search_calls": 0,
              "prepare_power_before": speed.power_state()}
    common.write_json(folder / "status.json", record)
    try:
        if os.environ.get("PYTHONHASHSEED") != "0":
            raise RuntimeError("PYTHONHASHSEED must be 0")
        if record["prepare_power_before"] == "battery":
            raise RuntimeError("Connect the laptop power adapter")
        costs = {}
        start = time.perf_counter()
        engine = searcher.prepare_method(method, costs)
        record["prepare_seconds"] = time.perf_counter() - start
        record["prepare_steps"] = costs
        record["prepare_power_after"] = speed.power_state()
        if record["prepare_power_after"] == "battery":
            raise RuntimeError("Power disconnected during preparation")
        e12 = None
        mapper = None
        if method == "E12":
            e12 = engine
            record["E12_transforms_before_first_search"] = e12.transforms
            record["E12_score_calls_before_first_search"] = e12.score_calls
            record["E12_inputs_before_first_search"] = e12.computed_inputs
            if e12.transforms != 0 or e12.score_calls != 0 or e12.computed_inputs != 0:
                raise RuntimeError("E12 searched during preparation")
        else:
            mapper = engine
        record["search_calls_before_first_search"] = record["search_calls"]
        record["status"] = "measuring"
        common.write_json(folder / "status.json", record)
        for position, item in enumerate(job["items"], start=1):
            row = {"dataset": job["dataset"], "workload": job["workload"],
                   "method_id": method, "repeat": job["repeat"], "request_index": position,
                   "row_id": item["row_id"], "input_key": item["input_key"],
                   "input_rows_per_round": len(job["items"]), "group_id": job["group_id"],
                   "process_id": os.getpid(), "first_search": position == 1,
                   "power_before": speed.power_state(), "power_after": "",
                   "eligible": False, "status": "not_run", "seconds": "",
                   "candidates": "", "error": ""}
            try:
                if row["power_before"] == "battery":
                    raise RuntimeError("Power disconnected before a search")
                record["search_calls"] += 1
                start = time.perf_counter()
                output = searcher.search(method, item["input_key"], item["row_id"], e12, mapper)
                row["seconds"] = time.perf_counter() - start
                row["power_after"] = speed.power_state()
                row["eligible"] = row["power_after"] != "battery"
                if not row["eligible"]:
                    raise RuntimeError("Power disconnected during a search")
                found = searcher.signature(method, output, item["input_key"], item["row_id"])
                row["candidates"] = json.dumps(found, ensure_ascii=False)
                row["status"] = "ok"
            except BaseException as error:
                row["status"] = "error"
                row["error"] = type(error).__name__ + ": " + str(error)
                if not row["power_after"]:
                    row["power_after"] = speed.power_state()
                speed.append_row(folder / "speed-timings.tsv", speed.FIELDS, row)
                raise
            speed.append_row(folder / "speed-timings.tsv", speed.FIELDS, row)
            record["successful_requests"] += 1
            record["last_request_index"] = position
            if position == 1 or position % 20 == 0 or position == len(job["items"]):
                record["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
                common.write_json(folder / "status.json", record)
                print(job["dataset"], method, position, "/", len(job["items"]), flush=True)
            del output
        record["status"] = "complete"
    except BaseException as error:
        record["status"] = "stopped"
        record["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        record["power_at_end"] = speed.power_state()
        common.write_json(folder / "status.json", record)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    measure(args.job.resolve())


if __name__ == "__main__":
    main()
